"""FastAPI dependency for the payment lookup boundary.

The concrete adapter is bound on ``app.state.receipts_payment_lookup`` at
startup by whoever wires the payment module. Nothing here builds a network
client; the port is resolved lazily so the monolith boots before the payment
module lands, exactly as the app factory skips a module whose router is absent.
"""

from __future__ import annotations

from fastapi import Request

from app.receipts.payments import PaymentLookup, UnavailablePaymentLookup


def get_payment_lookup(request: Request) -> PaymentLookup:
    lookup = getattr(request.app.state, "receipts_payment_lookup", None)
    if lookup is None:
        return UnavailablePaymentLookup()
    return lookup


__all__ = ["get_payment_lookup"]
