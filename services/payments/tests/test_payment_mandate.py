from datetime import UTC, datetime, timedelta

from sabi_payments.core.mandate import MandateRecord, verify_mandate

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def make_mandate(**overrides: object) -> MandateRecord:
    values: dict[str, object] = {
        "id": "mandate-1",
        "user_id": "user-1",
        "amount": 50_000,
        "currency": "NGN",
        "payee": "Lagos State Internal Revenue",
        "payee_reference": "TIN-123",
        "nonce": "nonce-1",
        "signature": "signed-blob",
        "status": "issued",
        "expires_at": NOW + timedelta(minutes=5),
    }
    values.update(overrides)
    return MandateRecord(**values)  # type: ignore[arg-type]


def verify(mandate: MandateRecord, **overrides: object) -> bool:
    args: dict[str, object] = {
        "user_id": "user-1",
        "amount": 50_000,
        "currency": "NGN",
        "payee": "Lagos State Internal Revenue",
    }
    args.update(overrides)
    return verify_mandate(mandate, now=NOW, **args)  # type: ignore[arg-type]


def test_a_fresh_matching_mandate_verifies() -> None:
    assert verify(make_mandate()) is True


def test_changed_amount_or_payee_is_refused() -> None:
    assert verify(make_mandate(), amount=99_000) is False
    assert verify(make_mandate(), payee="Someone else") is False


def test_consumed_or_expired_mandate_is_refused() -> None:
    assert verify(make_mandate(status="consumed")) is False
    assert verify(make_mandate(expires_at=NOW)) is False


def test_missing_signature_is_refused() -> None:
    assert verify(make_mandate(signature="")) is False
