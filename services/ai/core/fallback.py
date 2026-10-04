"""Fallback resolution when the model is unavailable or unusable.

The documented degradation is keyword and search resolution with mandatory
confirmation: the product answers from the catalogue, labels the result unresolved,
and never guesses a payee. This path never fabricates a service or an amount.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.config import MAX_RESULTS
from core.retrieval import RetrievalIndex, RetrievedRecord
from core.schemas import ServiceSummary

FALLBACK_SOURCE = "fallback"

# Confidence attached to a lexical match. It is deliberately below the intent
# threshold so a fallback result always requires confirmation before payment.
FALLBACK_CONFIDENCE = 0.0


@dataclass(frozen=True)
class FallbackResolution:
    """Keyword candidates for a request the model could not resolve."""

    query: str
    candidates: tuple[ServiceSummary, ...]
    source: str = FALLBACK_SOURCE


def summary_from_record(record: RetrievedRecord, *, confidence: float) -> ServiceSummary | None:
    """Map a catalogue record to the contract :class:`ServiceSummary`, or None.

    A record missing the identifying fields is skipped rather than guessed.
    """
    fields = record.fields
    service_id = record.service_id
    name = fields.get("name")
    body = fields.get("collecting_body")
    if not service_id or not isinstance(name, str) or not isinstance(body, str):
        return None
    known_amount = record.known_amount
    return ServiceSummary(
        service_id=service_id,
        name=name,
        collecting_body=body,
        category=str(fields.get("category") or "unknown"),
        confidence=confidence,
        known_amount=known_amount,
        currency=str(fields.get("currency") or "NGN"),
        status=str(fields.get("status") or "active"),
    )


def keyword_resolution(
    query: str,
    index: RetrievalIndex,
    *,
    limit: int = MAX_RESULTS,
) -> FallbackResolution:
    """Resolve a query by keyword search over catalogue names and aliases."""

    records: Sequence[RetrievedRecord] = index.search(query, limit=limit)
    candidates: list[ServiceSummary] = []
    for record in records:
        summary = summary_from_record(record, confidence=FALLBACK_CONFIDENCE)
        if summary is not None:
            candidates.append(summary)
    return FallbackResolution(query=query, candidates=tuple(candidates))


@dataclass(frozen=True)
class FallbackIntent:
    """The degraded keyword path's unresolved result, before the intent is shaped.

    This is deliberately not the MQ-001 :class:`~core.schemas.Intent`: a capability
    that still holds a structured clarifying question (the payment-intent extraction)
    needs one from this path, while the MQ-001 reply path does not — there the client
    renders its prewritten fallback reply and the AI service sends ``reply: null``.
    """

    intent_type: str
    confidence: float
    clarifying_question: str | None = None


def fallback_intent(
    query: str,
    resolution: FallbackResolution,
    *,
    locale: str = "en",
) -> FallbackIntent:
    """An unresolved result for the degraded keyword path.

    The intent type is ``unknown`` and the confidence is zero, so no payment can
    proceed from this path without explicit confirmation. A keyword match offers a
    confirmation question for the capabilities that still render a structured one; no
    fact grounds this path, so nothing is claimed beyond what was searched.
    """

    del query, locale  # no language is claimed and no fact grounds this path
    if resolution.candidates:
        question = (
            f"I couldn't understand that request. Did you mean {resolution.candidates[0].name}?"
        )
    else:
        question = "I couldn't find that service. Can you name the biller or agency?"
    return FallbackIntent(
        intent_type="unknown",
        confidence=FALLBACK_CONFIDENCE,
        clarifying_question=question,
    )
