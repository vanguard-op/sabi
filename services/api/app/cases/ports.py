"""Boundaries from the case service to the isolated payment store.

The boundary shapes now live once in :mod:`app.payments_port`; this module keeps
the ``app.cases.ports`` import path stable for callers and owns the two
case-specific state-key resolvers. A case view needs the payment record and its
append-only event timeline, and a refund needs a write to the rail; both live in
the isolated payment module behind that shared port. Until the module is wired,
the defaults refuse with ``payment_unavailable`` rather than reaching across the
store boundary and never fabricating a payment (architecture.md; schema.md).

Adapter state keys:
- ``app.state.cases_payment_lookup``: a ``PaymentLookup``.
- ``app.state.cases_refund_port``: a ``RefundPort``; falls back to the lookup
  when the same adapter implements both.
"""

from __future__ import annotations

from fastapi import Request

from app.payments_port import (
    InMemoryPaymentLookup,
    PaymentEventView,
    PaymentLookup,
    PaymentView,
    RefundPort,
    RefundView,
    UnavailablePaymentLookup,
    UnavailableRefundPort,
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
