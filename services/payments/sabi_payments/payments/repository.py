"""Payment-store reads and writes.

All access to the isolated payment store goes through these helpers so the
service layer holds the rules and this module holds the queries. Rows are scoped
by ``user_id`` everywhere a client asks for something: a guessed identifier must
never expose another account's payment.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from sabi_payments.db.models import Payment, PaymentEvent, PaymentMandate, PaymentMethod


def get_payment(session: Session, payment_id: str) -> Payment | None:
    return session.get(Payment, payment_id)


def get_owned_payment(session: Session, payment_id: str, user_id: str) -> Payment | None:
    payment = session.get(Payment, payment_id)
    if payment is None or payment.user_id != user_id:
        return None
    return payment


def get_mandate(session: Session, mandate_id: str) -> PaymentMandate | None:
    return session.get(PaymentMandate, mandate_id)


def get_owned_method(session: Session, method_id: str, user_id: str) -> PaymentMethod | None:
    method = session.get(PaymentMethod, method_id)
    if method is None or method.user_id != user_id:
        return None
    return method


def find_by_authorise_key(session: Session, idempotency_key: str) -> Payment | None:
    """A payment already created with this authorisation key, if any."""
    return session.execute(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    ).scalar_one_or_none()


def find_by_execute_key(session: Session, idempotency_key: str) -> Payment | None:
    return find_by_authorise_key(session, idempotency_key)


def list_for_user(
    session: Session,
    *,
    user_id: str,
    status: str | None,
    cursor_created_at: datetime | None,
    cursor_id: str | None,
    limit: int,
) -> list[Payment]:
    """One page newest-first; a tie on ``created_at`` is broken by ``id``."""
    query: Select = select(Payment).where(Payment.user_id == user_id)
    if status is not None:
        query = query.where(Payment.status == status)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            (Payment.created_at < cursor_created_at)
            | ((Payment.created_at == cursor_created_at) & (Payment.id < cursor_id))
        )
    query = query.order_by(Payment.created_at.desc(), Payment.id.desc()).limit(limit + 1)
    return list(session.execute(query).scalars())


def count_for_user(session: Session, *, user_id: str, status: str | None) -> int:
    query = select(func.count()).select_from(Payment).where(Payment.user_id == user_id)
    if status is not None:
        query = query.where(Payment.status == status)
    return int(session.execute(query).scalar_one())


def add_event(
    session: Session,
    *,
    payment_id: str,
    status: str,
    actor: str,
    detail: str | None = None,
) -> PaymentEvent:
    """Append a state-change event; the case timeline reads these in order."""
    from sabi_payments.core.ids import new_id
    from sabi_payments.db.base import utcnow

    event = PaymentEvent(
        id=new_id(),
        payment_id=payment_id,
        status=status,
        actor=actor,
        detail=detail,
        occurred_at=utcnow(),
    )
    session.add(event)
    return event


__all__ = [
    "add_event",
    "count_for_user",
    "find_by_authorise_key",
    "find_by_execute_key",
    "get_mandate",
    "get_owned_method",
    "get_owned_payment",
    "get_payment",
    "list_for_user",
]
