"""Primary-store queries the reconciliation jobs own.

The case table lives in the primary store and is read here for one reason: the
jobs must open a case only once per underlying condition, so a retried or
overlapping run does not multiply cases. The case workflow itself
(``app.cases``) is the writer of cases and stays untouched; this module reads
the same table to answer "is this condition already tracked?".

A case is matched by payment id and type. The job's exception types are a subset
of the schema's ``PaymentCase`` enum, so no mapping is needed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PaymentCase

# A case in one of these states is still being worked; a condition tracked by
# one is not reopened.
OPEN_CASE_STATUSES = ("open", "awaiting_provider", "escalated")


def find_open_case_for_payment(
    db: Session,
    payment_id: str,
    *,
    case_type: str,
) -> PaymentCase | None:
    """The oldest open case of ``case_type`` for the payment, if any."""
    return db.execute(
        select(PaymentCase)
        .where(
            PaymentCase.payment_id == payment_id,
            PaymentCase.type == case_type,
            PaymentCase.status.in_(OPEN_CASE_STATUSES),
        )
        .order_by(PaymentCase.id.asc())
        .limit(1)
    ).scalar_one_or_none()


__all__ = [
    "OPEN_CASE_STATUSES",
    "find_open_case_for_payment",
]
