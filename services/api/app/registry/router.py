"""Provider registry HTTP surface (C-013–C-016).

Paths are declared without the ``/v1`` prefix; the app factory mounts the router
under it (DELIVERY.md, conventions). Operator endpoints require an operator
session with MFA and the provider review analyst role (C-013, C-014, C-016).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    current_user,
    get_audit_log,
    require_operator_role,
)
from app.core.access import OperatorRole
from app.core.audit import AuditLog
from app.core.sessions import SessionData
from app.db.session import get_db
from app.registry import service
from app.registry.schemas import (
    CapabilityCreateRequest,
    CapabilityDetailResponse,
    CapabilityResponse,
    CapabilityReviewRequest,
    ProviderCreateRequest,
    ProviderResponse,
)

router = APIRouter(tags=["registry"])

ReviewAnalystSession = Annotated[
    SessionData,
    Depends(
        require_operator_role([OperatorRole.PROVIDER_REVIEW_ANALYST, OperatorRole.ADMINISTRATOR])
    ),
]
InternalSession = Annotated[SessionData, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]
Audit = Annotated[AuditLog, Depends(get_audit_log)]


@router.post("/providers", status_code=201, response_model=ProviderResponse)
def create_provider(
    request: ProviderCreateRequest,
    session: ReviewAnalystSession,
    db: DbSession,
    audit: Audit,
) -> dict:
    provider = service.create_provider(db, audit, actor=session, request=request)
    return {"provider": service.provider_payload(provider)}


@router.post(
    "/providers/{providerId}/capabilities",
    status_code=201,
    response_model=CapabilityResponse,
)
def create_capability(
    providerId: str,  # noqa: N803  (contract path placeholder is camelCase)
    request: CapabilityCreateRequest,
    session: ReviewAnalystSession,
    db: DbSession,
    audit: Audit,
) -> dict:
    capability = service.create_capability(
        db, audit, actor=session, provider_id=providerId, request=request
    )
    return {"capability": service.capability_payload(capability)}


@router.get("/capabilities/{capabilityId}", response_model=CapabilityDetailResponse)
def get_capability(
    capabilityId: str,  # noqa: N803  (contract path placeholder is camelCase)
    _: InternalSession,
    db: DbSession,
) -> dict:
    capability = service.get_capability_or_404(db, capabilityId)
    return {
        "capability": service.capability_payload(capability),
        "healthStatus": capability.health_status,
    }


@router.post("/capabilities/{capabilityId}/review", response_model=CapabilityResponse)
def review_capability(
    capabilityId: str,  # noqa: N803  (contract path placeholder is camelCase)
    request: CapabilityReviewRequest,
    session: ReviewAnalystSession,
    db: DbSession,
    audit: Audit,
) -> dict:
    capability = service.review_capability(
        db,
        audit,
        actor=session,
        capability_id=capabilityId,
        decision=request.decision,
        reason=request.reason,
        schema_version=request.schema_version,
    )
    return {"capability": service.capability_payload(capability)}
