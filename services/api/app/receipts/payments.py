"""Compatibility re-export for the receipt service's payment boundary.

The boundary shapes now live once in :mod:`app.payments_port`; this module keeps
the ``app.receipts.payments`` import path stable for callers while the state-key
resolver stays in :mod:`app.receipts.deps`. See the shared module for the
boundary's rules and the isolated store it fronts.
"""

from __future__ import annotations

from app.payments_port import (
    InMemoryPaymentLookup,
    PaymentLookup,
    PaymentView,
    UnavailablePaymentLookup,
)

__all__ = [
    "InMemoryPaymentLookup",
    "PaymentLookup",
    "PaymentView",
    "UnavailablePaymentLookup",
]
