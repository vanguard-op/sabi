"""Primary-store entities, mirroring schema.md.

Names are snake_case columns over the schema's camelCase fields; the API layer
maps to the wire format. Amounts are integer minor units paired with a currency
(schema.md, Overview). Fields annotated ``x-personal-data`` carry
``info={"personal_data": True}`` so the privacy registry can find them.

Payment execution entities (mandate, method, payment, payment event) live in the
isolated payment module with their own schema and audit log; references to them
here are opaque scalars, never foreign keys across the store boundary.
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampedMixin, UUIDPrimaryKeyMixin

PERSONAL = {"personal_data": True}


def _enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class User(UUIDPrimaryKeyMixin, TimestampedMixin, Base):
    __tablename__ = "users"

    display_name: Mapped[str | None] = mapped_column(String(200), info=PERSONAL)
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    preferred_channel: Mapped[str] = mapped_column(String(16), default="app", nullable=False)
    kyc_status: Mapped[str] = mapped_column(String(16), default="unverified", nullable=False)
    account_status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    __table_args__ = (
        _enum_check("locale", ("en", "pcm", "ha", "yo", "ig"), "locale"),
        _enum_check("preferred_channel", ("app", "ussd", "sms", "whatsapp"), "preferred_channel"),
        _enum_check("kyc_status", ("unverified", "pending", "verified", "rejected"), "kyc_status"),
        _enum_check("account_status", ("active", "suspended", "closed"), "account_status"),
    )


class AuthCredential(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "auth_credentials"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Passkey material: public half only; private keys never leave the device.
    public_key: Mapped[str | None] = mapped_column(Text, info=PERSONAL)
    # One-way Argon2id hash of a recovery code; never reversible (NFR-021).
    secret_hash: Mapped[str | None] = mapped_column(Text, info=PERSONAL)
    signature_counter: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    __table_args__ = (
        _enum_check("type", ("passkey", "recovery_code"), "type"),
        _enum_check("status", ("active", "revoked", "used"), "status"),
        Index("ix_auth_credentials_user_type", "user_id", "type"),
    )


class ChannelLink(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "channel_links"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    address: Mapped[str] = mapped_column(String(64), info=PERSONAL, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("channel", ("ussd", "sms", "whatsapp"), "channel"),
        # An address maps to exactly one account across every channel: the same
        # number on a second channel is the same identity, so a second link is
        # rejected rather than creating a duplicate (FEAT-001, user-flow.md
        # "Channel Identity Linking").
        UniqueConstraint("address", name="uq_channel_links_address"),
    )


class IdentityVerification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "identity_verifications"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    # Masked identity number, never the full value (schema.md).
    identifier_masked: Mapped[str] = mapped_column(String(64), info=PERSONAL, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("method", ("nin", "bvn"), "method"),
        _enum_check("status", ("pending", "verified", "failed", "corrected"), "status"),
    )


class Provider(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(254), info=PERSONAL)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)

    __table_args__ = (
        _enum_check("type", ("agency", "biller", "merchant", "aggregator"), "type"),
        _enum_check("status", ("pending", "active", "suspended", "deregistered"), "status"),
        Index("ix_providers_name", "name"),
    )


class Service(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "services"

    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    collecting_body: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    provider_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="SET NULL"), index=True
    )
    # Opaque reference to the capability that pays this service. Kept a scalar
    # because capability.service_id points back, and the two would be circular.
    capability_id: Mapped[str | None] = mapped_column(String(36), index=True)
    known_amount: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("type", ("government", "biller", "merchant"), "type"),
        _enum_check("status", ("active", "unavailable", "retired"), "status"),
        CheckConstraint("known_amount IS NULL OR known_amount >= 0", name="known_amount_nonneg"),
    )


class Capability(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "capabilities"

    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("services.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    input_schema_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_source: Mapped[str] = mapped_column(String(16), nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_amount: Mapped[int | None] = mapped_column(Integer)
    price_currency: Mapped[str | None] = mapped_column(String(3))
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    health_status: Mapped[str] = mapped_column(String(16), default="healthy", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)

    __table_args__ = (
        _enum_check("amount_source", ("fixed", "user_entered", "provider_query"), "amount_source"),
        _enum_check("health_status", ("healthy", "degraded", "unavailable"), "health_status"),
        _enum_check("status", ("pending", "active", "quarantined", "withdrawn"), "status"),
        CheckConstraint("price_amount IS NULL OR price_amount >= 0", name="price_amount_nonneg"),
    )


class Receipt(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "receipts"

    # The payment lives in the isolated payment store; the reference is opaque.
    payment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    receipt_number: Mapped[str | None] = mapped_column(String(128))
    verification_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    # Plain reason the receipt is unverified; null when verified or pending
    # (schema.md, Receipt.unverifiedReason; FEAT-008).
    unverified_reason: Mapped[str | None] = mapped_column(String(512))
    document_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("kind", ("official_e_receipt", "biller_confirmation", "token"), "kind"),
        _enum_check(
            "verification_status", ("verified", "unverified", "pending"), "verification_status"
        ),
    )


class PaymentCase(UUIDPrimaryKeyMixin, TimestampedMixin, Base):
    __tablename__ = "payment_cases"

    payment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    assignee_role: Mapped[str] = mapped_column(String(64), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check(
            "type",
            ("failed_no_delivery", "disputed", "refund", "receipt_missing"),
            "type",
        ),
        _enum_check(
            "status",
            ("open", "awaiting_provider", "resolved", "escalated", "closed"),
            "status",
        ),
    )


class Reminder(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "reminders"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lead_time_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default="app", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", nullable=False)

    __table_args__ = (
        _enum_check("channel", ("app", "ussd", "sms", "whatsapp"), "channel"),
        _enum_check("status", ("scheduled", "sent", "cancelled", "paid"), "status"),
        CheckConstraint("lead_time_hours >= 1", name="lead_time_hours_positive"),
    )


class Pool(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "pools"

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("status", ("open", "funded", "paid", "refunded", "closed"), "status"),
        CheckConstraint("target_amount >= 0", name="target_amount_nonneg"),
    )


class Contribution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "contributions"

    pool_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contributor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pledged", nullable=False)
    # Settling payment is an opaque reference to the payment store.
    payment_id: Mapped[str | None] = mapped_column(String(36), index=True)

    __table_args__ = (
        _enum_check("status", ("pledged", "paid", "reversed"), "status"),
        CheckConstraint("amount >= 0", name="amount_nonneg"),
    )


class Notification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    payload_ref: Mapped[str | None] = mapped_column(String(512))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        _enum_check("channel", ("sms", "push", "whatsapp"), "channel"),
        _enum_check("status", ("queued", "sent", "delivered", "failed"), "status"),
    )


class AuditLogRecord(Base):
    """Append-only, hash-chained audit stream (NFR-028).

    The chain links each row to its predecessor; see app.core.audit. Rows are
    never updated or deleted.
    """

    __tablename__ = "audit_log"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
