"""Conversation Org v2: user-scoped tags, a tag join table, and an archive flag.

Revision ID: 0025_conversation_tags_archive
Revises: 0024_keyboard_shortcuts
Create Date: 2026-06-05 00:00:00.000000

Adds:
- `tag`: a user-scoped label owned by a user (CASCADE on delete so account
  erasure removes them). The `(user_id, name)` UNIQUE index keeps tag names
  unique per user.
- `conversation_tag`: a join table linking conversations to tags. Composite PK
  `(conversation_id, tag_id)`; both FKs CASCADE. A `(tag_id)` index backs the
  "conversations for a tag" filter read.
- `conversation.archived`: a NOT NULL boolean (server_default false) that hides
  archived chats from the sidebar's main recency list. Archived conversations
  remain subject to the retention purge.

Cross-dialect notes (mirrors 0022/0024): `_uuid()` resolves to a PG-native UUID
on Postgres and a 36-char CHAR on SQLite (tests). env.py uses
`render_as_batch=True` for SQLite, so the `conversation.archived` ADD is wrapped
in `op.batch_alter_table`. The `tag` table is created BEFORE `conversation_tag`
so its FK target exists. Explicit FK names (`name="fk_..."`) keep the batch
recreate on SQLite dropable.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_conversation_tags_archive"
down_revision: str | Sequence[str] | None = "0024_keyboard_shortcuts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(
        sa.CHAR(36), "sqlite"
    )


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "tag",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_tag_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
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
        "ix_tag_user_name",
        "tag",
        ["user_id", "name"],
        unique=True,
    )

    op.create_table(
        "conversation_tag",
        sa.Column(
            "conversation_id",
            _uuid(),
            sa.ForeignKey(
                "conversation.id",
                ondelete="CASCADE",
                name="fk_conversation_tag_conversation_id_conversation",
            ),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            _uuid(),
            sa.ForeignKey(
                "tag.id",
                ondelete="CASCADE",
                name="fk_conversation_tag_tag_id_tag",
            ),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_conversation_tag_tag",
        "conversation_tag",
        ["tag_id"],
    )

    with op.batch_alter_table("conversation") as batch_op:
        batch_op.add_column(
            sa.Column(
                "archived",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.drop_column("archived")
    op.drop_index("ix_conversation_tag_tag", table_name="conversation_tag")
    op.drop_table("conversation_tag")
    op.drop_index("ix_tag_user_name", table_name="tag")
    op.drop_table("tag")
