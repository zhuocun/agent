"""Add user monthly budget cap to preferences.

Revision ID: 0018_preferences_monthly_budget
Revises: 0017_custom_instructions
Create Date: 2026-06-04 00:00:00.000000

A user-set monthly platform-spend cap in USD. NULL means "no user cap" (only the
operator's USAGE_BUDGET_USD applies). `Numeric(12,6)` mirrors the existing money
columns (`usage_rollup.cost_usd`, `message.cost_usd`) so the cap composes with
the same fixed-precision arithmetic.

Cross-dialect notes:
- env.py uses `render_as_batch=True`, so we wrap the ALTER in
  `op.batch_alter_table(...)` for SQLite (tests) safety. Postgres handles the
  plain ADD COLUMN equally well through the batch shim.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_preferences_monthly_budget"
down_revision: str | Sequence[str] | None = "0017_custom_instructions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column("monthly_budget_usd", sa.Numeric(12, 6), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("monthly_budget_usd")
