"""Mandate verification for the payment module.

A mandate is verified against the exact amount, currency, payee, and user it was
issued for, and it must be unconsumed and unexpired. Any mismatch means the
amount or payee changed after authorisation, so execution is refused (NFR-027).
"""

from __future__ import annotations

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
