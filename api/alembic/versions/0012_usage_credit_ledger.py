"""Add signed USD credit ledger.

Revision ID: 0012_usage_credit_ledger
Revises: 0011_privacy_controls_audit
Create Date: 2026-06-01 00:00:00.000000

Payment-provider-free accounting primitive for platform credits. Entries are
signed USD amounts:

- grant: positive credit grant
- platform_debit: negative draw from credits for platform-model usage
- adjustment: signed manual correction

The ledger is intentionally append-only from application code; no provider
charge, invoice, or payment intent identifiers are modeled here.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_usage_credit_ledger"
down_revision: Union[str, Sequence[str], None] = "0011_privacy_controls_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "usage_credit_ledger",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_usage_credit_ledger_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("reference_type", sa.String(), nullable=True),
        sa.Column("reference_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_usage_credit_ledger_user_created",
        "usage_credit_ledger",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_usage_credit_ledger_user_created",
        table_name="usage_credit_ledger",
    )
    op.drop_table("usage_credit_ledger")
