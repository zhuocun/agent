"""Add user per-conversation budget cap to preferences.

Revision ID: 0019_preferences_per_conversation_budget
Revises: 0018_preferences_monthly_budget
Create Date: 2026-06-05 00:00:00.000000

A user-set per-conversation platform-spend ceiling in USD. NULL means "no
per-conversation cap". `Numeric(12,6)` mirrors the existing money columns
(`preferences.monthly_budget_usd`, `usage_rollup.cost_usd`, `message.cost_usd`)
so the cap composes with the same fixed-precision arithmetic.

Cross-dialect notes:
- env.py uses `render_as_batch=True`, so we wrap the ALTER in
  `op.batch_alter_table(...)` for SQLite (tests) safety. Postgres handles the
  plain ADD COLUMN equally well through the batch shim.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_preferences_per_conversation_budget"
down_revision: str | Sequence[str] | None = "0018_preferences_monthly_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column("per_conversation_budget_usd", sa.Numeric(12, 6), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("per_conversation_budget_usd")
