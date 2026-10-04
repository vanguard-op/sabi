"""Model serving: the three model-backed capabilities behind one seam.

This is the "Model Serving" component. Each capability retrieves grounding content,
renders a versioned prompt, calls the pinned provider under pinned decoding settings,
validates the structured output, grounds it against the retrieved facts, applies the
guardrails, and degrades to the documented fallback when the provider fails or the
output is unusable. The HTTP contract layers (C-009, C-010, C-012) are thin adapters
over these methods.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from core.config import (
    CAPABILITY_DECODING,
    CAPABILITY_MODEL_PATH,
    MAX_RESULTS,
    PROMPT_VERSION,
    RETRIEVAL_LIMIT,
    Capability,
    ModelSettings,
    prompt_version_for,
)
from core.errors import OutputValidationError, ProviderUnavailable
from core.fallback import (
    FallbackResolution,
    fallback_intent,
    keyword_resolution,
    summary_from_record,
)
from core.grounding import build_context, ground_ranking
from core.guardrails import (
    RANKING_CONFIDENCE_THRESHOLD,
    validate_composition,
)
from core.guardrails import enforce_intent as apply_intent_guardrails
from core.history import (
    CLARIFICATION_LIMIT,
    CLARIFICATION_LIMIT_KEY,
    ConversationTurn,
    clarifying_questions_asked,
    render_history,
)
from core.prompts import load_prompt, render
from core.provider import ModelProvider, ModelRequest, parse_json
from core.retrieval import RetrievalIndex, RetrievedRecord, render_untrusted_block
from core.schemas import (
    CLIENT_COMPONENT_CATALOGUE,
    COMPOSITION_RESPONSE_SCHEMA,
    FALLBACK_TASKS,
    INTENT_RESPONSE_SCHEMA,
    NON_COMMAND_INTENT_TYPE,
    RANKING_RESPONSE_SCHEMA,
    Intent,
    RankingResult,
    ServiceSummary,
)
from core.telemetry import CostTracker, TaskCost

logger = logging.getLogger("core.serving")

MODEL_SOURCE = "model"
FALLBACK_SOURCE = "fallback"

_SYSTEM_INSTRUCTIONS: Mapping[Capability, str] = {
    Capability.INTENT_RESOLUTION: (
        "You resolve Nigerian payment and discovery requests into the pinned JSON "
        "schema. Facts come only from the provided catalogue records."
    ),
    Capability.DISCOVERY_RANKING: (
        "You rank catalogue records for a discovery query. You never invent a "
        "service or a collecting body."
    ),
    Capability.INTERFACE_COMPOSITION: (
        "You compose a declarative UI message stream from the client's component "
        "catalogue. You never emit executable code or external resource loads."
    ),
}


@dataclass(frozen=True)
class IntentResolution:
    """The result of MQ-001 intent resolution, shaped for C-009."""

    intent: Intent
    candidates: tuple[ServiceSummary, ...]
    source: str
    citations: tuple[str, ...] = ()
    model_id: str | None = None
    prompt_version: str = PROMPT_VERSION
    used_fallback: bool = False
    flags: frozenset[str] = frozenset()
    note: str | None = None
    cost: TaskCost | None = None


@dataclass(frozen=True)
class RankingOutcome:
    """The result of MQ-002 discovery ranking, shaped for C-010."""

    results: tuple[ServiceSummary, ...]
    no_match: bool
    source: str
    citations: tuple[str, ...] = ()
    model_id: str | None = None
    prompt_version: str = PROMPT_VERSION
    used_fallback: bool = False
    cost: TaskCost | None = None


@dataclass(frozen=True)
class CompositionOutcome:
    """The result of MQ-003 interface composition, shaped for C-012."""

    messages: tuple[Mapping[str, Any], ...]
    fallback: str
    source: str
    model_id: str | None = None
    prompt_version: str = PROMPT_VERSION
    used_fallback: bool = False
    cost: TaskCost | None = None


class ModelServing:
    """Runs the model-backed capabilities against a provider and a retrieval index."""

    def __init__(
        self,
        provider: ModelProvider,
        retrieval: RetrievalIndex,
        *,
        settings: ModelSettings | None = None,
        prompt_version: str | None = None,
        allowed_components: Sequence[str] | None = None,
    ) -> None:
        self._provider = provider
        self._retrieval = retrieval
        self._settings = settings or ModelSettings()
        # ``None`` means each capability loads the prompt version it is pinned to;
        # an explicit value is a test or evaluation override for all capabilities.
        self._prompt_version = prompt_version
        self._allowed_components = (
            frozenset(allowed_components)
            if allowed_components is not None
            else CLIENT_COMPONENT_CATALOGUE
        )
        self._tracker = CostTracker()

    # -- MQ-001 intent resolution -------------------------------------------------

    def resolve_intent(
        self,
        text: str,
        *,
        locale: str = "en",
        channel: str = "app",
        history: Sequence[ConversationTurn] = (),
        cost: TaskCost | None = None,
    ) -> IntentResolution:
        capability = Capability.INTENT_RESOLUTION
        task_cost = cost or self._begin(capability)
        asked = clarifying_questions_asked(history)
        records: list[RetrievedRecord] = []
        try:
            records = list(self._retrieval.search(text, limit=RETRIEVAL_LIMIT))
            context = build_context(records)
            prompt = load_prompt(capability, self._version_for(capability))
            request = self._build_request(
                capability,
                prompt.prompt_id,
                prompt.version,
                render(
                    prompt.text,
                    {
                        "user_message": text,
                        "locale": locale,
                        "channel": channel,
                        "retrieved_data": render_untrusted_block(records),
                        "conversation_history": render_history(history),
                        "clarifying_questions_asked": str(asked),
                        "clarification_limit": str(CLARIFICATION_LIMIT),
                    },
                ),
                INTENT_RESPONSE_SCHEMA,
            )
            response = self._provider.generate(request)
            task_cost.record(response.usage)
            payload = parse_json(response.text) if response.parsed is None else response.parsed
            intent = Intent.from_mapping(payload)
            outcome = apply_intent_guardrails(
                intent,
                user_text=text,
                context=context,
                locale=locale,
                clarifications_asked=asked,
            )
            # A non-command message carries no candidates: it is answered
            # conversationally, not resolved as a service.
            candidates = (
                ()
                if outcome.intent.intent_type == NON_COMMAND_INTENT_TYPE
                else self._candidates(
                    records, target=outcome.intent.target, confidence=outcome.intent.confidence
                )
            )
            return IntentResolution(
                intent=outcome.intent,
                candidates=candidates,
                source=MODEL_SOURCE,
                citations=outcome.citations,
                model_id=request.model_id,
                prompt_version=prompt.version,
                used_fallback=False,
                flags=outcome.flags,
                note=outcome.note,
                cost=task_cost,
            )
        except (ProviderUnavailable, OutputValidationError) as exc:
            return self._intent_fallback(
                text,
                locale=locale,
                records=records,
                task_cost=task_cost,
                reason=type(exc).__name__,
                clarifications_asked=asked,
            )

    def _intent_fallback(
        self,
        text: str,
        *,
        locale: str,
        records: Sequence[RetrievedRecord],
        task_cost: TaskCost,
        reason: str,
        clarifications_asked: int = 0,
    ) -> IntentResolution:
        resolution: FallbackResolution = keyword_resolution(
            text, self._retrieval, limit=MAX_RESULTS
        )
        logger.info("intent_fallback reason=%s", reason)
        candidates = resolution.candidates
        if not candidates and records:
            candidates = tuple(
                summary
                for record in records
                if (summary := summary_from_record(record, confidence=0.0)) is not None
            )[:MAX_RESULTS]
        flags = {"provider_fallback"}
        if clarifications_asked >= CLARIFICATION_LIMIT:
            # The degraded path must honour the same bound: decline rather than ask a
            # fourth question off the back of a keyword match.
            flags.add("clarification_limit_reached")
            intent = Intent(
                intent_type="unknown",
                confidence=0.0,
                language=locale,
                clarifying_question=None,
                constraints={CLARIFICATION_LIMIT_KEY: True},
            )
        else:
            intent = fallback_intent(text, resolution, locale=locale)
        return IntentResolution(
            intent=intent,
            candidates=candidates,
            source=FALLBACK_SOURCE,
            model_id=None,
            prompt_version=self._version_for(Capability.INTENT_RESOLUTION),
            used_fallback=True,
            flags=frozenset(flags),
            cost=task_cost,
        )

    # -- MQ-002 discovery ranking -------------------------------------------------

    def rank_services(
        self,
        query: str,
        *,
        category: str | None = None,
        limit: int = MAX_RESULTS,
        cost: TaskCost | None = None,
    ) -> RankingOutcome:
        capability = Capability.DISCOVERY_RANKING
        task_cost = cost or self._begin(capability)
        try:
            records = list(self._retrieval.search(query, limit=RETRIEVAL_LIMIT))
            context = build_context(records)
            prompt = load_prompt(capability, self._version_for(capability))
            request = self._build_request(
                capability,
                prompt.prompt_id,
                prompt.version,
                render(
                    prompt.text,
                    {
                        "user_query": query,
                        "category": category or "none",
                        "retrieved_data": render_untrusted_block(records),
                    },
                ),
                RANKING_RESPONSE_SCHEMA,
            )
            response = self._provider.generate(request)
            task_cost.record(response.usage)
            payload = parse_json(response.text) if response.parsed is None else response.parsed
            ranked = ground_ranking(RankingResult.from_mapping(payload), context=context)
            ranked = replace(
                ranked,
                results=tuple(
                    item
                    for item in ranked.results
                    if item.confidence >= RANKING_CONFIDENCE_THRESHOLD
                ),
            )
            ranked = replace(ranked, no_match=not ranked.results)
            ranked = replace(ranked, results=ranked.results[:limit])
            citations = tuple(item.service_id for item in ranked.results)
            return RankingOutcome(
                results=ranked.results,
                no_match=ranked.no_match,
                source=MODEL_SOURCE,
                citations=citations,
                model_id=request.model_id,
                prompt_version=prompt.version,
                used_fallback=False,
                cost=task_cost,
            )
        except (ProviderUnavailable, OutputValidationError) as exc:
            logger.info("ranking_fallback reason=%s", type(exc).__name__)
            resolution = keyword_resolution(query, self._retrieval, limit=limit)
            results = resolution.candidates[:limit]
            return RankingOutcome(
                results=results,
                no_match=not results,
                source=FALLBACK_SOURCE,
                citations=tuple(item.service_id for item in results),
                model_id=None,
                prompt_version=self._version_for(capability),
                used_fallback=True,
                cost=task_cost,
            )

    # -- MQ-003 interface composition ---------------------------------------------

    def compose_surface(
        self,
        task: str,
        context: Mapping[str, Any] | None = None,
        *,
        cost: TaskCost | None = None,
    ) -> CompositionOutcome:
        capability = Capability.INTERFACE_COMPOSITION
        task_cost = cost or self._begin(capability)
        fallback_key = task if task in FALLBACK_TASKS else "confirmation"
        try:
            prompt = load_prompt(capability, self._version_for(capability))
            request = self._build_request(
                capability,
                prompt.prompt_id,
                prompt.version,
                render(
                    prompt.text,
                    {
                        "task": task,
                        "context": json.dumps(context or {}, sort_keys=True, default=str),
                        "allowed_components": ", ".join(sorted(self._allowed_components)),
                    },
                ),
                COMPOSITION_RESPONSE_SCHEMA,
            )
            response = self._provider.generate(request)
            task_cost.record(response.usage)
            payload = parse_json(response.text) if response.parsed is None else response.parsed
            if not isinstance(payload, Mapping):
                raise OutputValidationError("composition payload must be an object")
            raw_messages = payload.get("messages")
            if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, (str, bytes)):
                raise OutputValidationError("messages must be an array")
            if any(not isinstance(item, Mapping) for item in raw_messages):
                raise OutputValidationError("every composition message must be an object")
            messages = [dict(item) for item in raw_messages]
            validation = validate_composition(messages, allowed_components=self._allowed_components)
            if not validation.ok or not messages:
                logger.info("composition_rejected errors=%d", len(validation.errors))
                return CompositionOutcome(
                    messages=(),
                    fallback=fallback_key,
                    source=FALLBACK_SOURCE,
                    model_id=request.model_id,
                    prompt_version=prompt.version,
                    used_fallback=True,
                    cost=task_cost,
                )
            return CompositionOutcome(
                messages=tuple(messages),
                fallback=fallback_key,
                source=MODEL_SOURCE,
                model_id=request.model_id,
                prompt_version=prompt.version,
                used_fallback=False,
                cost=task_cost,
            )
        except (ProviderUnavailable, OutputValidationError) as exc:
            logger.info("composition_fallback reason=%s", type(exc).__name__)
            return CompositionOutcome(
                messages=(),
                fallback=fallback_key,
                source=FALLBACK_SOURCE,
                model_id=None,
                prompt_version=self._version_for(capability),
                used_fallback=True,
                cost=task_cost,
            )

    # -- Internals ----------------------------------------------------------------

    def _version_for(self, capability: Capability) -> str:
        """The prompt version this serving instance uses for a capability."""

        return self._prompt_version or prompt_version_for(capability)

    def _begin(self, capability: Capability) -> TaskCost:
        model_id = self._settings.model_id_for_capability(capability)
        return self._tracker.begin(capability, model_id=model_id)

    def _build_request(
        self,
        capability: Capability,
        prompt_id: str,
        prompt_version: str,
        contents: str,
        response_schema: Mapping[str, Any],
    ) -> ModelRequest:
        path = CAPABILITY_MODEL_PATH[capability]
        return ModelRequest(
            capability=capability,
            model_path=path,
            model_id=self._settings.model_id_for(path),
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            system_instruction=_SYSTEM_INSTRUCTIONS[capability],
            contents=contents,
            response_schema=response_schema,
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
