"""Staff account entity for the Operations Console.

There are no shared operator accounts (operations.md): each staff member has
their own row, one role, and their own second factor. Passwords and the TOTP
seed are stored one-way or encrypted-at-rest material and are never returned on
the wire or written to a log.

The entity is defined here, next to the auth surface that owns it, rather than
in ``app.db.models``; the primary Alembic environment and the initial migration
must import and table it so a deployed console can authenticate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampedMixin, UUIDPrimaryKeyMixin

# Marked so the privacy registry can locate the fields that carry personal data.
PERSONAL = {"personal_data": True}


class StaffAccount(UUIDPrimaryKeyMixin, TimestampedMixin, Base):
    __tablename__ = "staff_accounts"

    # The login identifier. Stored lower-cased so a case variation does not
    # create a second account (no shared operator accounts, operations.md).
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, info=PERSONAL)
    # Argon2id hash of the password with a server-side pepper (NFR-021).
    password_hash: Mapped[str] = mapped_column(Text, info=PERSONAL)
    # Base32 RFC 4648 secret for the TOTP second factor. NULL until an
    # administrator has enrolled the factor.
    totp_secret: Mapped[str | None] = mapped_column(Text, info=PERSONAL)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # status: active, locked (held by policy), disabled (revoked).
        CheckConstraint(
            "status IN ('active', 'locked', 'disabled')",
            name="staff_account_status",
        ),
    )
