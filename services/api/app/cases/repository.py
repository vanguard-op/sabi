"""Primary-store queries for payment cases.

Cases are scoped to their owner: every read and write filters on ``user_id``, so
one user's case id can never expose another user's payment (least privilege,
operations.md). ``PaymentCase.id`` is a time-ordered UUIDv7, which makes the id
itself a stable keyset cursor for the newest-first list.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.time import utcnow
from app.db.models import PaymentCase

# A refund case in one of these states is still being worked; a second refund
# request for the same payment is a duplicate (FEAT-009, operations.md).
OPEN_CASE_STATUSES = ("open", "awaiting_provider", "escalated")


def get_case(db: Session, case_id: str, *, user_id: str | None = None) -> PaymentCase | None:
    stmt = select(PaymentCase).where(PaymentCase.id == case_id)
    if user_id is not None:
        stmt = stmt.where(PaymentCase.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def list_cases(
    db: Session,
    *,
    user_id: str,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[PaymentCase], str | None]:
    """Newest-first page of the user's cases, with the next keyset cursor."""
    stmt = select(PaymentCase).where(PaymentCase.user_id == user_id)
    if status is not None:
        stmt = stmt.where(PaymentCase.status == status)
    if cursor:
        # Newest first, so the next page holds ids below the cursor.
        stmt = stmt.where(PaymentCase.id < cursor)
    stmt = stmt.order_by(PaymentCase.id.desc()).limit(limit + 1)

    rows = list(db.execute(stmt).scalars())
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1].id if has_more and page else None
    return page, next_cursor


def find_dispute_for_payment(db: Session, payment_id: str) -> PaymentCase | None:
    return db.execute(
        select(PaymentCase)
        .where(PaymentCase.payment_id == payment_id, PaymentCase.type == "disputed")
        .order_by(PaymentCase.id.asc())
        .limit(1)
    ).scalar_one_or_none()


def find_open_refund_for_payment(db: Session, payment_id: str) -> PaymentCase | None:
    return db.execute(
        select(PaymentCase)
        .where(
            PaymentCase.payment_id == payment_id,
            PaymentCase.type == "refund",
            PaymentCase.status.in_(OPEN_CASE_STATUSES),
        )
        .order_by(PaymentCase.id.asc())
        .limit(1)
    ).scalar_one_or_none()


def create_case(
    db: Session,
    *,
    payment_id: str,
    user_id: str,
    case_type: str,
    status: str,
    assignee_role: str,
) -> PaymentCase:
    now = utcnow()
    case = PaymentCase(
        id=new_id(),
        payment_id=payment_id,
        user_id=user_id,
        type=case_type,
        status=status,
        assignee_role=assignee_role,
        opened_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()
    return case


__all__ = [
    "OPEN_CASE_STATUSES",
    "create_case",
    "find_dispute_for_payment",
    "find_open_refund_for_payment",
    "get_case",
    "list_cases",
]
