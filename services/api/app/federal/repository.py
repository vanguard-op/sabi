"""Primary-store queries for the federal flows.

All reads are scoped to the record they belong to: a collection is read by its
service, an open reconciliation is read by the owner's payment. The service
record itself is the shared catalogue entity, read here rather than copied.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.time import utcnow
from app.db.models import PaymentCase, Service
from app.federal.models import FederalCollection

# A reconciliation case in one of these states is still being worked; a second
# reconcile request for the same payment is a duplicate (FEAT-006).
OPEN_CASE_STATUSES = ("open", "awaiting_provider", "escalated")


def get_service(db: Session, service_id: str) -> Service | None:
    return db.get(Service, service_id)


def get_collection(db: Session, service_id: str) -> FederalCollection | None:
    return db.execute(
        select(FederalCollection).where(FederalCollection.service_id == service_id)
    ).scalar_one_or_none()


def find_open_reconciliation(db: Session, payment_id: str) -> PaymentCase | None:
    """An open reconciliation case for a payment, if one exists.

    Reconciliation against the agency record opens a ``receipt_missing`` case
    (operations.md, "Reconciliation operations"); opening a second one for the
    same payment is a conflict.
    """
    return db.execute(
        select(PaymentCase)
        .where(
            PaymentCase.payment_id == payment_id,
            PaymentCase.type == "receipt_missing",
            PaymentCase.status.in_(OPEN_CASE_STATUSES),
        )
        .order_by(PaymentCase.id.asc())
        .limit(1)
    ).scalar_one_or_none()


def create_reconciliation_case(
    db: Session,
    *,
    payment_id: str,
    user_id: str,
    reason: str,
    assignee_role: str,
) -> PaymentCase:
    """Open a reconciliation case for a federal payment.

    ``reason`` is user-supplied and may carry personal data; it is accepted for
    the contract but not copied onto the case row, matching how a dispute reason
    is handled (app.cases.service), so it never lands in an unencrypted column.
    """
    now = utcnow()
    case = PaymentCase(
        id=new_id(),
        payment_id=payment_id,
        user_id=user_id,
        type="receipt_missing",
        status="open",
        assignee_role=assignee_role,
        opened_at=now,
        updated_at=now,
    )
    db.add(case)
    db.flush()
    return case


__all__ = [
    "OPEN_CASE_STATUSES",
    "create_reconciliation_case",
    "find_open_reconciliation",
    "get_collection",
    "get_service",
]
