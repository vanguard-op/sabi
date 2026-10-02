"""Boundary to the isolated payment module.

The modular monolith holds the payment module behind this port so it can sit in
process now and move behind an HTTP hop later without touching callers
(architecture.md). No money moves in Phase 1: the default gateway refuses new
executions while discovery and receipt views keep working, which is the
documented degraded behaviour when the rail is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import APIError, ErrorCode


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    user_id: str
    capability_id: str | None
    amount: int
    currency: str
    payee: str
    payee_reference: str | None
    nonce: str
    idempotency_key: str
    channel: str


@dataclass(frozen=True, slots=True)
class PaymentResult:
    payment_id: str
    status: str
    rail_reference: str | None = None
    failure_reason: str | None = None


class PaymentGateway(Protocol):
    def execute(self, request: PaymentRequest) -> PaymentResult: ...

    def get(self, payment_id: str) -> PaymentResult | None: ...

    def health(self) -> str: ...


class DisabledPaymentGateway:
    """Phase 1 gateway: payment execution is not wired to a rail yet."""

    def execute(self, request: PaymentRequest) -> PaymentResult:
        raise APIError(
            503,
            ErrorCode.PAYMENT_UNAVAILABLE,
            "Payments are paused right now. Your request is safe; try again shortly.",
        )

    def get(self, payment_id: str) -> PaymentResult | None:
        return None

    def health(self) -> str:
        return "unavailable"
