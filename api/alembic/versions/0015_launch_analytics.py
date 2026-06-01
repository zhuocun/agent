"""Add first-party launch analytics events.

Revision ID: 0015_launch_analytics
Revises: 0014_message_request_fingerprint
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_launch_analytics"
down_revision: str | Sequence[str] | None = "0014_message_request_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine[object]:
    return postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def _jsonb() -> sa.types.TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "telemetry_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    op.create_table(
        "analytics_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_analytics_event_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("properties", _jsonb(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_analytics_event_user_created",
        "analytics_event",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_analytics_event_type_created",
        "analytics_event",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_analytics_first_success_user_unique",
        "analytics_event",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("event_type = 'activation.first_successful_response'"),
        sqlite_where=sa.text("event_type = 'activation.first_successful_response'"),
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_first_success_user_unique", table_name="analytics_event")
    op.drop_index("ix_analytics_event_type_created", table_name="analytics_event")
    op.drop_index("ix_analytics_event_user_created", table_name="analytics_event")
    op.drop_table("analytics_event")
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("telemetry_enabled")
