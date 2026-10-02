"""Intent resolution service (MQ-001, C-009).

A thin adapter over :class:`~core.serving.ModelServing`:

* it retrieves grounding records, lets the pinned flash model resolve the structured
  intent, grounds target, amount, and reference against the retrieved facts, and
  applies the refusal guardrail;
* below the 0.70 confidence cutoff the intent is unresolved, asks exactly one
  clarifying question, and never presents a payment type;
* when the provider is unavailable or returns unusable output, ``ModelServing``
  degrades to keyword and search resolution with mandatory confirmation, so a payment
  can never start from a degraded answer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.serving import IntentResolution, ModelServing
from intent.schemas import IntentResponse

logger = logging.getLogger("intent.service")


@dataclass(frozen=True)
class IntentOutcome:
    """One intent resolution, ready to render as the C-009 body."""

    response: IntentResponse
    source: str
    used_fallback: bool
    citations: tuple[str, ...]
    flags: frozenset[str]


class IntentService:
    """Resolves a free-form request into a structured intent."""

    def __init__(self, serving: ModelServing) -> None:
        self._serving = serving

    def resolve(self, text: str, *, locale: str = "en", channel: str = "app") -> IntentOutcome:
        result: IntentResolution = self._serving.resolve_intent(
            text, locale=locale, channel=channel
        )
        # Structure and outcome only; the free text of the request is never logged.
        logger.info(
            "intent_resolved source=%s intent_type=%s confidence=%.3f fallback=%s",
            result.source,
            result.intent.intent_type,
            result.intent.confidence,
            result.used_fallback,
        )
        return IntentOutcome(
            response=IntentResponse.from_resolution(result),
            source=result.source,
            used_fallback=result.used_fallback,
            citations=result.citations,
            flags=result.flags,
        )
