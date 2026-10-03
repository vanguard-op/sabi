"""Payment-intent extraction service (FEAT-005/FEAT-009, MQ-001).

Turns a free-form payment request into the amount and payee Sabi confirms before it
signs a mandate (FEAT-005, user-flow Flow 2), grounding both in the catalogue so a
payment can never be bound to an invented amount or payee:

* retrieve catalogue records, render the versioned extraction prompt, call the pinned
  flash build under MQ-001's decoding settings, validate the structured output, and
  ground service, payee, amount, and reference against the retrieved facts;
* below the 0.70 cutoff, or when no grounded service or amount remains, the extraction
  is unresolved, asks exactly one clarifying question, and never presents a payment
  intent type;
* when the provider is unavailable or returns unusable output, degrade to keyword and
  search resolution with mandatory confirmation, so a payment can never start from a
  degraded answer (MQ-001 Fallback).

The capability runs on the MQ-001 intent-resolution model path and decoding (the
pinned flash build, temperature 0, top_p 1) because it is a specialised intent
resolution, and reuses that pinned path without extending the frozen model-serving
foundation.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from core.config import (
    CAPABILITY_DECODING,
    CAPABILITY_MODEL_PATH,
    MAX_RESULTS,
    PROMPT_VERSION,
    RETRIEVAL_LIMIT,
    Capability,
    ModelSettings,
)
from core.errors import OutputValidationError, ProviderUnavailable
from core.fallback import fallback_intent, keyword_resolution, summary_from_record
from core.grounding import build_context
from core.prompts import render
from core.provider import ModelProvider, ModelRequest, parse_json
from core.retrieval import RetrievalIndex, RetrievedRecord, render_untrusted_block
from core.schemas import ServiceSummary
from payment_intent.guardrails import ground_payment_intent
from payment_intent.prompts import load_prompt
from payment_intent.schemas import (
    PAYMENT_INTENT_RESPONSE_SCHEMA,
    PaymentIntentExtraction,
    PaymentIntentResponse,
)

logger = logging.getLogger("payment_intent.service")

MODEL_SOURCE = "model"
FALLBACK_SOURCE = "fallback"

_SYSTEM_INSTRUCTION = (
    "You extract the amount and payee for one Nigerian payment request into the pinned "
    "JSON schema. Payees, amounts, and references come only from the provided catalogue "
    "records or the user's own words, never from memory."
)


@dataclass(frozen=True)
class PaymentIntentOutcome:
    """One extraction, ready to render as the response body."""

    response: PaymentIntentResponse
    source: str
    used_fallback: bool
    citations: tuple[str, ...]
    flags: frozenset[str]
    model_id: str | None
    prompt_version: str


class PaymentIntentService:
    """Extracts a grounded amount and payee for a payment request."""

    def __init__(
        self,
        provider: ModelProvider,
        retrieval: RetrievalIndex,
        *,
        settings: ModelSettings | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self._provider = provider
        self._retrieval = retrieval
        self._settings = settings or ModelSettings()
        self._prompt_version = prompt_version

    def extract(
        self,
        text: str,
        *,
        locale: str = "en",
        channel: str = "app",
    ) -> PaymentIntentOutcome:
        """Extract a grounded amount and payee, or an unresolved clarifying request."""

        records: list[RetrievedRecord] = []
        try:
            records = list(self._retrieval.search(text, limit=RETRIEVAL_LIMIT))
            context = build_context(records)
            prompt = load_prompt(self._prompt_version)
            request = self._build_request(
                prompt.prompt_id,
                prompt.version,
                render(
                    prompt.text,
                    {
                        "user_message": text,
                        "locale": locale,
                        "channel": channel,
                        "retrieved_data": render_untrusted_block(records),
                    },
                ),
            )
            response = self._provider.generate(request)
            payload = parse_json(response.text) if response.parsed is None else response.parsed
            extraction = PaymentIntentExtraction.from_mapping(payload)
            grounding = ground_payment_intent(extraction, user_text=text, context=context)
            grounded = grounding.extraction
            # Structure and outcome only; the request text is never logged.
            logger.info(
                "payment_intent_extracted source=%s resolved=%s intent_type=%s "
                "confidence=%.3f fallback=false",
                MODEL_SOURCE,
                grounded.resolved,
                grounded.intent_type,
                grounded.confidence,
            )
            return PaymentIntentOutcome(
                response=PaymentIntentResponse.from_parts(
                    grounded,
                    candidates=self._candidates(
                        records,
                        target=grounded.service_id,
                        confidence=grounded.confidence,
                    ),
                    source=MODEL_SOURCE,
                ),
                source=MODEL_SOURCE,
                used_fallback=False,
                citations=grounding.citations,
                flags=grounding.flags,
                model_id=request.model_id,
                prompt_version=prompt.version,
            )
        except (ProviderUnavailable, OutputValidationError) as exc:
            return self._fallback(
                text,
                locale=locale,
                records=records,
                reason=type(exc).__name__,
            )

    def _fallback(
        self,
        text: str,
        *,
        locale: str,
        records: Sequence[RetrievedRecord],
        reason: str,
    ) -> PaymentIntentOutcome:
        resolution = keyword_resolution(text, self._retrieval, limit=MAX_RESULTS)
        unresolved = fallback_intent(text, resolution, locale=locale)
        logger.info("payment_intent_fallback reason=%s", reason)
        candidates = resolution.candidates
        if not candidates and records:
            candidates = tuple(
                summary
                for record in records
                if (summary := summary_from_record(record, confidence=0.0)) is not None
            )[:MAX_RESULTS]
        extraction = PaymentIntentExtraction(
            confidence=0.0,
            language=locale,
            clarifying_question=unresolved.clarifying_question,
        )
        return PaymentIntentOutcome(
            response=PaymentIntentResponse.from_parts(
                extraction, candidates=candidates, source=FALLBACK_SOURCE
            ),
            source=FALLBACK_SOURCE,
            used_fallback=True,
            citations=(),
            flags=frozenset({"provider_fallback"}),
            model_id=None,
            prompt_version=self._prompt_version,
        )

    def _build_request(
        self,
        prompt_id: str,
        prompt_version: str,
        contents: str,
    ) -> ModelRequest:
        # Reuse the pinned MQ-001 path and decoding: this is a specialised intent
        # resolution, so it runs on the flash build at temperature 0, top_p 1.
        capability = Capability.INTENT_RESOLUTION
        path = CAPABILITY_MODEL_PATH[capability]
        return ModelRequest(
            capability=capability,
            model_path=path,
            model_id=self._settings.model_id_for(path),
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            system_instruction=_SYSTEM_INSTRUCTION,
            contents=contents,
            response_schema=PAYMENT_INTENT_RESPONSE_SCHEMA,
            decoding=CAPABILITY_DECODING[capability],
            timeout_seconds=self._settings.timeout_seconds,
        )

    @staticmethod
    def _candidates(
        records: Sequence[RetrievedRecord],
        *,
        target: str | None,
        confidence: float,
    ) -> tuple[ServiceSummary, ...]:
        summaries: list[ServiceSummary] = []
        for record in records:
            item = summary_from_record(
                record,
                confidence=confidence if record.service_id == target else 0.0,
            )
            if item is not None:
                summaries.append(item)
        summaries.sort(key=lambda item: (0 if item.service_id == target else 1, -item.confidence))
        return tuple(summaries[:MAX_RESULTS])


__all__ = [
    "FALLBACK_SOURCE",
    "MODEL_SOURCE",
    "PaymentIntentOutcome",
    "PaymentIntentService",
]
