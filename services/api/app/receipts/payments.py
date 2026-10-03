"""Boundary from the receipt service to the isolated payment module.

The primary store holds the receipt record and the payment store holds the
payment it proves; they are separate databases joined by an opaque scalar, never
a foreign key (schema.md, Overview; architecture.md, "Payment Module"). A
receipt view therefore needs the payment's reference, payee, amount, currency,
and status, and this port is the only place that fetches them.

The concrete adapter is supplied by the payment module and bound on
``app.state.receipts_payment_lookup``; the default refuses like the rail
boundary does (``app.payment_gateway``), so a deployment that has not wired the
payment store reports ``payment_unavailable`` rather than inventing a receipt.
Tests bind the in-memory adapter without a second database.

The lookup is scoped to the account owner: a payment that belongs to another
user is never returned, so a guessed receipt id cannot expose someone else's
payment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.errors import APIError, ErrorCode


@dataclass(frozen=True, slots=True)
class PaymentView:
    """The payment fields a receipt view needs, read across the store boundary."""

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


class PaymentLookup(Protocol):
    """Read-only access to payment records, scoped to the owning user."""

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        """Return the payment if it exists and belongs to ``user_id``."""

    def get_many(self, *, user_id: str, payment_ids: Sequence[str]) -> dict[str, PaymentView]:
        """Return the payments that exist and belong to ``user_id``, by id."""


class UnavailablePaymentLookup:
    """Default boundary: the payment store is not wired into this deployment.

    Mirrors ``DisabledPaymentGateway``: the capability is present but the
    backing dependency is absent. It is a system condition, not a client error,
    and the client is told payments are unavailable rather than shown a
    receipt with fabricated payment fields.
    """

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        raise APIError(
            503,
            ErrorCode.PAYMENT_UNAVAILABLE,
            "Payment records are unavailable right now. Try again shortly.",
        )

    def get_many(self, *, user_id: str, payment_ids: Sequence[str]) -> dict[str, PaymentView]:
        raise APIError(
            503,
            ErrorCode.PAYMENT_UNAVAILABLE,
            "Payment records are unavailable right now. Try again shortly.",
        )


class InMemoryPaymentLookup:
    """Process-local payment lookup for development and tests.

    A stand-in for the payment module's adapter so receipt views can be exercised
    without a second database; it is not used in production.
    """

    def __init__(self, payments: Sequence[PaymentView] = ()) -> None:
        self._by_id = {payment.payment_id: payment for payment in payments}

    def add(self, payment: PaymentView) -> None:
        self._by_id[payment.payment_id] = payment

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        payment = self._by_id.get(payment_id)
        if payment is None or payment.user_id != user_id:
            return None
        return payment

    def get_many(self, *, user_id: str, payment_ids: Sequence[str]) -> dict[str, PaymentView]:
        found: dict[str, PaymentView] = {}
        for payment_id in payment_ids:
            payment = self.get(user_id=user_id, payment_id=payment_id)
            if payment is not None:
                found[payment_id] = payment
        return found


__all__ = [
    "InMemoryPaymentLookup",
    "PaymentLookup",
    "PaymentView",
    "UnavailablePaymentLookup",
]
