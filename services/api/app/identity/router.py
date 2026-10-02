"""Identity and account endpoints (C-001..C-008).

Paths are declared without the ``/v1`` prefix; the application factory mounts
the router under ``/v1``. Request and response shapes, status codes, and error
codes are the frozen client contract.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    current_user,
    get_audit_log,
    get_rate_limiter,
    get_session_manager,
    get_settings,
)
from app.core.audit import AuditLog
from app.core.config import Settings
from app.core.errors import APIError, ErrorCode
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData, SessionManager
from app.db.models import User
from app.db.session import get_db
from app.identity import service
from app.identity.challenges import ChallengeStore, get_challenge_store
from app.identity.schemas import (
    AccountMeResponse,
    ChannelLinkAccountOut,
    ChannelLinkCreateRequest,
    ChannelLinkOut,
    LoginOptionsResponse,
    LoginVerifyRequest,
    LoginVerifyResponse,
    RecoveryRegenerateResponse,
    RecoveryVerifyRequest,
    RecoveryVerifyResponse,
    RegisterOptionsRequest,
    RegisterVerifyRequest,
    RegisterVerifyResponse,
    RegistrationOptionsResponse,
    UserOut,
)

router = APIRouter(tags=["identity"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_db)]
ChallengeStoreDep = Annotated[ChallengeStore, Depends(get_challenge_store)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
AuditDep = Annotated[AuditLog, Depends(get_audit_log)]
AccountOwnerDep = Annotated[SessionData, Depends(current_user)]


def _enforce_rate_limit(request: Request, limiter: RateLimiter, scope: str) -> None:
    client = request.client.host if request.client else "unknown"
    limiter.check(f"identity:{scope}:{client}")


def _account_response(user: User, links: list) -> AccountMeResponse:
    return AccountMeResponse(
        id=user.id,
        display_name=user.display_name,
        locale=user.locale,
        preferred_channel=user.preferred_channel,
        kyc_status=user.kyc_status,
        account_status=user.account_status,
        channel_links=[ChannelLinkAccountOut.model_validate(link) for link in links],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/auth/register/options", response_model=RegistrationOptionsResponse)
def register_options(
    payload: RegisterOptionsRequest,
    request: Request,
    settings: SettingsDep,
    store: ChallengeStoreDep,
    limiter: LimiterDep,
) -> RegistrationOptionsResponse:
    _enforce_rate_limit(request, limiter, "register-options")
    challenge_id, public_key = service.start_registration(settings, store, locale=payload.locale)
    return RegistrationOptionsResponse(challenge_id=challenge_id, public_key=public_key)


@router.post("/auth/register/verify", response_model=RegisterVerifyResponse, status_code=201)
def register_verify(
    payload: RegisterVerifyRequest,
    response: Response,
    db: SessionDep,
    settings: SettingsDep,
    store: ChallengeStoreDep,
    manager: SessionManagerDep,
    audit: AuditDep,
) -> RegisterVerifyResponse:
    user, recovery_code = service.finish_registration(
        db,
        settings,
        store,
        challenge_id=payload.challenge_id,
        credential=payload.credential,
        display_name=payload.display_name,
        locale=payload.locale,
    )
    token, _ = manager.issue(user_id=user.id)
    manager.set_cookie(response, token)
    audit.append(
        "identity.register",
        actor_id=user.id,
        target=user.id,
        detail={"locale": user.locale},
    )
    return RegisterVerifyResponse(user=UserOut.model_validate(user), recovery_code=recovery_code)


@router.post("/auth/login/options", response_model=LoginOptionsResponse)
def login_options(
    request: Request,
    settings: SettingsDep,
    store: ChallengeStoreDep,
    limiter: LimiterDep,
) -> LoginOptionsResponse:
    _enforce_rate_limit(request, limiter, "login-options")
    challenge_id, public_key = service.start_authentication(settings, store)
    return LoginOptionsResponse(challenge_id=challenge_id, public_key=public_key)


@router.post("/auth/login/verify", response_model=LoginVerifyResponse)
def login_verify(
    payload: LoginVerifyRequest,
    response: Response,
    db: SessionDep,
    settings: SettingsDep,
    store: ChallengeStoreDep,
    manager: SessionManagerDep,
    audit: AuditDep,
) -> LoginVerifyResponse:
    user = service.finish_authentication(
        db,
        settings,
        store,
        challenge_id=payload.challenge_id,
        credential=payload.credential,
    )
    token, _ = manager.issue(user_id=user.id)
    manager.set_cookie(response, token)
    audit.append("identity.login", actor_id=user.id, target=user.id)
    return LoginVerifyResponse(user=UserOut.model_validate(user))


@router.post("/auth/recovery/verify", response_model=RecoveryVerifyResponse)
def recovery_verify(
    payload: RecoveryVerifyRequest,
    response: Response,
    db: SessionDep,
    settings: SettingsDep,
    manager: SessionManagerDep,
    audit: AuditDep,
) -> RecoveryVerifyResponse:
    user = service.verify_recovery(db, settings, recovery_code=payload.recovery_code)
    token, _ = manager.issue(user_id=user.id)
    manager.set_cookie(response, token)
    audit.append("identity.recovery.verify", actor_id=user.id, target=user.id)
    return RecoveryVerifyResponse(user=UserOut.model_validate(user), must_enrol_passkey=True)


@router.post("/auth/recovery/regenerate", response_model=RecoveryRegenerateResponse)
def recovery_regenerate(
    db: SessionDep,
    settings: SettingsDep,
    audit: AuditDep,
    session: AccountOwnerDep,
) -> RecoveryRegenerateResponse:
    code = service.regenerate_recovery(db, settings, user_id=session.user_id)
    audit.append(
        "identity.recovery.regenerate",
        actor_id=session.user_id,
        target=session.user_id,
    )
    return RecoveryRegenerateResponse(recovery_code=code)


@router.post("/auth/channel-links", response_model=ChannelLinkOut, status_code=201)
def create_channel_link(
    payload: ChannelLinkCreateRequest,
    db: SessionDep,
    audit: AuditDep,
    session: AccountOwnerDep,
) -> ChannelLinkOut:
    link, owner = service.create_channel_link(
        db,
        user_id=session.user_id,
        channel=payload.channel,
        address=payload.address,
    )
    if owner is not None:
        service.notify_channel_conflict(db, owner=owner)
        # Persist the owner notice before the rejection unwinds the request; the
        # request session rolls back on the raised error.
        db.commit()
        audit.append(
            "identity.channel_link_conflict",
            actor_id=session.user_id,
            target=owner.id,
            detail={"channel": payload.channel},
        )
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "That number is already linked to another account. We have let the owner know.",
        )
    audit.append(
        "identity.channel_link",
        actor_id=session.user_id,
        target=link.id,
        detail={"channel": payload.channel},
    )
    return ChannelLinkOut.model_validate(link)


@router.get("/account/me", response_model=AccountMeResponse)
def account_me(db: SessionDep, session: AccountOwnerDep) -> AccountMeResponse:
    user, links = service.get_account(db, user_id=session.user_id)
    return _account_response(user, links)
