"""Primary-store queries for the service catalogue."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Service

# Discovery offers active records and keeps transiently unavailable ones visible
# so the client can explain why they cannot be paid right now; retired records
# are withdrawn and never offered (FEAT-004, FEAT-012).
_VISIBLE_STATUSES = ("active", "unavailable")


def candidates(db: Session, category: str | None = None) -> list[Service]:
    stmt = select(Service).where(Service.status.in_(_VISIBLE_STATUSES))
    if category and category.strip():
        stmt = stmt.where(func.lower(Service.category) == category.strip().casefold())
    stmt = stmt.order_by(Service.name)
    return list(db.execute(stmt).scalars())


def get(db: Session, service_id: str) -> Service | None:
    return db.get(Service, service_id)
