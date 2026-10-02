"""Payment-store entities, mirroring schema.md.

This store is isolated: it has no foreign keys to the primary database, so
``user_id`` and ``service_id`` are opaque references. A payment record stores the
amount, currency, and payee at execution time so a receipt never changes if a
catalogue entry is later edited (schema.md, Overview).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from sabi_payments.db.base import (
    Base,
    CreatedAtMixin,
    TimestampedMixin,
    UUIDPrimaryKeyMixin,
)

PERSONAL = {"personal_data": True}


def _enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class PaymentMandate(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "payment_mandates"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    capability_id: Mapped[str | None] = mapped_column(String(36))
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    payee: Mapped[str] = mapped_column(String(200), nullable=False)
    payee_reference: Mapped[str | None] = mapped_column(String(128))
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="issued", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        _enum_check("status", ("issued", "consumed", "expired", "revoked"), "status"),
        CheckConstraint("amount >= 0", name="amount_nonneg"),
    )


class PaymentMethod(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "payment_methods"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    # Masked identifier only; a full account or card number is never stored
    # (schema.md, NFR-042).
    masked_identifier: Mapped[str] = mapped_column(String(64), info=PERSONAL, nullable=False)
    processor_token: Mapped[str | None] = mapped_column(Text, info=PERSONAL)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    __table_args__ = (
        _enum_check("type", ("bank_account", "wallet", "card"), "type"),
        _enum_check("status", ("active", "expired", "revoked"), "status"),
    )


class Payment(UUIDPrimaryKeyMixin, TimestampedMixin, Base):
    __tablename__ = "payments"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mandate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("payment_mandates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payment_method_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("payment_methods.id", ondelete="SET NULL"), index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    payee: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="initiated", nullable=False)
    rail_reference: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    # Unique so a replayed request never double-pays (architecture.md).
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("type", ("government", "bill"), "type"),
        _enum_check(
            "status",
            ("initiated", "authorized", "pending", "succeeded", "failed", "reversed", "refunded"),
            "status",
        ),
        _enum_check("channel", ("app", "ussd", "sms", "whatsapp"), "channel"),
        CheckConstraint("amount >= 0", name="amount_nonneg"),
        Index("ix_payments_status_created", "status", "created_at"),
    )


class PaymentEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only record of a payment state change; the case timeline."""

    __tablename__ = "payment_events"

    payment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        _enum_check(
            "status",
            ("initiated", "authorized", "pending", "succeeded", "failed", "reversed", "refunded"),
            "status",
        ),
        _enum_check("actor", ("user", "system", "rail", "provider"), "actor"),
    )


class PaymentAuditRecord(Base):
    """Append-only, hash-chained audit stream for the payment module."""

    __tablename__ = "payment_audit_log"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    target: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
