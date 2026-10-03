"""receipt unverified reason

A receipt the source cannot confirm is marked unverified with a plain reason
(FEAT-008); store that reason so the receipt detail can state why
(schema.md, Receipt.unverifiedReason).

Revision ID: 3b1f2c9d4e07
Revises: 7a58489a7d6c
Create Date: 2026-10-03 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b1f2c9d4e07"
down_revision: str | None = "7a58489a7d6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipts",
        sa.Column("unverified_reason", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipts", "unverified_reason")
