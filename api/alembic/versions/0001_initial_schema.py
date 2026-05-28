"""Initial schema: users, sessions, conversation, message, vote, api_key, usage_rollup.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-28 00:00:00.000000

All seven M0+M1+M2+M3 tables ship in one revision so future milestones don't
need migration work to land. Column types are dialect-aware: Postgres gets
JSONB + native UUID, everything else (SQLite for tests) gets JSON + CHAR(36).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def _jsonb() -> sa.types.TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False, server_default="Guest"),
        sa.Column(
            "is_anonymous",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("plan_label", sa.String(), nullable=False, server_default="Free"),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_sessions_user_id_users"),
            nullable=False,
        ),
        sa.Column("expires_at", _timestamp_tz(), nullable=False),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "conversation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_conversation_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(), nullable=False, server_default="New chat"),
        sa.Column("selected_tier_id", sa.String(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "conversation_user_pinned_updated_idx",
        "conversation",
        ["user_id", "pinned", "updated_at"],
    )

    op.create_table(
        "message",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            _uuid(),
            sa.ForeignKey(
                "conversation.id",
                ondelete="CASCADE",
                name="fk_message_conversation_id_conversation",
            ),
            nullable=False,
        ),
        sa.Column("client_message_id", _uuid(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("parts", _jsonb(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("attribution", _jsonb(), nullable=True),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="message_client_msg_uniq",
        ),
    )
    op.create_index(
        "ix_message_conversation_created",
        "message",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "vote",
        sa.Column(
            "message_id",
            _uuid(),
            sa.ForeignKey(
                "message.id", ondelete="CASCADE", name="fk_vote_message_id_message"
            ),
            primary_key=True,
        ),
        sa.Column("feedback", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "api_key",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_api_key_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("ciphertext", sa.String(), nullable=False),
        sa.Column("masked_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "provider", name="api_key_user_provider_uniq"
        ),
    )

    op.create_table(
        "usage_rollup",
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_usage_rollup_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("period_start", _timestamp_tz(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column(
            "is_byok", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.PrimaryKeyConstraint("user_id", "period_start", name="usage_rollup_pk"),
    )


def downgrade() -> None:
    op.drop_table("usage_rollup")
    op.drop_table("api_key")
    op.drop_table("vote")
    op.drop_index("ix_message_conversation_created", table_name="message")
    op.drop_table("message")
    op.drop_index("conversation_user_pinned_updated_idx", table_name="conversation")
    op.drop_table("conversation")
    op.drop_table("sessions")
    op.drop_table("users")
