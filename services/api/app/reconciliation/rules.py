"""Pure reconciliation rules (FEAT-006, FEAT-009).

operations.md, "Reconciliation operations", fixes the outcomes:

- Matched items are closed.
- An unmatched or mismatched item opens an exception case: a debit with no
  delivery, a payment the agency does not show, or a receipt with no matching
  payment.
- A federal collection is checked for no point-of-collection deduction and for
  arrival in the designated treasury account; a deduction or a wrong account is
  an exception and escalates.

The rules here are pure functions over records and statement lines, so they are
testable without a clock, a queue, or a running payment service. Correlation is
by rail reference first, falling back to the opaque payment id when the source
supplies one; a payment the rail never gave a reference for can still be matched
against a line that carries the payment id.

Business rule: an amount or currency disagreement is a mismatch, and a mismatch
is an exception even when both sides show the payment. A missing statement line
for an internal debit is the "debit with no delivery" exception. A statement
line with no internal payment is either a receipt Sabi never stored
(``receipt_missing``) or, for a federal collection, an agency record Sabi does
not recognise.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.reconciliation.ports import PaymentRecord, StatementLine


class MatchOutcome(StrEnum):
    """The disposition of one internal payment against the statements."""

    MATCHED = "matched"
    # The rail settled but the agency or treasury record disagrees on amount,
    # currency, deduction, or destination.
    MISMATCHED = "mismatched"
    # An internal debit with no statement line at all.
    NO_DELIVERY = "no_delivery"
    # A statement line with no internal payment to back it.
    UNKNOWN = "unknown"


class ExceptionType(StrEnum):
    """The case type an exception opens, from the schema ``PaymentCase`` enum."""

    FAILED_NO_DELIVERY = "failed_no_delivery"
    DISPUTED = "disputed"
    RECEIPT_MISSING = "receipt_missing"


@dataclass(frozen=True, slots=True)
class ReconciliationItem:
    """One internal payment paired with its statement line, or the absence."""

    payment: PaymentRecord
    statement: StatementLine | None
    outcome: MatchOutcome
    reason: str


@dataclass(frozen=True, slots=True)
class ReconciliationException:
    """An item that did not reconcile and must open a case."""

    payment_id: str
    user_id: str
    reference: str | None
    case_type: ExceptionType
    reason: str
    # A federal exception escalates to the payment partner immediately rather
    # than waiting out the case window (operations.md).
    escalate: bool = False


def _statement_key(line: StatementLine) -> tuple[str, str | None]:
    return (line.reference, line.payment_id)


def correlate(
    payments: list[PaymentRecord],
    statements: list[StatementLine],
) -> tuple[list[ReconciliationItem], list[ReconciliationException]]:
    """Pair payments with statement lines and classify each disposition.

    Returns the matched and unmatched items and the exceptions to open, in the
    order of the payments then any statement lines with no payment.
    """
    by_reference: dict[str, StatementLine] = {}
    by_payment_id: dict[str, StatementLine] = {}
    for line in statements:
        by_reference.setdefault(line.reference, line)
        if line.payment_id is not None:
            by_payment_id.setdefault(line.payment_id, line)

    items: list[ReconciliationItem] = []
    exceptions: list[ReconciliationException] = []
    matched_lines: set[tuple[str, str | None]] = set()

    for payment in payments:
        statement = _find_statement(payment, by_reference, by_payment_id)
        if statement is None:
            reason = "The service was debited but no rail or agency record was found."
            items.append(
                ReconciliationItem(
                    payment=payment,
                    statement=None,
                    outcome=MatchOutcome.NO_DELIVERY,
                    reason=reason,
                )
            )
            exceptions.append(_exception(payment, ExceptionType.FAILED_NO_DELIVERY, reason))
            continue

        matched_lines.add(_statement_key(statement))
        reason = _mismatch_reason(payment, statement)
        if reason is None:
            items.append(
                ReconciliationItem(
                    payment=payment,
                    statement=statement,
                    outcome=MatchOutcome.MATCHED,
                    reason="The internal record agrees with the statement.",
                )
            )
            continue

        items.append(
            ReconciliationItem(
                payment=payment,
                statement=statement,
                outcome=MatchOutcome.MISMATCHED,
                reason=reason,
            )
        )
        # A federal deduction or wrong account is escalated on the spot; a
        # domestic amount disagreement waits on the provider.
        escalate = payment.federal
        exceptions.append(
            _exception(payment, ExceptionType.DISPUTED, reason, escalate=escalate)
        )

    # A statement line Sabi has no payment for: a missing stored receipt when a
    # receipt source supplies it, otherwise an unrecognised collection.
    for line in statements:
        if _statement_key(line) in matched_lines:
            continue
        if line.payment_id is not None and any(
            item.payment.payment_id == line.payment_id for item in items
        ):
            continue
        exceptions.append(_orphan_exception(line))

    return items, exceptions


def _find_statement(
    payment: PaymentRecord,
    by_reference: dict[str, StatementLine],
    by_payment_id: dict[str, StatementLine],
) -> StatementLine | None:
    if payment.reference is not None and payment.reference in by_reference:
        return by_reference[payment.reference]
    return by_payment_id.get(payment.payment_id)


def _mismatch_reason(payment: PaymentRecord, statement: StatementLine) -> str | None:
    """Why the internal record and the statement disagree, or None if they agree."""
    if statement.currency != payment.currency:
        return "The statement currency does not match the payment."
    if statement.amount != payment.amount:
        return "The statement amount does not match the payment."
    if payment.federal:
        if statement.deduction != 0:
            return "A deduction was taken at the point of collection."
        if (
            payment.destination is not None
            and statement.destination is not None
            and statement.destination != payment.destination
        ):
            return "The collection did not arrive in the designated treasury account."
    return None


def _exception(
    payment: PaymentRecord,
    case_type: ExceptionType,
    reason: str,
    *,
    escalate: bool = False,
) -> ReconciliationException:
    return ReconciliationException(
        payment_id=payment.payment_id,
        user_id=payment.user_id,
        reference=payment.reference,
        case_type=case_type,
        reason=reason,
        escalate=escalate,
    )


def _orphan_exception(line: StatementLine) -> ReconciliationException:
    """A statement line with no internal payment behind it."""
    if line.kind == "treasury" or line.kind == "rail":
        # A collection Sabi cannot match to a payment: the official receipt
        # cannot be stored without it (FEAT-008).
        case_type = ExceptionType.RECEIPT_MISSING
        reason = "A collection was recorded with no matching payment."
    else:
        # An agency record Sabi does not recognise is treated as a payment it
        # cannot show was delivered.
        case_type = ExceptionType.FAILED_NO_DELIVERY
        reason = "A statement line has no matching payment record."
    # The orphan carries no user id; the case is opened against the payment
    # record once one is known, so it is reported without an owner.
    return ReconciliationException(
        payment_id=line.payment_id or line.reference,
        user_id="",
        reference=line.reference,
        case_type=case_type,
        reason=reason,
    )


__all__ = [
    "ExceptionType",
    "MatchOutcome",
    "ReconciliationException",
    "ReconciliationItem",
    "correlate",
]
