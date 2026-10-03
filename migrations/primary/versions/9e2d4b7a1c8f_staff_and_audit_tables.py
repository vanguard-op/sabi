"""staff accounts, compliance findings, and audit exports

The Operations Console brings three tables the catalogue and payment schema do
not cover. ``staff_accounts`` holds one row per operator: the console has no
shared accounts, so each row carries its own Argon2id password hash, its own
TOTP seed, and its own role (operations-console.md, "Staff authentication";
NFR-020). ``compliance_findings`` is the open-or-closed state of a completeness
review over the append-only audit stream; ``audit_exports`` is a queued audit
extract. The audit stream itself stays in ``audit_log``, written by
``app.core.audit`` (NFR-028). Each entity is defined beside the module that owns
it and registered on the metadata by ``app.db.models``.

Revision ID: 9e2d4b7a1c8f
Revises: 4c9a1f0e2b6d
Create Date: 2026-10-03 08:33:30.154319
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e2d4b7a1c8f"
down_revision: str | None = "4c9a1f0e2b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_accounts",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("totp_secret", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'locked', 'disabled')",
            name=op.f("ck_staff_accounts_staff_account_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_accounts")),
    )
    # The login identifier is unique and lower-cased before storage, so a case
    # difference never creates a second operator account (operations-console.md).
    op.create_index(op.f("ix_staff_accounts_email"), "staff_accounts", ["email"], unique=True)

    op.create_table(
        "compliance_findings",
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("blocked_role", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_by", sa.String(length=36), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('open', 'closed')",
            name=op.f("ck_compliance_findings_compliance_finding_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_findings")),
    )
    op.create_index(
        op.f("ix_compliance_findings_target"), "compliance_findings", ["target"], unique=False
    )
    op.create_index(
        op.f("ix_compliance_findings_status"), "compliance_findings", ["status"], unique=False
    )

    op.create_table(
        "audit_exports",
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("range_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "format IN ('csv', 'json')",
            name=op.f("ck_audit_exports_audit_export_format"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name=op.f("ck_audit_exports_audit_export_status"),
        ),
        sa.CheckConstraint(
            "range_from <= range_to",
            name=op.f("ck_audit_exports_audit_export_range_order"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_exports")),
    )
    op.create_index(
        op.f("ix_audit_exports_requested_by"), "audit_exports", ["requested_by"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_exports_requested_by"), table_name="audit_exports")
    op.drop_table("audit_exports")
    op.drop_index(op.f("ix_compliance_findings_status"), table_name="compliance_findings")
    op.drop_index(op.f("ix_compliance_findings_target"), table_name="compliance_findings")
    op.drop_table("compliance_findings")
    op.drop_index(op.f("ix_staff_accounts_email"), table_name="staff_accounts")
    op.drop_table("staff_accounts")
