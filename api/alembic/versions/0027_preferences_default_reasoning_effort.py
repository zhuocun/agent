"""Add persisted default reasoning-effort preference.

Revision ID: 0027_preferences_default_reasoning_effort
Revises: 0026_conversation_expiry_sensitive
Create Date: 2026-06-18 00:00:00.000000

A per-user default `ReasoningEffortId` (`auto` | `minimal` | `standard` |
`extended`) mirroring how `default_tier_id` persists the user's default tier.
`auto` defers to the selected tier's binding default — so the default value
keeps existing behavior identical for every backfilled row.

Cross-dialect notes (mirrors 0024 / 0026): env.py uses `render_as_batch=True`,
so the ADD is wrapped in `op.batch_alter_table` for SQLite (tests) safety.
`server_default="auto"` backfills existing rows so the column is never NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_preferences_default_reasoning_effort"
down_revision: str | Sequence[str] | None = "0026_conversation_expiry_sensitive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_reasoning_effort",
                sa.Text(),
                nullable=False,
                server_default="auto",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("default_reasoning_effort")
