"""Development-only provisioning of a staff operator account.

The Operations Console needs one working credential before anyone can exercise the
provider review, health and quarantine, and audit surfaces (operations-console.md,
"Staff authentication"). No account is created by the login path itself, so this
module provisions exactly one administrator.

Safety property (NFR-024): the function refuses to run outside ``development``.
The TOTP secret is printed only by the dev-only entrypoint; it is the deliberate
provisioning output, and no password is ever logged. The seed is idempotent: a
re-run updates the existing row rather than creating a second account, since the
email is unique and the console keeps no shared operator accounts (operations.md).
"""

from __future__ import annotations

import base64
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import OperatorRole
from app.core.config import Settings
from app.core.security import hash_secret
from app.staff import totp
from app.staff.models import StaffAccount

# The dev credential's non-secret identity. Overridable so a developer can hold
# several console identities. The domain must be a syntactically valid address the
# login schema accepts: a reserved TLD such as ``.local`` is rejected by
# ``EmailStr`` before the credential ever reaches the seed, so it would be
# unusable. This is a local identity, never a real mailbox and never a production
# value.
DEFAULT_DEV_STAFF_EMAIL = "admin@sabi.ng"

# The account is an administrator because that is the only role that reaches
# every Phase 1 console surface: provider review, health and quarantine, and the
# audit view (which otherwise needs compliance_privacy_officer).
DEV_STAFF_ROLE = OperatorRole.ADMINISTRATOR


class SeedError(RuntimeError):
    """Raised when provisioning is refused or cannot proceed."""


@dataclass(frozen=True)
class SeedResult:
    """What the provisioning run produced, for the operator to enrol or sign in."""

    staff_id: str
    email: str
    role: str
    totp_secret: str
    current_code: str
    created: bool


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def generate_totp_secret() -> str:
    """Return a base32 (RFC 4648) TOTP seed an authenticator app can enrol.

    160 bits from ``secrets``; the padding is stripped because authenticator apps
    display the bare base32 string, and ``app.staff.totp`` restores any missing
    padding when it decodes.
    """
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def guard_environment(settings: Settings) -> None:
    """Refuse to provision outside development (NFR-024, safety property).

    Raises ``SeedError`` with a clear message; callers must let it propagate so a
    misconfigured environment fails loudly rather than writing a dev credential.
    """
    if settings.environment != "development":
        raise SeedError(
            "The dev staff seed only runs in development; "
            f"environment is {settings.environment!r}. Provision operators through "
            "the administrator workflow in a deployed environment."
        )


def seed_dev_staff(
    db: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    code_at: Callable[[str], str] | None = None,
) -> SeedResult:
    """Create or refresh the single development administrator account.

    ``password`` is hashed here with the configured pepper and never stored or
    returned in the clear. ``code_at`` lets a test pin the TOTP step; the
    entrypoint leaves it at the current step.
    """
    guard_environment(settings)

    if not email or "@" not in email:
        raise SeedError("A valid staff email is required.")
    if not password:
        # Never echo the value; the value itself must come from the secret store.
        raise SeedError("A non-empty staff password is required.")

    normalised = _normalise_email(email)
    account = db.execute(
        select(StaffAccount).where(StaffAccount.email == normalised)
    ).scalar_one_or_none()

    created = account is None
    if account is None:
        account = StaffAccount(email=normalised)
        db.add(account)

    account.password_hash = hash_secret(password, settings.recovery_code_pepper.get_secret_value())
    account.role = str(DEV_STAFF_ROLE)
    account.status = "active"
    account.failed_attempts = 0
    account.locked_until = None
    # A fresh seed always re-provisions the factor, so a lost authenticator is
    # recovered by re-running the seed rather than by a self-service flow
    # (operations-console.md, "Staff authentication": administrator re-enrolment).
    account.totp_secret = generate_totp_secret()

    db.flush()

    generate_code = code_at or (lambda secret: totp.generate(secret))
    return SeedResult(
        staff_id=account.id,
        email=account.email,
        role=account.role,
        totp_secret=account.totp_secret,
        current_code=generate_code(account.totp_secret),
        created=created,
    )
