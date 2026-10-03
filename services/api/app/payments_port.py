"""Cross-store boundary to the isolated payment module.

The primary store holds receipts and cases; the payment store holds the payment
records and their append-only events. They are separate databases joined by an
opaque scalar, never a foreign key (schema.md, Overview; architecture.md,
"Payment Module" and "Data architecture"). Every read that a receipt, a case, or
a refund needs about a payment crosses that boundary here, so the boundary is
defined once rather than copied per consumer.

Two rules hold at the port and are not the caller's to re-check:

- Reads are scoped to the account owner. A payment or event belonging to another
  user is never returned, so a guessed receipt or case id cannot expose someone
  else's payment (least privilege, operations.md).
- The default lookup refuses like the rail boundary does
  (``app.payment_gateway``). A deployment that has not wired the payment store
  reports ``payment_unavailable`` rather than fabricating a payment, so a
  receipt view is never invented from a record the system cannot reach.

The concrete adapter is supplied by the payment module and bound on the consumer
state key: ``app.state.receipts_payment_lookup`` for the receipt service and
``app.state.cases_payment_lookup`` / ``app.state.cases_refund_port`` for the case
service. Nothing here builds a network client; the port is resolved lazily so the
monolith boots before the payment module lands, exactly as the app factory skips
a module whose router is absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.errors import APIError, ErrorCode


@dataclass(frozen=True, slots=True)
class PaymentView:
    """The payment fields a receipt view and a case summary need.

    Amount, currency, and payee are stored on the payment at execution time, so
    a receipt never changes when a catalogue entry is later edited
    (schema.md, Payment).
    """

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
    """One append-only payment state change, rendered in the case timeline.

    Maps to PaymentEvent in the isolated store (schema.md, PaymentEvent).
    """

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
    """Read-only access to payment records and their timeline, user-scoped.

    A consumer uses only the operations it needs: the receipt service batches a
    page with :meth:`get_many`, the case service reads a single payment and its
    :meth:`events`. Both adapters in this module implement the whole boundary.
    """

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        """Return the payment if it exists and belongs to ``user_id``."""

    def get_many(self, *, user_id: str, payment_ids: Sequence[str]) -> dict[str, PaymentView]:
        """Return the payments that exist and belong to ``user_id``, by id."""

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

    Mirrors ``DisabledPaymentGateway``: the capability is present but the
    backing dependency is absent. It is a system condition, not a client error,
    and the client is told payments are unavailable rather than shown a receipt
    or case with fabricated payment fields.
    """

    def get(self, *, user_id: str, payment_id: str) -> PaymentView | None:
        raise _unavailable()

    def get_many(self, *, user_id: str, payment_ids: Sequence[str]) -> dict[str, PaymentView]:
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
    """Process-local payment lookup for development and tests.

    A stand-in for the payment module's adapter so receipt and case views can be
    exercised without a second database; it is not used in production.
    """

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

    def get_many(self, *, user_id: str, payment_ids: Sequence[str]) -> dict[str, PaymentView]:
        found: dict[str, PaymentView] = {}
        for payment_id in payment_ids:
            payment = self.get(user_id=user_id, payment_id=payment_id)
            if payment is not None:
                found[payment_id] = payment
        return found

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


__all__ = [
    "InMemoryPaymentLookup",
    "PaymentEventView",
    "PaymentLookup",
    "PaymentView",
    "RefundPort",
    "RefundView",
    "UnavailablePaymentLookup",
    "UnavailableRefundPort",
]
