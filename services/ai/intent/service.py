"""Intent resolution service (MQ-001, C-009).

A thin adapter over :class:`~core.serving.ModelServing`:

* it grounds on the candidate services the gateway forwards for the request, falling
  back to its own retrieval index when none are forwarded, renders the earlier turns of
  the conversation, lets the pinned flash model resolve the structured intent, grounds
  target, amount, and reference against the retrieved facts, and applies the refusal
  guardrail;
* the model authors the user-facing ``reply`` in the request locale (greeting,
  clarifying question, refusal, or non-resolving reply) alongside the reduced
  machine-actionable intent; the reply is not pinned or rewritten, and it is dropped
  to null when it is missing, empty, unsafe, or ungrounded so the client renders its
  prewritten fallback;
* below the 0.70 confidence cutoff the intent is unresolved and asks its follow-up in
  the reply, building on the earlier turns, up to three in one conversation, and
  never presents a payment type; at the bound it declines instead of asking again;
* a greeting or other non-command message resolves to ``non_command`` with no
  clarifying question, no payment field, and nothing recorded for coverage;
* when the provider is unavailable or returns unusable output, ``ModelServing``
  degrades to keyword and search resolution with mandatory confirmation, so a payment
  can never start from a degraded answer.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from core.history import ConversationTurn
from core.retrieval import RetrievedRecord
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

    def resolve(
        self,
        text: str,
        *,
        locale: str = "en",
        channel: str = "app",
        history: Sequence[ConversationTurn] = (),
        candidates: Sequence[RetrievedRecord] | None = None,
    ) -> IntentOutcome:
        result: IntentResolution = self._serving.resolve_intent(
            text,
            locale=locale,
            channel=channel,
            history=history,
            candidates=candidates,
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
