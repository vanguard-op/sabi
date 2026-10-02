"""Primary-store queries for the provider registry.

All reads are parameterised through SQLAlchemy; nothing here builds SQL by
string. Name lookups are case-insensitive so "MTN" and "mtn" are the same
provider and the same capability.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Capability, Provider, Service

# Capabilities that still occupy a name or a service. A withdrawn capability is
# history and does not block a corrected resubmission (FEAT-012).
LIVE_CAPABILITY_STATUSES = ("pending", "active", "quarantined")


def get_provider(db: Session, provider_id: str) -> Provider | None:
    return db.get(Provider, provider_id)


def get_service(db: Session, service_id: str) -> Service | None:
    return db.get(Service, service_id)


def get_capability(db: Session, capability_id: str) -> Capability | None:
    return db.get(Capability, capability_id)


def find_provider_by_name(db: Session, name: str) -> Provider | None:
    return db.execute(
        select(Provider).where(func.lower(Provider.name) == name.lower())
    ).scalar_one_or_none()


def find_live_capability_by_name(db: Session, provider_id: str, name: str) -> Capability | None:
    return db.execute(
        select(Capability).where(
            Capability.provider_id == provider_id,
            func.lower(Capability.name) == name.lower(),
            Capability.status.in_(LIVE_CAPABILITY_STATUSES),
        )
    ).scalar_one_or_none()


def find_live_capability_by_service(db: Session, service_id: str) -> Capability | None:
    return db.execute(
        select(Capability)
        .where(
            Capability.service_id == service_id,
            Capability.status.in_(LIVE_CAPABILITY_STATUSES),
        )
        .order_by(Capability.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


def list_provider_capabilities(db: Session, provider_id: str) -> list[Capability]:
    return list(
        db.execute(
            select(Capability)
            .where(Capability.provider_id == provider_id)
            .order_by(Capability.created_at.asc())
        ).scalars()
    )
