"""Identity verification rules (FEAT-002, C-020..C-022).

The router stays thin; this layer holds the rules and maps provider outcomes to
the frozen contract. It never stores or returns the submitted identifier: the
record keeps a masked form only (schema.md, IdentityVerification.identifierMasked;
NFR-043). No identifier, full or masked, is ever written to the audit log.

Correction policy (FEAT-002, "Data mismatch ... allow correction once, then
require support"): a first no-match leaves the account rejected and correctable;
a second no-match also leaves it rejected but closes self-service, so the client
routes the user to support instead of looping.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import AuditLog
from app.core.errors import APIError, ErrorCode
from app.core.sessions import SessionData
from app.core.time import utcnow
from app.db.models import IdentityVerification, User
from app.identity.verification.provider import (
    IdentityProvider,
    ProviderOutcome,
    ProviderResult,
    UnavailableIdentityProvider,
)

# One self-service correction after a no-match, then support (FEAT-002).
MAX_SELF_SERVICE_ATTEMPTS = 2

# A NIN and a BVN are both eleven digits. Rejecting anything else is the 400 the
# contract names ("invalid identifier") before a provider is ever called.
_IDENTIFIER_LENGTH = 11

_NO_MATCH_REASON = (
    "The details you gave do not match the national identity record. Check them and try once more."
)
_RETRY_EXHAUSTED_REASON = (
    "We still could not match your details. Contact support so we can help you finish."
)
_PENDING_REASON = "We are still checking your details. This can take a little while."
_UNKNOWN_REASON = "That verification could not be found."


@dataclass(frozen=True, slots=True)
class VerificationState:
    """The account-level verification view (C-022)."""

    kyc_status: str
    method: str | None
    can_correct: bool


def _normalise_identifier(raw: str) -> str:
    return raw.strip()


def _is_valid_identifier(identifier: str) -> bool:
    return len(identifier) == _IDENTIFIER_LENGTH and identifier.isdigit()


def mask_identifier(identifier: str) -> str:
    """Mask an identity number, keeping only the last four digits.

    The full value is never persisted; this is the only form the record keeps
    (schema.md, IdentityVerification.identifierMasked; NIMC one-identity rule).
    """
    tail = identifier[-4:] if len(identifier) >= 4 else identifier
    return f"{'*' * max(len(identifier) - len(tail), 0)}{tail}"


def _latest_for_user(db: Session, user_id: str) -> IdentityVerification | None:
    return (
        db.execute(
            select(IdentityVerification)
            .where(IdentityVerification.user_id == user_id)
            .order_by(IdentityVerification.created_at.desc(), IdentityVerification.id.desc())
        )
        .scalars()
        .first()
    )


def _failed_attempts(db: Session, user_id: str) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(IdentityVerification)
            .where(
                IdentityVerification.user_id == user_id,
                IdentityVerification.status == "failed",
            )
        ).scalar_one()
    )


def get_account_verification(db: Session, *, user_id: str) -> VerificationState:
    """The account's verification state (C-022).

    ``canCorrect`` is true only while the account is rejected and still within
    its one self-service correction (FEAT-002). Unverified, pending, and verified
    accounts are never offering a correction.
    """
    user = db.get(User, user_id)
    if user is None:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")
    latest = _latest_for_user(db, user_id)
    method = latest.method if latest is not None else None
    can_correct = (
        user.kyc_status == "rejected" and _failed_attempts(db, user_id) < MAX_SELF_SERVICE_ATTEMPTS
    )
    return VerificationState(
        kyc_status=user.kyc_status,
        method=method,
        can_correct=can_correct,
    )


def get_verification(db: Session, *, user_id: str, verification_id: str) -> IdentityVerification:
    """One verification record owned by the caller (C-021).

    A record owned by another account is reported as unknown, never as forbidden,
    so the endpoint cannot be used to probe which identifiers exist.
    """
    record = db.get(IdentityVerification, verification_id)
    if record is None or record.user_id != user_id:
        raise APIError(404, ErrorCode.NOT_FOUND, _UNKNOWN_REASON)
    return record


def _reason_for(record: IdentityVerification, can_correct: bool) -> str | None:
    if record.status == "verified":
        return None
    if record.status == "pending":
        return _PENDING_REASON
    if record.status == "failed":
        return _NO_MATCH_REASON if can_correct else _RETRY_EXHAUSTED_REASON
    return None


def detail_payload(db: Session, *, user_id: str, record: IdentityVerification) -> dict:
    """Map a record to the C-021 wire shape.

    ``reason`` is recomputed at read time so it reflects the account's remaining
    correction, not the sentence stored when the check failed.
    """
    can_correct = (
        record.status == "failed" and _failed_attempts(db, user_id) < MAX_SELF_SERVICE_ATTEMPTS
    )
    return {
        "verificationId": record.id,
        "method": record.method,
        "status": record.status,
        "reason": _reason_for(record, can_correct),
        "verifiedAt": record.verified_at,
    }


def start_verification(
    db: Session,
    audit: AuditLog,
    *,
    actor: SessionData,
    method: str,
    identifier: str,
    provider: IdentityProvider | None = None,
) -> tuple[IdentityVerification, bool]:
    """Submit an identity check (C-020).

    Returns the record and whether it was an explicit correction of the prior
    attempt. Raises 409 when a check is already in progress, so a second submit
    cannot race the first (C-020).
    """
    normalised = _normalise_identifier(identifier)
    if not _is_valid_identifier(normalised):
        raise APIError(
            400,
            ErrorCode.INVALID_REQUEST,
            "Enter the 11 digits of your NIN or BVN.",
        )

    user = db.get(User, actor.user_id)
    if user is None:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")

    latest = _latest_for_user(db, actor.user_id)
    if latest is not None and latest.status == "pending":
        raise APIError(409, ErrorCode.CONFLICT, "Your verification is already in progress.")

    is_correction = user.kyc_status == "rejected"
    if is_correction and _failed_attempts(db, actor.user_id) >= MAX_SELF_SERVICE_ATTEMPTS:
        # Self-service is closed; do not create another record that could loop.
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "We still could not match your details. Contact support so we can help you finish.",
        )

    result = (provider or UnavailableIdentityProvider()).check(method=method, identifier=normalised)
    record = _record_for_result(
        db,
        user=user,
        method=method,
        identifier=normalised,
        result=result,
        is_correction=is_correction,
    )
    db.flush()

    audit.append(
        "identity.verification.submit",
        actor_id=actor.user_id,
        actor_role=actor.role,
        target=record.id,
        # The identifier, full or masked, is personal data (schema.md); it is
        # never written here. Only the method and resulting status are recorded.
        detail={"method": record.method, "status": record.status, "correction": is_correction},
    )
    return record, is_correction


def _record_for_result(
    db: Session,
    *,
    user: User,
    method: str,
    identifier: str,
    result: ProviderResult,
    is_correction: bool,
) -> IdentityVerification:
    """Persist the check outcome and move the account's KYC status with it."""
    if result.outcome is ProviderOutcome.UNAVAILABLE:
        # Queue, never fail: discovery stays open and a gated payment is held.
        record = IdentityVerification(
            user_id=user.id,
            method=method,
            identifier_masked=mask_identifier(identifier),
            status="pending",
            provider_reference=None,
            verified_at=None,
        )
        db.add(record)
        user.kyc_status = "pending"
        return record

    if result.outcome is ProviderOutcome.MATCH:
        record = IdentityVerification(
            user_id=user.id,
            method=method,
            identifier_masked=mask_identifier(identifier),
            status="corrected" if is_correction else "verified",
            provider_reference=result.reference,
            verified_at=utcnow(),
        )
        db.add(record)
        user.kyc_status = "verified"
        return record

    record = IdentityVerification(
        user_id=user.id,
        method=method,
        identifier_masked=mask_identifier(identifier),
        status="failed",
        provider_reference=result.reference,
        verified_at=None,
    )
    db.add(record)
    user.kyc_status = "rejected"
    return record


__all__ = [
    "MAX_SELF_SERVICE_ATTEMPTS",
    "VerificationState",
    "detail_payload",
    "get_account_verification",
    "get_verification",
    "mask_identifier",
    "start_verification",
]
