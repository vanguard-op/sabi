"""NFR-027: a mandate binds the user, amount, payee, and nonce, tamper-evidently."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sabi_payments.core.mandate import MandateRecord, MandateSigner

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def signed_record(signer: MandateSigner) -> MandateRecord:
    expires_at = (NOW + timedelta(minutes=5)).replace(microsecond=0)
    signature = signer.sign(
        user_id="user-1",
        amount=50_000,
        currency="NGN",
        payee="Lagos State Internal Revenue",
        payee_reference="TIN-123",
        nonce="nonce-1",
        expires_at=expires_at,
    )
    return MandateRecord(
        id="mandate-1",
        user_id="user-1",
        amount=50_000,
        currency="NGN",
        payee="Lagos State Internal Revenue",
        payee_reference="TIN-123",
        nonce="nonce-1",
        signature=signature,
        status="issued",
        expires_at=expires_at,
    )


def test_a_signed_mandate_verifies() -> None:
    signer = MandateSigner("test-key")
    assert signer.verify_signature(signed_record(signer)) is True


def test_a_changed_amount_breaks_the_signature() -> None:
    signer = MandateSigner("test-key")
    record = signed_record(signer)
    changed = replace(record, amount=99_000)
    assert signer.verify_signature(changed) is False


def test_a_different_key_does_not_verify() -> None:
    assert MandateSigner("other-key").verify_signature(
        signed_record(MandateSigner("test-key"))
    ) is (False)
