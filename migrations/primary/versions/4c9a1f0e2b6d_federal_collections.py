"""federal collections

The catalogue Service says what is collected and by which body; it does not
carry the agency account a federal collection arrives in, whether a payer
reference is mandatory, or how a payer obtains one. Those agency-side facts
are held on FederalCollection so a federal payment can be prepared and
reconciliation can check the designated treasury account (FEAT-006,
schema.md, operations.md "Reconciliation operations").

Revision ID: 4c9a1f0e2b6d
Revises: 3b1f2c9d4e07
Create Date: 2026-10-03 00:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c9a1f0e2b6d"
down_revision: str | None = "3b1f2c9d4e07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "federal_collections",
        sa.Column("service_id", sa.String(length=36), nullable=False),
        sa.Column("account_reference", sa.String(length=128), nullable=False),
        sa.Column("requires_reference", sa.Boolean(), nullable=False),
        sa.Column("instructions", sa.String(length=512), nullable=True),
        sa.Column("reference_instructions", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('current', 'changed')",
            name=op.f("ck_federal_collections_status"),
        ),
        sa.CheckConstraint(
            "length(account_reference) > 0",
            name=op.f("ck_federal_collections_account_reference_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_federal_collections_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_federal_collections")),
    )
    # Exactly one collection channel per service (schema.md).
    op.create_index(
        op.f("ix_federal_collections_service_id"),
        "federal_collections",
        ["service_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_federal_collections_service_id"), table_name="federal_collections")
    op.drop_table("federal_collections")
