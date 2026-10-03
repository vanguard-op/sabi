"""Primary-store entity for a federal agency's collection channel.

The catalogue ``Service`` says what is collected and by which body; it does not
carry the collection account an agency collects through, whether a payer
reference is mandatory, or how a payer obtains one. Those are the agency-side
facts a federal payment needs before it is prepared, so they live with the
federal flows rather than in the shared catalogue, mirroring how the registry
keeps capability detail beside a service (FEAT-006).

``status`` carries the collection-account check from FEAT-006: when
reconciliation or the agency reports that the account has changed, it flips to
``changed`` and a prepare reads as a conflict until the channel is re-resolved.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class FederalCollection(UUIDPrimaryKeyMixin, TimestampedMixin, Base):
    __tablename__ = "federal_collections"

    service_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # The agency account a federal collection arrives in. Checked by
    # reconciliation for the designated treasury account (operations.md).
    account_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    # A payer reference (for example an agency-issued assessment number) is
    # required before the obligation can be paid (FEAT-006).
    requires_reference: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # How to complete the payment, shown when no extra guidance is needed.
    instructions: Mapped[str | None] = mapped_column(String(512))
    # How a payer obtains the reference, shown when one is required and the user
    # has not supplied it, so Sabi explains rather than paying without it
    # (FEAT-006, user-flow Flow 2 step 6).
    reference_instructions: Mapped[str | None] = mapped_column(String(512))
    # ``current`` when the account is valid, ``changed`` when the agency has
    # switched collection accounts and the channel must be re-resolved.
    status: Mapped[str] = mapped_column(String(16), default="current", nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('current', 'changed')", name="status"),
        CheckConstraint("length(account_reference) > 0", name="account_reference_nonempty"),
    )


__all__ = ["FederalCollection"]
