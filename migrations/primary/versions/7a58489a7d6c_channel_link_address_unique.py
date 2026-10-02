"""channel link address unique across channels

An address identifies one account across every channel (FEAT-001). The former
(channel, address) constraint allowed the same number to attach to a second
channel on another account; replace it with an address-only constraint.

Revision ID: 7a58489a7d6c
Revises: 25448567494d
Create Date: 2026-10-02 19:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "7a58489a7d6c"
down_revision: str | None = "25448567494d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_channel_links_channel_address", "channel_links", type_="unique")
    op.create_unique_constraint("uq_channel_links_address", "channel_links", ["address"])


def downgrade() -> None:
    op.drop_constraint("uq_channel_links_address", "channel_links", type_="unique")
    op.create_unique_constraint(
        "uq_channel_links_channel_address", "channel_links", ["channel", "address"]
    )
