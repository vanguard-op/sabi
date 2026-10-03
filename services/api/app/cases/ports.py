"""Boundaries from the case service to the isolated payment store.

A case view needs the payment record and its append-only event timeline, and a
refund needs a write to the rail. Those live in the isolated payment module, so
this module defines the shapes it needs and the application binds an adapter on
``app.state``. Until that module is wired, the defaults refuse with
``payment_unavailable`` rather than reaching across the store boundary and never
fabricating a payment (architecture.md; schema.md, Overview).

Reads are account-scoped at the port: a payment or event belonging to another
user is never returned, so a guessed case id cannot expose someone else's
payment (least privilege, operations.md). This mirrors the receipt service's
payment boundary (``app.receipts.payments``); a single shared port is the
cleaner home for both and is raised as a change request rather than copied
again.

Adapter state keys:
- ``app.state.cases_payment_lookup``: a ``PaymentLookup``.
- ``app.state.cases_refund_port``: a ``RefundPort``; falls back to the lookup
  when the same adapter implements both.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import Request

from app.core.errors import APIError, ErrorCode


@dataclass(frozen=True, slots=True)
class PaymentView:
    """The payment fields a case summary and a refund decision need."""

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
class PaymentEventView:
    """One append-only payment state change, rendered in the case timeline."""

    event_id: str
    payment_id: str
    status: str
    actor: str
    occurred_at: datetime
    created_at: datetime
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RefundView:
    """The rail's answer to a refund request.

    ``status`` is ``reversed`` or ``refunded``; anything else means the refund
    has not settled and the payment stays as it was.
    """

    status: str
    refund_reference: str | None = None


class PaymentLookup(Protocol):
    """Read-only access to payment records and their timeline, user-scoped."""

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        """Return the payment if it exists and belongs to ``user_id``."""

    def events(self, *, user_id: str, payment_id: str) -> list[PaymentEventView]:
        """Return the payment's events if it belongs to ``user_id``."""


class RefundPort(Protocol):
    """Request a reversal or refund through the rail, keyed for idempotency."""

    def refund(
        self,
        *,
        user_id: str,
        payment_id: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundView: ...


class UnavailablePaymentLookup:
    """Default boundary: the payment store is not wired into this deployment.

    Mirrors ``UnavailablePaymentLookup`` in the receipt boundary: the capability
    is present but the backing dependency is absent, which is a system condition
    reported as ``payment_unavailable``, not a fabricated payment.
    """

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        raise _unavailable()

    def events(self, *, user_id: str, payment_id: str) -> list[PaymentEventView]:
        raise _unavailable()


class UnavailableRefundPort:
    """Default refund boundary when the rail is not wired."""

    def refund(
        self,
        *,
        user_id: str,
        payment_id: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundView:
        raise _unavailable()


class InMemoryPaymentLookup:
    """Process-local payment lookup for development and tests."""

    def __init__(
        self,
        payments: Sequence[PaymentView] = (),
        events: Sequence[PaymentEventView] = (),
    ) -> None:
        self._by_id = {payment.payment_id: payment for payment in payments}
        self._events: dict[str, list[PaymentEventView]] = {}
        for event in events:
            self._events.setdefault(event.payment_id, []).append(event)

    def add(self, payment: PaymentView) -> None:
        self._by_id[payment.payment_id] = payment

    def add_event(self, event: PaymentEventView) -> None:
        self._events.setdefault(event.payment_id, []).append(event)

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        payment = self._by_id.get(payment_id)
        if payment is None or payment.user_id != user_id:
            return None
        return payment

    def events(self, *, user_id: str, payment_id: str) -> list[PaymentEventView]:
        if self.get(user_id=user_id, payment_id=payment_id) is None:
            return []
        return list(self._events.get(payment_id, []))


def _unavailable() -> APIError:
    return APIError(
        503,
        ErrorCode.PAYMENT_UNAVAILABLE,
        "Payment records are unavailable right now. Try again shortly.",
    )


def get_payment_lookup(request: Request) -> PaymentLookup:
    lookup = getattr(request.app.state, "cases_payment_lookup", None)
    if lookup is None:
        return UnavailablePaymentLookup()
    return lookup


def get_refund_port(request: Request) -> RefundPort:
    port = getattr(request.app.state, "cases_refund_port", None)
    if port is not None:
        return port
    # A single adapter that also refunds can serve both boundaries.
    lookup = getattr(request.app.state, "cases_payment_lookup", None)
    if isinstance(lookup, RefundPort):  # pragma: no cover - structural check
        return lookup
    return UnavailableRefundPort()


__all__ = [
    "InMemoryPaymentLookup",
    "PaymentEventView",
    "PaymentLookup",
    "PaymentView",
    "RefundPort",
    "RefundView",
    "UnavailablePaymentLookup",
    "UnavailableRefundPort",
    "get_payment_lookup",
    "get_refund_port",
]
