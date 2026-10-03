"""Privileged-action audit view endpoints (C-041-C-043).

Paths are declared without the ``/v1`` prefix; the application factory mounts the
router under it (DELIVERY.md, conventions). Every route needs an operator session
with MFA: the read is open to the compliance and privacy officer or an
administrator, while closing a finding and exporting an extract are held to the
compliance and privacy officer alone (operations-console.md, "Permitted role").

The view reads the append-only log and never writes to it; the two privileged
actions it performs, closing a finding and requesting an export, are themselves
appended to the log by the service layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_audit_log, get_rate_limiter, require_operator_role
from app.audit import service
from app.audit.schemas import (
    DEFAULT_LIMIT,
    AuditListResponse,
    CloseFindingRequest,
    CloseFindingResponse,
    ExportRequest,
    ExportResponse,
)
from app.core.access import OperatorRole
from app.core.audit import AuditLog
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData
from app.db.session import get_db

router = APIRouter(tags=["audit"])

AuditReviewer = Annotated[
    SessionData,
    Depends(
        require_operator_role([OperatorRole.COMPLIANCE_PRIVACY_OFFICER, OperatorRole.ADMINISTRATOR])
    ),
]
ComplianceOfficer = Annotated[
    SessionData,
    Depends(require_operator_role([OperatorRole.COMPLIANCE_PRIVACY_OFFICER])),
]
DbSession = Annotated[Session, Depends(get_db)]
Audit = Annotated[AuditLog, Depends(get_audit_log)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


@router.get("/staff/audit", response_model=AuditListResponse)
def read_audit(
    session: AuditReviewer,
    audit: Audit,
    limiter: Limiter,
    actor: str | None = Query(default=None),
    role: str | None = Query(default=None),
    target: str | None = Query(default=None),
    action: str | None = Query(default=None),
    range_from: str | None = Query(default=None, alias="from"),
    range_to: str | None = Query(default=None, alias="to"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT),
) -> AuditListResponse:
    limiter.check(f"staff:audit:{session.user_id}")
    return service.read_audit(
        audit,
        actor=actor,
        role=role,
        target=target,
        action=action,
        range_from=range_from,
        range_to=range_to,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/staff/audit/findings/{findingsId}/close",
    response_model=CloseFindingResponse,
)
def close_finding(
    findingsId: str,  # noqa: N803  (contract path placeholder is camelCase)
    request: CloseFindingRequest,
    session: ComplianceOfficer,
    db: DbSession,
    audit: Audit,
) -> CloseFindingResponse:
    return service.close_finding(
        db,
        audit,
        actor=session,
        findings_id=findingsId,
        resolution=request.resolution,
    )


@router.post("/staff/audit/export", status_code=202, response_model=ExportResponse)
def export_audit(
    request: ExportRequest,
    session: ComplianceOfficer,
    db: DbSession,
    audit: Audit,
) -> ExportResponse:
    return service.request_export(
        db,
        audit,
        actor=session,
        range_from=request.range_from,
        range_to=request.range_to,
        export_format=request.format,
    )
