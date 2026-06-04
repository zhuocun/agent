"""Add message request fingerprint for idempotency replay.

Revision ID: 0014_message_request_fingerprint
Revises: 0013_usage_credit_ledger_constraints
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_message_request_fingerprint"
down_revision: str | Sequence[str] | None = "0013_usage_credit_ledger_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb() -> sa.types.TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.add_column(
            sa.Column("request_fingerprint", _jsonb(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.drop_column("request_fingerprint")
