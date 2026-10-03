"""Primary-store queries for receipts.

Reads are scoped to the account owner and ordered newest first with a keyset
cursor over ``(created_at, id)``, so a page boundary is stable while new
receipts are written (DELIVERY.md, cursor pagination).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import Receipt


def get_receipt(db: Session, receipt_id: str, *, user_id: str) -> Receipt | None:
    """A receipt by id, only when it belongs to ``user_id``."""
    return db.execute(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    ).scalar_one_or_none()


def list_receipts(
    db: Session,
    *,
    user_id: str,
    limit: int,
    before: tuple[datetime, str] | None = None,
    scan_limit: int | None = None,
) -> list[Receipt]:
    """The owner's receipts, newest first.

    ``before`` is the keyset cursor ``(created_at, id)``: only receipts strictly
    older than it are returned. ``scan_limit`` bounds how many rows a search may
    read in one pass; when it is set the window is ``scan_limit`` rather than
    ``limit`` so filtering can run before pagination.
    """
    stmt = select(Receipt).where(Receipt.user_id == user_id)
    if before is not None:
        created_at, receipt_id = before
        stmt = stmt.where(
            or_(
                Receipt.created_at < created_at,
                and_(Receipt.created_at == created_at, Receipt.id < receipt_id),
            )
        )
    window = scan_limit if scan_limit is not None else limit
    stmt = stmt.order_by(Receipt.created_at.desc(), Receipt.id.desc()).limit(window)
    return list(db.execute(stmt).scalars())


__all__ = ["get_receipt", "list_receipts"]
