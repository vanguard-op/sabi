"""Grounding: bind model output to retrieved facts and the user's own words.

The model-quality contract says facts about agencies, billers, amounts, references,
and receipts must come from the catalogue or the payment source, never from model
memory, and that the model must not emit an identifier, amount, or reference that is
not present in retrieved data. This module enforces that after generation: a value
that cannot be traced is dropped and flagged, and an unresolved target collapses the
intent to ``unknown`` so a payment type can never survive on an invented payee.

Amounts stated by the user are legitimate and are traced against the utterance,
including the common naira-to-kobo relationship.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from core.retrieval import RetrievedRecord
from core.schemas import (
    PAYMENT_INTENT_TYPES,
    Intent,
    RankingResult,
    ServiceSummary,
)


@dataclass(frozen=True)
class GroundingContext:
    """The set of facts model output is allowed to reference."""

    service_ids: frozenset[str] = frozenset()
    amounts: frozenset[int] = frozenset()
    references: frozenset[str] = frozenset()
    records: tuple[RetrievedRecord, ...] = ()

    def record_for(self, service_id: str | None) -> RetrievedRecord | None:
        if service_id is None:
            return None
        for record in self.records:
            if record.record_id == service_id or record.service_id == service_id:
                return record
        return None


@dataclass(frozen=True)
class GroundingReport:
    """Flags raised while grounding one intent."""

    flags: frozenset[str] = frozenset()
    citations: tuple[str, ...] = ()


def build_context(records: Sequence[RetrievedRecord]) -> GroundingContext:
    service_ids: set[str] = set()
    amounts: set[int] = set()
    references: set[str] = set()
    for record in records:
        if record.service_id:
            service_ids.add(record.service_id)
        if record.record_id:
            service_ids.add(record.record_id)
        if record.known_amount is not None:
            amounts.add(record.known_amount)
        if record.reference:
            references.add(record.reference)
    return GroundingContext(
        service_ids=frozenset(service_ids),
        amounts=frozenset(amounts),
        references=frozenset(references),
        records=tuple(records),
    )


# --- Amount tracing --------------------------------------------------------------

_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
_SUFFIX = {"k": 1_000, "m": 1_000_000}


def _number_words(tokens: Sequence[str]) -> list[int]:
    """Parse simple English/Pidgin number phrases such as "five thousand"."""

    values: list[int] = []
    current = 0
    seen = False

    def flush() -> None:
        nonlocal current, seen
        if seen:
            values.append(current)
        current = 0
        seen = False

    for token in tokens:
        if token in _UNITS:
            current += _UNITS[token]
            seen = True
        elif token in _TENS:
            current += _TENS[token]
            seen = True
        elif token in _SCALES:
            current = (current or 1) * _SCALES[token]
            seen = True
        elif token in {"and", "naira", "kobo", "naria"}:
            continue
        else:
            flush()
    flush()
    return values


def amounts_in_text(text: str) -> frozenset[int]:
    """Extract candidate amounts (in naira units) from free text deterministically."""

    lowered = text.lower()
    found: set[int] = set()

    for match in re.finditer(r"(?<![\w.])(\d[\d,]*)(?:\.(\d+))?\s*([km])\b", lowered):
        whole = int(match.group(1).replace(",", ""))
        if match.group(2):
            whole += int(match.group(2)) / (10 ** len(match.group(2)))
        found.add(int(whole * _SUFFIX[match.group(3)]))

    for match in re.finditer(r"(?<![\w.])(\d[\d,]*)(?:\.\d+)?(?![\w])", lowered):
        found.add(int(match.group(1).replace(",", "")))

    words = [token for token in re.findall(r"[a-z]+", lowered)]
    found.update(_number_words(words))
    return frozenset(found)


def amount_is_traceable(
    amount: int,
    *,
    user_text: str,
    context: GroundingContext,
) -> bool:
    """True when the amount is in retrieved data or traceable to the user's words.

    A user-states-naira / model-emits-kobo pair is accepted in both directions so a
    correct conversion is not mistaken for an invented number.
    """

    if amount in context.amounts:
        return True
    stated = amounts_in_text(user_text)
    if amount in stated:
        return True
    for value in stated:
        if value and amount == value * 100:
            return True
        if value and amount % 100 == 0 and amount // 100 == value:
            return True
    return False


def ground_intent(
    intent: Intent,
    *,
    user_text: str,
    context: GroundingContext,
) -> tuple[Intent, GroundingReport]:
    """Drop ungrounded target, amount, and reference; flag what was dropped."""

    flags: set[str] = set()
    citations: list[str] = []

    target = intent.target
    if target is not None and target not in context.service_ids:
        flags.add("ungrounded_target")
        target = None
    if target is not None:
        citations.append(target)

    amount = intent.amount
    if amount is not None and not amount_is_traceable(amount, user_text=user_text, context=context):
        flags.add("ungrounded_amount")
        amount = None

    reference = intent.reference
    if reference is not None and reference not in context.references:
        flags.add("ungrounded_reference")
        reference = None

    grounded = replace(intent, target=target, amount=amount, reference=reference)

    # An unresolved target must never survive inside a payment intent.
    if target is None and grounded.intent_type in PAYMENT_INTENT_TYPES:
        flags.add("unresolved")
        grounded = replace(grounded, intent_type="unknown")

    deduped = tuple(dict.fromkeys(citations))
    return grounded, GroundingReport(flags=frozenset(flags), citations=deduped)


def ground_ranking(
    result: RankingResult,
    *,
    context: GroundingContext,
) -> RankingResult:
    """Keep only results whose service_id exists in the retrieved set.

    Order is preserved; a ranking that cites nothing, or a fabricated service, yields
    an empty set rather than an invented result.
    """

    kept: list[ServiceSummary] = []
    for item in result.results:
        if item.service_id in context.service_ids:
            kept.append(item)
    if len(kept) == len(result.results) and result.results:
        return result
    return RankingResult(results=tuple(kept), no_match=not kept)
