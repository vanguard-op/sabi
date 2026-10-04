"""unique service natural key (name, collecting_body)

The catalogue seeder upserts by the natural key ``(name, collecting_body)`` in
application logic, but the table had no database-level guard, so a concurrent
double-load (two ``up`` runs, or an operator re-running the seed) could create a
duplicate service that then splits discovery ranking and grounding (FEAT-004,
FEAT-012). This adds a case-insensitive unique expression index on the natural
key.

Existing rows are not guaranteed unique, so the migration first reconciles any
duplicates deterministically before it applies the constraint: for each
case-folded natural key it keeps the earliest row (oldest ``created_at``,
``id`` as the tie-breaker) and deletes the rest. No non-key meaning is merged;
the duplicates are exact-key collisions, and keeping the oldest preserves the
original record. On every environment so far the ``services`` table is empty,
so this reconciliation is a no-op there.

Revision ID: a1b2c3d4e5f6
Revises: 9e2d4b7a1c8f
Create Date: 2026-10-04 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9e2d4b7a1c8f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Deterministic reconciliation: keep the earliest row per case-folded key,
#: ordered by created_at then id so the choice is stable across reruns.
_KEEP_EARLIEST = """
DELETE FROM services
WHERE id IN (
    SELECT id FROM (
        SELECT
            id,
            row_number() OVER (
                PARTITION BY lower(name), lower(collecting_body)
                ORDER BY created_at ASC, id ASC
            ) AS rn
        FROM services
    ) AS ranked
    WHERE ranked.rn > 1
)
"""


def upgrade() -> None:
    # Reconcile duplicates before the unique index can be created.
    op.execute(_KEEP_EARLIEST)
    op.create_index(
        "uq_services_natural_key",
        "services",
        [sa.text("lower(name)"), sa.text("lower(collecting_body)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_services_natural_key", table_name="services")
