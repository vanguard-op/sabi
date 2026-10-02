"""Shared FastAPI dependencies.

These are thin adapters over the pure policy in ``app.core``; the policy holds
the rules, the dependencies fetch state from the request.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import Depends, Request

from app.core.access import OperatorRole, require_operator, require_user
from app.core.audit import AuditLog
from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.sessions import SessionData, SessionManager


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_audit_log(request: Request) -> AuditLog:
    return request.app.state.audit_log


def get_current_session(
    request: Request,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionData | None:
    token = request.cookies.get(manager.settings.session_cookie_name)
    if not token:
        return None
    return manager.read(token)


def current_user(session: SessionData | None = Depends(get_current_session)) -> SessionData:
    return require_user(session)


def require_operator_role(
    allowed_roles: Iterable[OperatorRole | str],
):
    """Dependency factory: an operator session with MFA and one of the roles."""

    def dependency(
        session: SessionData | None = Depends(get_current_session),
    ) -> SessionData:
        return require_operator(session, allowed_roles)

    return dependency
