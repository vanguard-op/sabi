"""Wire models for catalogue discovery (C-010, C-011).

Field names follow the frozen contract: the ServiceSummary and search envelope
use the contract's own spelling, while the full Service record mirrors the
schema.md entity fields (camelCase). Timestamps render as RFC 3339 UTC.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.time import to_rfc3339
from app.db.models import Service


class ServiceSummary(BaseModel):
    """One ranked discovery result (C-010)."""

    service_id: str
    name: str
    collecting_body: str
    category: str
    known_amount: int | None
    currency: str
    status: str
    confidence: float


class SearchResponse(BaseModel):
    results: list[ServiceSummary]
    no_match: bool


class ServiceOut(BaseModel):
    """A full service record (C-011), mirroring schema.md ``Service``."""

    id: str
    type: str
    name: str
    collectingBody: str
    category: str
    aliases: list[str]
    providerId: str | None
    capabilityId: str | None
    knownAmount: int | None
    currency: str
    status: str
    refreshedAt: str | None
    createdAt: str


class ServiceResponse(BaseModel):
    service: ServiceOut


def serialize_service(service: Service) -> ServiceOut:
    return ServiceOut(
        id=service.id,
        type=service.type,
        name=service.name,
        collectingBody=service.collecting_body,
        category=service.category,
        aliases=list(service.aliases or []),
        providerId=service.provider_id,
        capabilityId=service.capability_id,
        knownAmount=service.known_amount,
        currency=service.currency,
        status=service.status,
        refreshedAt=to_rfc3339(service.refreshed_at) if service.refreshed_at else None,
        createdAt=to_rfc3339(service.created_at),
    )
