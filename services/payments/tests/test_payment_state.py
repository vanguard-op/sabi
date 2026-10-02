import pytest

from sabi_payments.core.state import (
    ALLOWED_TRANSITIONS,
    InvalidPaymentTransition,
    PaymentState,
    assert_transition,
    can_transition,
)


def test_happy_path_transitions() -> None:
    assert can_transition(PaymentState.INITIATED, PaymentState.AUTHORIZED)
    assert can_transition(PaymentState.AUTHORIZED, PaymentState.SUCCEEDED)
    assert can_transition(PaymentState.SUCCEEDED, PaymentState.REFUNDED)


def test_unknown_outcome_is_held_pending_not_retried() -> None:
    assert can_transition(PaymentState.PENDING, PaymentState.SUCCEEDED)
    assert can_transition(PaymentState.PENDING, PaymentState.FAILED)
    assert not can_transition(PaymentState.PENDING, PaymentState.AUTHORIZED)


def test_terminal_states_do_not_move_forward() -> None:
    for state in (PaymentState.FAILED, PaymentState.REVERSED, PaymentState.REFUNDED):
        assert ALLOWED_TRANSITIONS[state] == frozenset()


def test_invalid_transition_raises() -> None:
    with pytest.raises(InvalidPaymentTransition):
        assert_transition(PaymentState.FAILED, PaymentState.SUCCEEDED)
