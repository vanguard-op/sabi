"""Compliance review entities for the privileged-action audit view (C-041-C-043).

The audit timeline itself is read from the existing append-only ``audit_log``;
these entities hold only the state the review workflow needs on top of it:

- ``ComplianceFinding`` is the open-or-closed state of a completeness review.
  Closing it records the reviewer and the resolution, and appends the action to
  the audit log (operations-console.md, "Privileged-action audit view").
- ``AuditExport`` is a queued audit extract. The request is itself a privileged
  action and is logged; the row tracks the queued job (C-043).

They are defined next to the surface that owns them, following ``app.staff``,
so two modules' tables do not collide in the shared ``app.db.models``. The
primary Alembic environment must import this module so the tables are created.
Nothing here offers an update or delete of ``audit_log``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampedMixin, UUIDPrimaryKeyMixin


class ComplianceFinding(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One completeness review: an action suspected of having no audit entry.

    A finding starts ``open`` and can be closed once with a resolution. The
    reviewed target and the reviewer are kept so the monthly completeness check
    can be reproduced; personal data is never copied into this row (NFR-028).
    """

    __tablename__ = "compliance_findings"

    # The privileged action or actor the review is about, as it appears in the
    # log's ``target``/``actor`` fields. Opaque, never personal data.
    target: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # The role whose further privileged actions are blocked until the gap is
    # corrected (operations.md, "Privileged-action and audit-log review").
    blocked_role: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The reviewer's staff id and the resolution text, set when closed.
    closed_by: Mapped[str | None] = mapped_column(String(36))
    resolution: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="compliance_finding_status"),
    )


class AuditExport(UUIDPrimaryKeyMixin, TimestampedMixin, Base):
    """A queued audit extract (C-043).

    The job carries the requested window and format only; the extract itself is
    produced by the export worker and is not held here, so no bulk personal data
    sits in the primary store. Status is ``queued`` until the worker claims it.
    """

    __tablename__ = "audit_exports"

    requested_by: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    range_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)

    __table_args__ = (
        CheckConstraint("format IN ('csv', 'json')", name="audit_export_format"),
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="audit_export_status"
        ),
        CheckConstraint("range_from <= range_to", name="audit_export_range_order"),
    )


__all__ = ["AuditExport", "ComplianceFinding"]
