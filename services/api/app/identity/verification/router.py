"""Identity verification endpoints (C-020..C-022).

Paths are declared without the ``/v1`` prefix; the application factory mounts the
router under it (DELIVERY.md, conventions). Every endpoint requires an
authenticated account owner. The provider port is read from ``app.state`` so the
isolated stub is substituted in development and tests without a code path in
production that could mark an account verified on its own.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_audit_log
from app.core.audit import AuditLog
from app.core.sessions import SessionData
from app.db.session import get_db
from app.identity.verification import service
from app.identity.verification.provider import (
    IdentityProvider,
    UnavailableIdentityProvider,
)
from app.identity.verification.schemas import (
    AccountVerificationResponse,
    VerificationCreatedResponse,
    VerificationCreateRequest,
    VerificationDetailResponse,
)

router = APIRouter(tags=["identity"])

DbSession = Annotated[Session, Depends(get_db)]
Audit = Annotated[AuditLog, Depends(get_audit_log)]
AccountOwner = Annotated[SessionData, Depends(current_user)]


def get_identity_provider(request: Request) -> IdentityProvider:
    provider = getattr(request.app.state, "identity_provider", None)
    return provider if provider is not None else UnavailableIdentityProvider()


Provider = Annotated[IdentityProvider, Depends(get_identity_provider)]


@router.post("/identity/verifications", status_code=202, response_model=VerificationCreatedResponse)
def create_verification(
    payload: VerificationCreateRequest,
    db: DbSession,
    audit: Audit,
    session: AccountOwner,
    provider: Provider,
) -> VerificationCreatedResponse:
    record, _ = service.start_verification(
        db,
        audit,
        actor=session,
        method=payload.method,
        identifier=payload.identifier,
        provider=provider,
    )
    return VerificationCreatedResponse(verification_id=record.id, status=record.status)


@router.get(
    "/identity/verifications/{verificationId}",
    response_model=VerificationDetailResponse,
)
def get_verification(
    verificationId: str,  # noqa: N803  (contract path placeholder is camelCase)
    db: DbSession,
    session: AccountOwner,
) -> VerificationDetailResponse:
    record = service.get_verification(db, user_id=session.user_id, verification_id=verificationId)
    return VerificationDetailResponse.model_validate(
        service.detail_payload(db, user_id=session.user_id, record=record)
    )


@router.get("/account/verification", response_model=AccountVerificationResponse)
def account_verification(db: DbSession, session: AccountOwner) -> AccountVerificationResponse:
    state = service.get_account_verification(db, user_id=session.user_id)
    return AccountVerificationResponse(
        kyc_status=state.kyc_status,
        method=state.method,
        can_correct=state.can_correct,
    )
