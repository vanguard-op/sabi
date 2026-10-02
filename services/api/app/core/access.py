"""Role and access policy.

Operator surfaces need an operator session, an assigned role, and a completed
MFA step; a passkey alone is not enough (NFR-020, operations.md). End-user
surfaces need an authenticated account owner. Policies are pure functions so
they are testable without a running app, and the FastAPI dependencies in
``app.api.deps`` are thin wrappers over them.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from app.core.errors import APIError, ErrorCode
from app.core.sessions import SessionData, SessionKind


class OperatorRole(StrEnum):
    PROVIDER_REVIEW_ANALYST = "provider_review_analyst"
    SUPPORT_OPERATIONS_AGENT = "support_operations_agent"
    RECONCILIATION_OFFICER = "reconciliation_officer"
    COMPLIANCE_PRIVACY_OFFICER = "compliance_privacy_officer"
    ADMINISTRATOR = "administrator"


def operator_has_access(
    session: SessionData,
    allowed_roles: Iterable[OperatorRole | str],
) -> bool:
    """True only for an MFA-verified operator holding one of the given roles."""
    if session.kind is not SessionKind.OPERATOR or not session.mfa_verified:
        return False
    allowed = {str(role) for role in allowed_roles}
    return session.role in allowed


def require_user(session: SessionData | None) -> SessionData:
    if session is None:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")
    return session


def require_operator(
    session: SessionData | None,
    allowed_roles: Iterable[OperatorRole | str],
) -> SessionData:
    if session is None:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")
    if not operator_has_access(session, allowed_roles):
        # One message for both a missing role and a missing MFA step so the
        # response does not reveal which control failed (least privilege).
        raise APIError(403, ErrorCode.FORBIDDEN, "This action needs an operator session with MFA.")
    return session
