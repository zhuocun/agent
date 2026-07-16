"""Platform budget reservation holds (B9).

Revision ID: 0029_platform_budget_reservation
Revises: 0028_message_server_state_parts_version
Create Date: 2026-07-16 00:00:00.000000

Adds ``platform_budget_reservation`` so concurrent agentic turns atomically
reserve estimated platform spend under a per-user lock. Active holds are
subtracted from ``get_platform_remaining_usd``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029_platform_budget_reservation"
down_revision: str | Sequence[str] | None = "0028_message_server_state_parts_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine[object]:
    return postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "platform_budget_reservation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_platform_budget_reservation_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column(
            "stream_id",
            _uuid(),
            sa.ForeignKey(
                "stream.id",
                ondelete="CASCADE",
                name="fk_platform_budget_reservation_stream_id_stream",
            ),
            nullable=False,
        ),
        sa.Column("amount_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "stream_id", name="uq_platform_budget_reservation_stream"
        ),
    )
    op.create_index(
        "ix_platform_budget_reservation_user",
        "platform_budget_reservation",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_budget_reservation_user",
        table_name="platform_budget_reservation",
    )
    op.drop_table("platform_budget_reservation")
