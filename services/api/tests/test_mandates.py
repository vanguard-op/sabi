from datetime import timedelta

import pytest

from app.core.mandates import (
    MandateIntent,
    authorisation_matches,
    canonical_message,
    is_expired,
)
from app.core.time import utcnow


def make_intent(amount: int = 50_000) -> MandateIntent:
    return MandateIntent(
        user_id="user-1",
        amount=amount,
        currency="NGN",
        payee="Lagos State Internal Revenue",
        payee_reference="TIN-123",
        nonce="nonce-1",
        expires_at=utcnow() + timedelta(minutes=5),
    )


def test_canonical_message_is_deterministic() -> None:
    intent = make_intent()
    assert canonical_message(intent) == canonical_message(intent)


def test_changing_the_amount_changes_the_signed_message() -> None:
    assert canonical_message(make_intent(amount=1)) != canonical_message(make_intent(amount=2))


def test_authorisation_binds_user_amount_currency_and_payee() -> None:
    intent = make_intent()
    assert authorisation_matches(
        intent,
        user_id="user-1",
        amount=50_000,
        currency="NGN",
        payee="Lagos State Internal Revenue",
    )
    assert not authorisation_matches(
        intent,
        user_id="user-1",
        amount=99_000,
        currency="NGN",
        payee="Lagos State Internal Revenue",
    )
    assert not authorisation_matches(
        intent, user_id="user-1", amount=50_000, currency="NGN", payee="Someone else"
    )


def test_expiry_is_enforced() -> None:
    intent = make_intent()
    assert is_expired(intent, intent.expires_at) is True
    assert is_expired(intent, intent.expires_at - timedelta(seconds=1)) is False


def test_negative_amount_is_rejected() -> None:
    with pytest.raises(ValueError):
        make_intent(amount=-1)
