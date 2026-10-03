"""Staff authentication service (C-039, C-040).

The router stays thin; this layer holds the rules and raises the contract's
errors. Password and TOTP material never leaves this module: only a hash or a
constant-time comparison result does, and no secret is written to an audit entry.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import OperatorRole
from app.core.audit import AuditLog
from app.core.config import Settings
from app.core.errors import APIError, ErrorCode
from app.core.security import hash_secret, verify_secret
from app.core.time import utcnow
from app.staff import totp
from app.staff.models import StaffAccount
from app.staff.schemas import StaffLoginRequest

# Repeated failures lock the account for a cooling-off period (C-039, 423).
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60

# A fixed, well-formed Argon2id hash verified when the email is unknown, so the
# response time does not reveal whether an account exists.
_DUMMY_HASH = hash_secret("not-a-real-password", "staff-timing-equaliser")


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _pepper(settings: Settings) -> str:
    return settings.recovery_code_pepper.get_secret_value()


def _not_permitted() -> APIError:
    return APIError(403, ErrorCode.FORBIDDEN, "This account cannot sign in to the console.")


def _invalid_credentials() -> APIError:
    return APIError(401, ErrorCode.UNAUTHENTICATED, "That email, password, or code is not valid.")


def find_by_email(db: Session, email: str) -> StaffAccount | None:
    return db.execute(
        select(StaffAccount).where(StaffAccount.email == _normalise_email(email))
    ).scalar_one_or_none()


def authenticate(
    db: Session,
    settings: Settings,
    audit: AuditLog,
    *,
    request: StaffLoginRequest,
) -> StaffAccount:
    """Verify password and TOTP and return the operator to issue a session for.

    Order of checks: lockout, credentials, role, then second factor. Each
    outcome is audited; the submitted password and TOTP are never recorded.
    """
    account = find_by_email(db, request.email)
    now = utcnow()

    if account is None:
        # Spend the same time as a real verification so a missing account and a
        # wrong password are indistinguishable by timing.
        verify_secret(request.password, _DUMMY_HASH, _pepper(settings))
        audit.append("staff.login_failed", reason="invalid_credentials")
        raise _invalid_credentials()

    if account.status == "disabled":
        audit.append("staff.login_failed", actor_id=account.id, target=account.id, reason="disabled")
        raise _not_permitted()

    if account.locked_until is not None and account.locked_until > now:
        audit.append("staff.login_failed", actor_id=account.id, target=account.id, reason="locked")
        raise APIError(
            423,
            ErrorCode.FORBIDDEN,
            "This account is locked after repeated failed attempts. Contact an administrator.",
        )

    if not verify_secret(request.password, account.password_hash, _pepper(settings)):
        _record_failure(db, audit, account, reason="invalid_credentials", now=now)
        raise _invalid_credentials()

    try:
        OperatorRole(account.role)
    except ValueError as exc:
        audit.append("staff.login_failed", actor_id=account.id, target=account.id, reason="role")
        raise _not_permitted() from exc

    if account.totp_secret:
        if not totp.verify(account.totp_secret, request.totp):
            _record_failure(db, audit, account, reason="invalid_totp", now=now)
            raise _invalid_credentials()
        must_enrol = False
    else:
        # Factor two has not been provisioned; the session is not MFA-verified
        # and may not reach any operator surface until an administrator enrolls it.
        must_enrol = True

    account.failed_attempts = 0
    account.locked_until = None
    account.last_login_at = now
    db.flush()

    audit.append(
        "staff.login",
        actor_id=account.id,
        actor_role=account.role,
        target=account.id,
        detail={"mfaVerified": not must_enrol},
    )
    return account


def _record_failure(
    db: Session,
    audit: AuditLog,
    account: StaffAccount,
    *,
    reason: str,
    now: datetime,
) -> None:
    account.failed_attempts += 1
    if account.failed_attempts >= MAX_FAILED_ATTEMPTS:
        account.locked_until = now + timedelta(seconds=LOCKOUT_SECONDS)
        account.status = "locked" if account.status == "active" else account.status
    db.flush()
    audit.append(
        "staff.login_failed",
        actor_id=account.id,
        target=account.id,
        reason=reason,
        detail={"failedAttempts": account.failed_attempts},
    )


def logout(db: Session, audit: AuditLog, *, staff_id: str) -> None:
    account = db.get(StaffAccount, staff_id)
    if account is not None:
        audit.append("staff.logout", actor_id=account.id, target=account.id)
    else:
        audit.append("staff.logout", actor_id=staff_id, target=staff_id)
