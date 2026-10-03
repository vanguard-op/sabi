"""Grounding and refusal for payment-intent extraction (MQ-001).

The quality contract is explicit: facts about agencies, billers, amounts, and
references must come from the catalogue or the payment source, never from model
memory, and the model must not emit an amount or a payee that retrieved data does not
support (model-quality.md, "Grounding, safety, and refusal behavior").

This module enforces that after generation:

* the payee is taken from the grounded record's ``collecting_body``; a payee the model
  might return is ignored because the provider schema has no payee field;
* an amount that cannot be traced to the user's words or a retrieved record is dropped
  and flagged, and a recorded ``known_amount`` fills a missing amount;
* a ``service_id`` or ``payee_reference`` absent from the retrieved set is dropped;
* below the 0.70 serving cutoff, or when no grounded service or amount remains, the
  extraction is unresolved, asks exactly one clarifying question, and never presents a
  payment intent type (MQ-001 Refusal).

Nothing here raises for an imperfect model answer; it repairs the result or marks it
unresolved so the caller asks or declines instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from core.config import INTENT_CONFIDENCE_CUTOFF
from core.grounding import GroundingContext, amount_is_traceable
from core.guardrails import normalize_question
from core.retrieval import RetrievedRecord
from payment_intent.schemas import PaymentIntentExtraction

# The single serving cutoff fixed at 0.70 (D-017), read from the model build rather
# than re-declared. Below it the extraction asks exactly one question and no payment
# intent is presented.
INTENT_CONFIDENCE_THRESHOLD = INTENT_CONFIDENCE_CUTOFF

DEFAULT_CLARIFYING_QUESTION = "Which service do you want to pay, and how much?"

# Catalogue categories that identify a federal or state collection. The catalogue
# record decides the payment type; the model never chooses it.
_GOVERNMENT_CATEGORIES = frozenset(
    {"government", "gov", "agency", "tax", "levy", "fee", "fees", "fine", "fines"}
)


@dataclass(frozen=True)
class PaymentGrounding:
    """The extraction after grounding, with the flags that explain any repair."""

    extraction: PaymentIntentExtraction
    flags: frozenset[str] = frozenset()
    citations: tuple[str, ...] = ()


def intent_type_for(record: RetrievedRecord) -> str:
    """Derive the payment intent type from the grounded catalogue record."""

    category = str(record.fields.get("category") or "").strip().lower()
    return "gov_payment" if category in _GOVERNMENT_CATEGORIES else "bill_payment"


def ground_payment_intent(
    extraction: PaymentIntentExtraction,
    *,
    user_text: str,
    context: GroundingContext,
) -> PaymentGrounding:
    """Ground service, payee, amount, and reference; apply the refusal rule."""

    flags: set[str] = set()
    citations: list[str] = []

    service_id = extraction.service_id
    if service_id is not None and service_id not in context.service_ids:
        flags.add("ungrounded_target")
        service_id = None

    record: RetrievedRecord | None = None
    if service_id is not None:
        record = context.record_for(service_id)
        if record is None:
            flags.add("ungrounded_target")
            service_id = None
        else:
            citations.append(service_id)

    # The payee is always the grounded record's collecting body, never the model's.
    payee: str | None = None
    if record is not None:
        body = record.fields.get("collecting_body")
        if isinstance(body, str) and body.strip():
            payee = body.strip()
        else:
            # A record with no collecting body cannot identify a payee.
            flags.add("ungrounded_target")
            service_id = None
            record = None

    amount = extraction.amount
    if amount is not None and not amount_is_traceable(amount, user_text=user_text, context=context):
        flags.add("ungrounded_amount")
        amount = None
    if amount is None and record is not None and record.known_amount is not None:
        amount = record.known_amount

    reference = extraction.payee_reference
    if reference is not None and reference not in context.references:
        flags.add("ungrounded_reference")
        reference = None

    low_confidence = extraction.confidence < INTENT_CONFIDENCE_THRESHOLD
    if low_confidence:
        flags.add("low_confidence")

    unresolved = record is None or amount is None or low_confidence
    if unresolved:
        flags.add("unresolved")
        intent_type = "unknown"
        question = normalize_question(extraction.clarifying_question or DEFAULT_CLARIFYING_QUESTION)
        resolved = False
    else:
        intent_type = intent_type_for(record)
        question = (
            normalize_question(extraction.clarifying_question)
            if extraction.clarifying_question
            else None
        )
        resolved = True

    grounded = replace(
        extraction,
        service_id=service_id,
        payee=payee,
        amount=amount,
        payee_reference=reference,
        intent_type=intent_type,
        clarifying_question=question,
        resolved=resolved,
    )
    return PaymentGrounding(
        extraction=grounded,
        flags=frozenset(flags),
        citations=tuple(dict.fromkeys(citations)),
    )


__all__ = [
    "DEFAULT_CLARIFYING_QUESTION",
    "INTENT_CONFIDENCE_THRESHOLD",
    "PaymentGrounding",
    "ground_payment_intent",
    "intent_type_for",
]
