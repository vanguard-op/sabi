"""Boundaries from the federal flows to the payment store and the FTeR source.

A federal receipt view needs the payment record that paid the obligation, and
capturing the Federal Treasury e-Receipt (FTeR) needs the government e-receipt
platform. Both are external to the primary store, so this module states the
shapes it needs and the application binds adapters on ``app.state``. Until they
are wired, the defaults answer conservatively: an unwired payment store refuses
with ``payment_unavailable`` rather than inventing a payment, and an unwired
e-receipt source reports nothing, which the receipt endpoint renders as
"awaiting the official receipt" and keeps checking (FEAT-006).

Reads are account-scoped at the port: a payment belonging to another user is
never returned, so a guessed payment id cannot expose someone else's payment.

Adapter state keys:
- ``app.state.federal_payment_lookup``: a ``PaymentLookup``.
- ``app.state.federal_receipt_source``: a ``FederalReceiptSource``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import Request

from app.core.errors import APIError, ErrorCode


@dataclass(frozen=True, slots=True)
class PaymentView:
    """The payment fields the federal flows read across the store boundary."""

    payment_id: str
    user_id: str
    service_id: str
    # Reference returned by the rail; null until the rail answers.
    reference: str | None
    payee: str
    amount: int
    currency: str
    status: str
    channel: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FederalReceiptView:
    """The FTeR as the government source returns it.

    ``verification_status`` is ``verified``, ``unverified``, or ``pending``; the
    value is passed through to the stored receipt unchanged so the receipt shows
    what the source actually confirmed.
    """

    receipt_number: str
    verification_status: str
    document_ref: str | None = None
    issued_at: datetime | None = None


class PaymentLookup(Protocol):
    """Read-only access to payment records, scoped to the owning user."""

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        """Return the payment if it exists and belongs to ``user_id``."""


class FederalReceiptSource(Protocol):
    """Fetch a federal obligation's official e-receipt, or report none yet."""

    def fetch(self, *, payment_id: str, reference: str | None) -> FederalReceiptView | None:
        """Return the FTeR when the platform has issued it, else ``None``."""


class UnavailablePaymentLookup:
    """Default boundary: the payment store is not wired into this deployment."""

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        raise APIError(
            503,
            ErrorCode.PAYMENT_UNAVAILABLE,
            "Payment records are unavailable right now. Try again shortly.",
        )


class UnavailableReceiptSource:
    """Default FTeR source: the e-receipt platform is not wired.

    This is the documented degraded behaviour rather than an error: the receipt
    endpoint reports ``awaiting_receipt`` and the client keeps checking
    (FEAT-006; user-flow Flow 2, alternate F).
    """

    def fetch(self, *, payment_id: str, reference: str | None) -> FederalReceiptView | None:
        return None


class InMemoryPaymentLookup:
    """Process-local payment lookup for development and tests."""

    def __init__(self, payments: list[PaymentView] | None = None) -> None:
        self._by_id = {payment.payment_id: payment for payment in (payments or [])}

    def add(self, payment: PaymentView) -> None:
        self._by_id[payment.payment_id] = payment

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        payment = self._by_id.get(payment_id)
        if payment is None or payment.user_id != user_id:
            return None
        return payment


class InMemoryReceiptSource:
    """Process-local FTeR source for development and tests."""

    def __init__(self, receipts: dict[str, FederalReceiptView] | None = None) -> None:
        self._by_payment = dict(receipts or {})

    def add(self, payment_id: str, receipt: FederalReceiptView) -> None:
        self._by_payment[payment_id] = receipt

    def fetch(self, *, payment_id: str, reference: str | None) -> FederalReceiptView | None:
        return self._by_payment.get(payment_id)


def get_payment_lookup(request: Request) -> PaymentLookup:
    lookup = getattr(request.app.state, "federal_payment_lookup", None)
    if lookup is None:
        return UnavailablePaymentLookup()
    return lookup


def get_receipt_source(request: Request) -> FederalReceiptSource:
    source = getattr(request.app.state, "federal_receipt_source", None)
    if source is None:
        return UnavailableReceiptSource()
    return source


__all__ = [
    "FederalReceiptSource",
    "FederalReceiptView",
    "InMemoryPaymentLookup",
    "InMemoryReceiptSource",
    "PaymentLookup",
    "PaymentView",
    "UnavailablePaymentLookup",
    "UnavailableReceiptSource",
    "get_payment_lookup",
    "get_receipt_source",
]
