"""Switch cost ledger columns from Float to Numeric(12,6).

Revision ID: 0008_cost_numeric
Revises: 0007_stream_table
Create Date: 2026-05-29 00:04:00.000000

A binary `float` (double precision) ledger drifts by ULPs near the `>=` budget
cap when summed over many turns. Switch both cost columns to fixed-precision
`NUMERIC(12,6)` so Postgres (prod) stores exact decimals and accumulates them
exactly via the SQL-side `cost_usd + excluded.cost_usd` upsert. The ORM keeps
`asdecimal=False`, so SQLAlchemy still returns Python floats — no Decimal ripple
through pricing/handler/tests.

Columns:
- `message.cost_usd` (nullable): per-turn cost mirroring `attribution.costUsd`.
- `usage_rollup.cost_usd` (non-null, server_default 0): accumulated per-period
  cost the budget gate reads.

Cross-dialect notes:
- env.py uses `render_as_batch=True`, so the ALTERs go through
  `op.batch_alter_table(...)`. On SQLite (tests) that recreates the table; the
  values are preserved (SQLite stores NUMERIC as REAL — no exactness, fine since
  prod is Postgres). On Postgres `float8 -> numeric` is an assignment cast, so
  `ALTER TYPE` needs no `USING` clause.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_cost_numeric"
down_revision: Union[str, Sequence[str], None] = "0007_stream_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.alter_column(
            "cost_usd",
            type_=sa.Numeric(12, 6),
            existing_type=sa.Float(),
            existing_nullable=True,
        )
    with op.batch_alter_table("usage_rollup") as batch_op:
        batch_op.alter_column(
            "cost_usd",
            type_=sa.Numeric(12, 6),
            existing_type=sa.Float(),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_rollup") as batch_op:
        batch_op.alter_column(
            "cost_usd",
            type_=sa.Float(),
            existing_type=sa.Numeric(12, 6),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
        )
    with op.batch_alter_table("message") as batch_op:
        batch_op.alter_column(
            "cost_usd",
            type_=sa.Float(),
            existing_type=sa.Numeric(12, 6),
            existing_nullable=True,
        )
