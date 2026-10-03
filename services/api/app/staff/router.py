"""Staff authentication endpoints (C-039, C-040).

Paths are declared without the ``/v1`` prefix; the application factory mounts the
router under it (DELIVERY.md, conventions). This surface issues only operator
sessions and is wholly separate from the end-user passkey flow (C-001..C-008):
no impersonation, no shared accounts, MFA on every session.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import (
    get_audit_log,
    get_current_session,
    get_rate_limiter,
    get_session_manager,
    get_settings,
)
from app.core.audit import AuditLog
from app.core.config import Settings
from app.core.errors import APIError, ErrorCode
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData, SessionKind, SessionManager
from app.db.session import get_db
from app.staff import service
from app.staff.schemas import (
    StaffLoginRequest,
    StaffLoginResponse,
    StaffOut,
    StaffSessionResponse,
)

router = APIRouter(tags=["staff"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]
AuditDep = Annotated[AuditLog, Depends(get_audit_log)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
ManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
CurrentSessionDep = Annotated[SessionData | None, Depends(get_current_session)]


def _require_staff_session(session: SessionData | None) -> SessionData:
    """Any operator session may sign out, even one still to enrol its factor."""
    if session is None or session.kind is not SessionKind.OPERATOR:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")
    return session


def _enforce_rate_limit(request: Request, limiter: RateLimiter) -> None:
    client = request.client.host if request.client else "unknown"
    limiter.check(f"staff:login:{client}")


def _parse_login(body: dict[str, Any]) -> StaffLoginRequest:
    try:
        return StaffLoginRequest.model_validate(body)
    except ValidationError as exc:
        # C-039 returns 400 for invalid input; strip values so a submitted
        # password or code never travels back in the response (NFR-024).
        fields = [
            {"loc": [str(part) for part in error.get("loc", [])], "type": error.get("type")}
            for error in exc.errors()
        ]
        raise APIError(
            400,
            ErrorCode.INVALID_REQUEST,
            "Enter your email, password, and six-digit code.",
            {"fields": fields},
        ) from exc


@router.post("/staff/auth/login", response_model=StaffLoginResponse)
def staff_login(
    request: Request,
    response: Response,
    body: Annotated[dict[str, Any], Body()],
    db: DbDep,
    settings: SettingsDep,
    manager: ManagerDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> StaffLoginResponse:
    _enforce_rate_limit(request, limiter)
    payload = _parse_login(body)
    account = service.authenticate(db, settings, audit, request=payload)

    must_enrol = account.totp_secret is None
    token, _ = manager.issue(
        user_id=account.id,
        kind=SessionKind.OPERATOR,
        role=account.role,
        mfa_verified=not must_enrol,
    )
    manager.set_cookie(response, token)
    return StaffLoginResponse(
        staff=StaffOut(staff_id=account.id, email=account.email, role=account.role),
        must_enrol_mfa=must_enrol,
    )


@router.get("/staff/auth/session", response_model=StaffSessionResponse)
def staff_session(db: DbDep, session: CurrentSessionDep) -> StaffSessionResponse:
    """Confirm the operator session and return the current identity.

    The console calls this on load: the HttpOnly cookie is the authority, so a
    mirrored identity that outlives the cookie must not show an operator as
    signed in (C-039).
    """
    staff_session = _require_staff_session(session)
    account = service.find_by_id(db, staff_session.user_id)
    if account is None:
        # The account was removed while the session lived: treat as unauthorised
        # rather than reporting an identity that no longer exists.
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")
    return StaffSessionResponse(
        staff=StaffOut(
            staff_id=account.id,
            email=account.email,
            role=account.role,
        )
    )


@router.post("/staff/auth/logout", status_code=204)
def staff_logout(
    db: DbDep,
    audit: AuditDep,
    manager: ManagerDep,
    response: Response,
    session: CurrentSessionDep,
) -> Response:
    staff_session = _require_staff_session(session)
    service.logout(db, audit, staff_id=staff_session.user_id)
    manager.revoke(staff_session.id)
    manager.clear_cookie(response)
    response.status_code = 204
    return response
