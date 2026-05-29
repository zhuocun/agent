"""Add `cost_usd` to `message` and `usage_rollup` for the cost ledger.

Revision ID: 0006_message_usage_cost
Revises: 0005_message_responds_to
Create Date: 2026-05-29 00:02:00.000000

PRD 04 §5.6/§6 + PRD 05 §4.4/§5.1: persist per-turn cost and accumulate it per
billing period so a USD budget cap can be enforced. Two new columns:

- `message.cost_usd` (nullable Float): the per-turn cost mirroring
  `attribution.costUsd` (breakdown subtotal + session surcharge). NULL on
  legacy rows written before this migration and on user rows.
- `usage_rollup.cost_usd` (non-null Float, server_default 0): the accumulated
  USD cost for the period. Parallel to `used` (the integer per-turn counter the
  FE meter renders raw) so the FE wire contract for `used` is unchanged; this
  is the cost-ledger axis the budget gate reads.

Cross-dialect notes:
- env.py uses `render_as_batch=True`, so we wrap both ALTERs in
  `op.batch_alter_table(...)` for SQLite (tests) safety. Postgres handles the
  plain ADD COLUMN equally well through the batch shim.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_message_usage_cost"
down_revision: Union[str, Sequence[str], None] = "0005_message_responds_to"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.add_column(
            sa.Column("cost_usd", sa.Float(), nullable=True)
        )
    with op.batch_alter_table("usage_rollup") as batch_op:
        batch_op.add_column(
            sa.Column(
                "cost_usd",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_rollup") as batch_op:
        batch_op.drop_column("cost_usd")
    with op.batch_alter_table("message") as batch_op:
        batch_op.drop_column("cost_usd")
