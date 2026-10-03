"""Mandate verification for the payment module.

A mandate is verified against the exact amount, currency, payee, and user it was
issued for, and it must be unconsumed and unexpired. Any mismatch means the
amount or payee changed after authorisation, so execution is refused (NFR-027).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class MandateRecord:
    id: str
    user_id: str
    amount: int
    currency: str
    payee: str
    payee_reference: str | None
    nonce: str
    signature: str
    status: str
    expires_at: datetime


def verify_mandate(
    mandate: MandateRecord,
    *,
    user_id: str,
    amount: int,
    currency: str,
    payee: str,
    now: datetime | None = None,
) -> bool:
    moment = now or datetime.now(UTC)
    if mandate.status != "issued":
        return False
    if mandate.expires_at <= moment:
        return False
    if not mandate.signature:
        return False
    return (
        mandate.user_id == user_id
        and mandate.amount == amount
        and mandate.currency == currency
        and mandate.payee == payee
    )


# Same field set and order as the API's canonical message, so the module signs
# and verifies over the exact bytes the API defines (app.core.mandates). Kept
# duplicated rather than imported: the module never imports the primary app.
def _canonical_payload(
    *,
    user_id: str,
    amount: int,
    currency: str,
    payee: str,
    payee_reference: str | None,
    nonce: str,
    expires_at: datetime,
) -> bytes:
    stamp = expires_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    stamp = stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    payload = {
        "amount": amount,
        "currency": currency,
        "expiresAt": stamp,
        "nonce": nonce,
        "payee": payee,
        "payeeReference": payee_reference,
        "userId": user_id,
        "version": "sabi.payment-mandate.v1",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class MandateSigner:
    """Binds a mandate to its user, amount, payee, and nonce with a keyed digest.

    In production the user's passkey signs the mandate and this verifies against
    the enrolled public key; until that contract lands, the module signs with its
    own key so the binding is still tamper-evident (NFR-027).
    """

    def __init__(self, key: str) -> None:
        self._key = key.encode("utf-8")

    def sign(
        self,
        *,
        user_id: str,
        amount: int,
        currency: str,
        payee: str,
        payee_reference: str | None,
        nonce: str,
        expires_at: datetime,
    ) -> str:
        message = _canonical_payload(
            user_id=user_id,
            amount=amount,
            currency=currency,
            payee=payee,
            payee_reference=payee_reference,
            nonce=nonce,
            expires_at=expires_at,
        )
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def verify_signature(self, mandate: MandateRecord) -> bool:
        if not mandate.signature:
            return False
        expected = self.sign(
            user_id=mandate.user_id,
            amount=mandate.amount,
            currency=mandate.currency,
            payee=mandate.payee,
            payee_reference=mandate.payee_reference,
            nonce=mandate.nonce,
            expires_at=mandate.expires_at,
        )
        return hmac.compare_digest(expected, mandate.signature)


__all__ = ["MandateRecord", "MandateSigner", "verify_mandate"]
