"""Add the `stream` table for the streaming-turn lifecycle.

Revision ID: 0007_stream_table
Revises: 0006_message_usage_cost
Create Date: 2026-05-29 00:03:00.000000

PRD 04 §5.1: persist the in-progress assistant message + track the active
stream id per conversation so "stop" can be a dedicated server-side action
(and, later, so streams can be resumed). One row per streaming turn on a
non-temporary conversation; lifecycle `active -> done | stopped | error`.

Schema choices:
- `conversation_id` FK ON DELETE CASCADE: deleting a conversation drops its
  stream rows.
- `message_id` FK ON DELETE SET NULL, nullable: points at the in-progress /
  final assistant message. NULL until the assistant row is persisted; a purged
  message nulls the pointer rather than dangling.
- `status` non-null with server_default "active" so a freshly-inserted row is
  unambiguously active without the app having to set it.
- Index on `conversation_id` for the "active stream for this conversation"
  lookup the stop endpoint does; index on `status` is a cheap aid to that
  filter.

Cross-dialect notes:
- env.py uses `render_as_batch=True`. `op.create_table` + `op.create_index` are
  plain CREATEs that work identically on Postgres and SQLite (tests).
- UUID columns use the same `_uuid()` variant helper as 0001/0005/0006;
  timestamps mirror 0001's `sa.TIMESTAMP(timezone=True)` + `sa.func.now()`.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_stream_table"
down_revision: Union[str, Sequence[str], None] = "0006_message_usage_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "stream",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            _uuid(),
            sa.ForeignKey(
                "conversation.id",
                ondelete="CASCADE",
                name="fk_stream_conversation_id_conversation",
            ),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            _uuid(),
            sa.ForeignKey(
                "message.id",
                ondelete="SET NULL",
                name="fk_stream_message_id_message",
            ),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="active",
        ),
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
    op.create_index("ix_stream_conversation", "stream", ["conversation_id"])
    op.create_index("ix_stream_status", "stream", ["status"])


def downgrade() -> None:
    op.drop_index("ix_stream_status", table_name="stream")
    op.drop_index("ix_stream_conversation", table_name="stream")
    op.drop_table("stream")
