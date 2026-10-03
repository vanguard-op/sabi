"""Boundaries from the federal flows to the payment store and the FTeR source.

A federal receipt view needs the payment record that paid the obligation, and
capturing the Federal Treasury e-Receipt (FTeR) needs the government e-receipt
platform. The payment record lives in the isolated payment module behind the
shared port in :mod:`app.payments_port`; this module re-exports that boundary so
the ``app.federal.ports`` import path stays stable and owns only the two
federal-specific state-key resolvers and the FTeR source. Until the payment store
is wired, the shared default refuses with ``payment_unavailable`` rather than
inventing a payment, and an unwired e-receipt source reports nothing, which the
receipt endpoint renders as "awaiting the official receipt" and keeps checking
(FEAT-006).

Adapter state keys:
- ``app.state.federal_payment_lookup``: a ``PaymentLookup``.
- ``app.state.federal_receipt_source``: a ``FederalReceiptSource``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import Request

from app.payments_port import (
    InMemoryPaymentLookup,
    PaymentLookup,
    PaymentView,
    UnavailablePaymentLookup,
)


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


class FederalReceiptSource(Protocol):
    """Fetch a federal obligation's official e-receipt, or report none yet."""

    def fetch(self, *, payment_id: str, reference: str | None) -> FederalReceiptView | None:
        """Return the FTeR when the platform has issued it, else ``None``."""


class UnavailableReceiptSource:
    """Default FTeR source: the e-receipt platform is not wired.

    This is the documented degraded behaviour rather than an error: the receipt
    endpoint reports ``awaiting_receipt`` and the client keeps checking
    (FEAT-006; user-flow Flow 2, alternate F).
    """

    def fetch(self, *, payment_id: str, reference: str | None) -> FederalReceiptView | None:
        return None


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
