"""Payment mandate binding.

A mandate authorises one exact money movement: a changed amount, currency, or
payee invalidates it, and a mandate is single-use and time-boxed (NFR-027). The
canonical message here is what the client signs and what the payment module
verifies against the stored intent, so both sides commit to the same bytes.
Execution itself lives in the isolated payment module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from app.core.time import to_rfc3339, utcnow


@dataclass(frozen=True, slots=True)
class MandateIntent:
    user_id: str
    amount: int
    currency: str
    payee: str
    payee_reference: str | None
    nonce: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("amount must be non-negative minor units")
        if not self.currency:
            raise ValueError("currency is required")


def canonical_message(intent: MandateIntent) -> bytes:
    """Deterministic bytes the user signs; order and formatting are fixed."""
    payload = {
        "amount": intent.amount,
        "currency": intent.currency,
        "expiresAt": to_rfc3339(intent.expires_at),
        "nonce": intent.nonce,
        "payee": intent.payee,
        "payeeReference": intent.payee_reference,
        "userId": intent.user_id,
        "version": "sabi.payment-mandate.v1",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def is_expired(intent: MandateIntent, now: datetime | None = None) -> bool:
    return intent.expires_at <= (now or utcnow())


def authorisation_matches(
    intent: MandateIntent,
    *,
    user_id: str,
    amount: int,
    currency: str,
    payee: str,
) -> bool:
    """Whether the stored intent still matches the authorisation presented.

    Any mismatch means the amount or payee changed after authorisation, so the
    payment must not execute (NFR-027).
    """
    return (
        intent.user_id == user_id
        and intent.amount == amount
        and intent.currency == currency
        and intent.payee == payee
    )
