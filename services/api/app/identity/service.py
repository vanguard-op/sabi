"""Identity service: passkey ceremonies, recovery, and channel links (FEAT-001).

The router stays thin; this layer holds the rules and raises the contract's
errors. It never logs or returns a recovery code, credential key, or channel
address beyond what the frozen contract explicitly puts on the wire.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException

from app.core.config import Settings
from app.core.errors import APIError, ErrorCode
from app.core.ids import new_id
from app.core.security import generate_recovery_code, hash_secret, verify_secret
from app.core.time import utcnow
from app.db.models import AuthCredential, ChannelLink, Notification, User
from app.identity import passkeys
from app.identity.challenges import (
    CHALLENGE_TTL_SECONDS,
    Challenge,
    ChallengeKind,
    ChallengeStore,
)
from app.identity.schemas import SUPPORTED_LOCALES


def ensure_locale(locale: str) -> str:
    if locale not in SUPPORTED_LOCALES:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "Choose English or Pidgin to continue.")
    return locale


def _normalise_recovery_code(raw: str) -> str:
    return raw.strip().upper().replace(" ", "")


def _find_passkey(
    db: Session, credential_id_b64: str
) -> tuple[AuthCredential | None, bytes | None]:
    """Find an active passkey by the credential id presented at sign-in.

    The frozen schema has no credential-id column, so the id is carried inside
    the ``public_key`` envelope; the lookup scans active passkeys.
    """
    try:
        wanted = base64url_to_bytes(credential_id_b64)
    except Exception:
        return None, None
    rows = (
        db.execute(
            select(AuthCredential).where(
                AuthCredential.type == "passkey",
                AuthCredential.status == "active",
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if not row.public_key:
            continue
        try:
            stored_id, stored_key = passkeys.decode_passkey(row.public_key)
        except (ValueError, KeyError, TypeError):
            continue
        if stored_id == wanted:
            return row, stored_key
    return None, None


def start_registration(
    settings: Settings, store: ChallengeStore, *, locale: str
) -> tuple[str, dict]:
    ensure_locale(locale)
    challenge_bytes = passkeys.new_challenge()
    user_handle = passkeys.new_user_handle()
    user_name = passkeys.new_user_name()
    challenge_id = new_id()
    store.put(
        Challenge(
            id=challenge_id,
            kind=ChallengeKind.REGISTRATION,
            challenge=challenge_bytes,
            expires_at=utcnow() + timedelta(seconds=CHALLENGE_TTL_SECONDS),
        )
    )
    public_key = passkeys.registration_options(
        settings,
        challenge=challenge_bytes,
        user_handle=user_handle,
        user_name=user_name,
    )
    return challenge_id, public_key


def finish_registration(
    db: Session,
    settings: Settings,
    store: ChallengeStore,
    *,
    challenge_id: str,
    credential: dict,
    display_name: str | None,
    locale: str,
) -> tuple[User, str]:
    challenge = store.consume(challenge_id)
    if challenge is None or challenge.kind is not ChallengeKind.REGISTRATION:
        raise APIError(410, ErrorCode.CHALLENGE_EXPIRED, "That sign-up took too long. Start again.")
    ensure_locale(locale)
    try:
        verified = passkeys.verify_registration(
            settings, credential=credential, challenge=challenge.challenge
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        raise APIError(
            400, ErrorCode.INVALID_REQUEST, "That passkey could not be verified. Try again."
        ) from exc

    credential_b64 = bytes_to_base64url(verified.credential_id)
    if _find_passkey(db, credential_b64)[0] is not None:
        raise APIError(409, ErrorCode.CONFLICT, "That passkey is already registered.")

    user = User(
        display_name=(display_name or "").strip() or None,
        locale=locale,
        preferred_channel="app",
        kyc_status="unverified",
        account_status="active",
    )
    db.add(user)
    db.flush()

    db.add(
        AuthCredential(
            user_id=user.id,
            type="passkey",
            public_key=passkeys.encode_passkey(
                verified.credential_id, verified.credential_public_key
            ),
            signature_counter=verified.sign_count,
            status="active",
        )
    )
    recovery_code = generate_recovery_code()
    pepper = settings.recovery_code_pepper.get_secret_value()
    db.add(
        AuthCredential(
            user_id=user.id,
            type="recovery_code",
            secret_hash=hash_secret(recovery_code, pepper),
            status="active",
        )
    )
    db.flush()
    return user, recovery_code


def start_authentication(settings: Settings, store: ChallengeStore) -> tuple[str, dict]:
    challenge_bytes = passkeys.new_challenge()
    challenge_id = new_id()
    store.put(
        Challenge(
            id=challenge_id,
            kind=ChallengeKind.AUTHENTICATION,
            challenge=challenge_bytes,
            expires_at=utcnow() + timedelta(seconds=CHALLENGE_TTL_SECONDS),
        )
    )
    public_key = passkeys.authentication_options(settings, challenge=challenge_bytes)
    return challenge_id, public_key


def finish_authentication(
    db: Session,
    settings: Settings,
    store: ChallengeStore,
    *,
    challenge_id: str,
    credential: dict,
) -> User:
    challenge = store.consume(challenge_id)
    if challenge is None or challenge.kind is not ChallengeKind.AUTHENTICATION:
        raise APIError(410, ErrorCode.CHALLENGE_EXPIRED, "That sign-in took too long. Try again.")
    credential_b64 = passkeys.credential_id_of(credential)
    if credential_b64 is None:
        raise APIError(400, ErrorCode.INVALID_REQUEST, "That passkey response was not valid.")
    row, public_key = _find_passkey(db, credential_b64)
    if row is None or public_key is None:
        raise APIError(
            401, ErrorCode.UNAUTHENTICATED, "No matching passkey. Use a recovery code or sign up."
        )
    try:
        verified = passkeys.verify_authentication(
            settings,
            credential=credential,
            challenge=challenge.challenge,
            public_key=public_key,
            sign_count=row.signature_counter or 0,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        raise APIError(
            400, ErrorCode.INVALID_REQUEST, "That passkey could not be verified. Try again."
        ) from exc

    row.signature_counter = verified.new_sign_count
    user = db.get(User, row.user_id)
    if user is None:
        raise APIError(
            401, ErrorCode.UNAUTHENTICATED, "No matching passkey. Use a recovery code or sign up."
        )
    db.flush()
    return user


def verify_recovery(db: Session, settings: Settings, *, recovery_code: str) -> User:
    code = _normalise_recovery_code(recovery_code)
    if not code:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "That recovery code is not valid.")
    pepper = settings.recovery_code_pepper.get_secret_value()
    rows = (
        db.execute(
            select(AuthCredential).where(
                AuthCredential.type == "recovery_code",
                AuthCredential.status.in_(("active", "used")),
            )
        )
        .scalars()
        .all()
    )
    used_match: AuthCredential | None = None
    for row in rows:
        if not row.secret_hash:
            continue
        if not verify_secret(code, row.secret_hash, pepper):
            continue
        if row.status == "active":
            row.status = "used"
            user = db.get(User, row.user_id)
            db.flush()
            if user is None:
                raise APIError(401, ErrorCode.UNAUTHENTICATED, "That recovery code is not valid.")
            return user
        used_match = row
    if used_match is not None:
        raise APIError(
            409,
            ErrorCode.CONFLICT,
            "That recovery code has already been used. Sign in with a passkey or contact support.",
        )
    raise APIError(401, ErrorCode.UNAUTHENTICATED, "That recovery code is not valid.")


def regenerate_recovery(db: Session, settings: Settings, *, user_id: str) -> str:
    user = db.get(User, user_id)
    if user is None:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")
    active = (
        db.execute(
            select(AuthCredential).where(
                AuthCredential.user_id == user_id,
                AuthCredential.type == "recovery_code",
                AuthCredential.status == "active",
            )
        )
        .scalars()
        .all()
    )
    for row in active:
        row.status = "revoked"
    code = generate_recovery_code()
    pepper = settings.recovery_code_pepper.get_secret_value()
    db.add(
        AuthCredential(
            user_id=user_id,
            type="recovery_code",
            secret_hash=hash_secret(code, pepper),
            status="active",
        )
    )
    db.flush()
    return code


def create_channel_link(
    db: Session, *, user_id: str, channel: str, address: str
) -> tuple[ChannelLink, User | None]:
    """Attach a channel address to the account.

    An address identifies one account across every channel, so a link owned by
    another account is a conflict regardless of the channel presented (FEAT-001).
    Returns the link and, when a different account already owns the address, its
    owner so the caller can reject the link and notify them.
    """
    existing = db.execute(
        select(ChannelLink).where(ChannelLink.address == address)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.user_id == user_id:
            return existing, None
        return existing, db.get(User, existing.user_id)

    link = ChannelLink(user_id=user_id, channel=channel, address=address, verified_at=None)
    db.add(link)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent link won the unique address race.
        db.rollback()
        existing = db.execute(
            select(ChannelLink).where(ChannelLink.address == address)
        ).scalar_one_or_none()
        if existing is None:
            raise
        return existing, (None if existing.user_id == user_id else db.get(User, existing.user_id))
    return link, None


def notify_channel_conflict(db: Session, *, owner: User) -> None:
    """Queue a notice to the existing owner; never echo the address back."""
    target = owner.preferred_channel if owner.preferred_channel in ("sms", "whatsapp") else "sms"
    db.add(
        Notification(
            user_id=owner.id,
            channel=target,
            template="channel_link_conflict",
            status="queued",
        )
    )


def get_account(db: Session, *, user_id: str) -> tuple[User, list[ChannelLink]]:
    user = db.get(User, user_id)
    if user is None:
        raise APIError(401, ErrorCode.UNAUTHENTICATED, "Sign in to continue.")
    links = (
        db.execute(
            select(ChannelLink)
            .where(ChannelLink.user_id == user_id)
            .order_by(ChannelLink.created_at.asc())
        )
        .scalars()
        .all()
    )
    return user, list(links)
