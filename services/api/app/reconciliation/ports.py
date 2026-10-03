"""Boundaries the reconciliation and refund jobs reach across.

Daily reconciliation compares the payment records store against the licensed
rail statement and, for federal collections, against the agency collection
record (operations.md, "Reconciliation operations"). Those records live in the
isolated payment module and at two external sources, so this module defines the
shapes it needs and the application binds an adapter on ``app.state``.

No default reaches a live source: a deployment that has not wired the rail
statement reports ``payment_unavailable`` rather than treating every payment as
unmatched and opening exception cases against records Sabi cannot actually see.

Adapter state keys:
- ``app.state.reconciliation_payment_source``: a ``PaymentSource``.
- ``app.state.reconciliation_statement_source``: a ``StatementSource``.
- ``app.state.reconciliation_notifier``: a ``Notifier``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import Request

from app.core.errors import APIError, ErrorCode


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    """A payment as reconciliation sees it, read across the store boundary.

    ``reference`` is the rail reference; null means the rail never answered, so
    the item can only be compared against a statement line by payment id.
    ``destination`` is the account the money was sent to, used for the federal
    treasury-account check.
    """

    payment_id: str
    user_id: str
    reference: str | None
    amount: int
    currency: str
    payee: str
    status: str
    # True for a federal collection, which is checked for a deduction and for
    # arrival in the designated treasury account (operations.md).
    federal: bool = False
    destination: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StatementLine:
    """One line from the rail, agency, or treasury statement for a reference.

    ``kind`` is ``rail``, ``agency``, or ``treasury``; the job compares each
    source in turn. ``deduction`` is the amount taken at collection; any non-zero
    value on a federal collection is an exception. ``destination`` is the account
    the statement shows the money landed in.
    """

    reference: str
    amount: int
    currency: str
    kind: str = "rail"
    status: str = "settled"
    # Money not forwarded to the service; non-zero is a federal exception.
    deduction: int = 0
    destination: str | None = None
    payment_id: str | None = None


class PaymentSource(Protocol):
    """Read the internal payment records for a reconciliation window."""

    def payments(self, *, since: datetime, until: datetime) -> list[PaymentRecord]:
        """Settled or pending payments created in the window, internal records."""


class StatementSource(Protocol):
    """Read the external statement lines for a reconciliation window."""

    def statements(self, *, since: datetime, until: datetime) -> list[StatementLine]:
        """Rail, agency, and treasury lines in the window.

        A line of each ``kind`` is keyed by its reference; the job correlates on
        the reference first and falls back to the opaque payment id where the
        source supplies it.
        """


class UnavailablePaymentSource:
    """Default boundary: the internal payment store is not wired."""

    def payments(self, *, since: datetime, until: datetime) -> list[PaymentRecord]:
        raise _unavailable()


class UnavailableStatementSource:
    """Default boundary: no rail, agency, or treasury statement is wired."""

    def statements(self, *, since: datetime, until: datetime) -> list[StatementLine]:
        raise _unavailable()


class Notifier(Protocol):
    """The user-facing notification the case and refund events trigger."""

    def notify(self, *, user_id: str, template: str, detail: str | None = None) -> None: ...


class NullNotifier:
    """Default notifier: records nothing and sends nothing.

    Notifications are best-effort; a case that opens without one is still a
    correct case, so the default is a no-op rather than a failure.
    """

    def notify(self, *, user_id: str, template: str, detail: str | None = None) -> None:
        return None


class InMemoryPaymentSource:
    """Process-local payment source for development and tests."""

    def __init__(self, records: Sequence[PaymentRecord] = ()) -> None:
        self._records = list(records)

    def add(self, record: PaymentRecord) -> None:
        self._records.append(record)

    def payments(self, *, since: datetime, until: datetime) -> list[PaymentRecord]:
        return [record for record in self._records if _in_window(record.created_at, since, until)]


class InMemoryStatementSource:
    """Process-local statement source for development and tests."""

    def __init__(self, lines: Sequence[StatementLine] = ()) -> None:
        self._lines = list(lines)

    def add(self, line: StatementLine) -> None:
        self._lines.append(line)

    def statements(self, *, since: datetime, until: datetime) -> list[StatementLine]:
        return list(self._lines)


def _in_window(value: datetime | None, since: datetime, until: datetime) -> bool:
    # A record with no created time cannot be placed in the window and is
    # skipped rather than guessed into it.
    return value is not None and since <= value < until


def _unavailable() -> APIError:
    return APIError(
        503,
        ErrorCode.PAYMENT_UNAVAILABLE,
        "Payment records are unavailable right now. Try again shortly.",
    )


def get_payment_source(request: Request) -> PaymentSource:
    source = getattr(request.app.state, "reconciliation_payment_source", None)
    if source is None:
        return UnavailablePaymentSource()
    return source


def get_statement_source(request: Request) -> StatementSource:
    source = getattr(request.app.state, "reconciliation_statement_source", None)
    if source is None:
        return UnavailableStatementSource()
    return source


def get_notifier(request: Request) -> Notifier:
    notifier = getattr(request.app.state, "reconciliation_notifier", None)
    if notifier is None:
        return NullNotifier()
    return notifier


__all__ = [
    "InMemoryPaymentSource",
    "InMemoryStatementSource",
    "Notifier",
    "NullNotifier",
    "PaymentRecord",
    "PaymentSource",
    "StatementLine",
    "StatementSource",
    "UnavailablePaymentSource",
    "UnavailableStatementSource",
    "get_notifier",
    "get_payment_source",
    "get_statement_source",
]
