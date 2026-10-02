"""Payment state machine.

Transitions are explicit so an unknown rail outcome is held pending and
reconciled, never retried blindly, and a completed payment can only move to a
reversal or refund (architecture.md, FEAT-009).
"""

from __future__ import annotations

from enum import StrEnum


class PaymentState(StrEnum):
    INITIATED = "initiated"
    AUTHORIZED = "authorized"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REVERSED = "reversed"
    REFUNDED = "refunded"


ALLOWED_TRANSITIONS: dict[PaymentState, frozenset[PaymentState]] = {
    PaymentState.INITIATED: frozenset(
        {PaymentState.AUTHORIZED, PaymentState.PENDING, PaymentState.FAILED}
    ),
    PaymentState.AUTHORIZED: frozenset(
        {PaymentState.PENDING, PaymentState.SUCCEEDED, PaymentState.FAILED}
    ),
    PaymentState.PENDING: frozenset({PaymentState.SUCCEEDED, PaymentState.FAILED}),
    PaymentState.SUCCEEDED: frozenset({PaymentState.REVERSED, PaymentState.REFUNDED}),
    PaymentState.FAILED: frozenset(),
    PaymentState.REVERSED: frozenset(),
    PaymentState.REFUNDED: frozenset(),
}


class InvalidPaymentTransition(ValueError):
    pass


def can_transition(current: PaymentState, target: PaymentState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: PaymentState, target: PaymentState) -> None:
    if not can_transition(current, target):
        raise InvalidPaymentTransition(f"cannot move a payment from {current} to {target}")
