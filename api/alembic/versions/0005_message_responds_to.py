"""Add `responds_to_message_id` to `message` for explicit reply pairing.

Revision ID: 0005_message_responds_to
Revises: 0004_users_email_unique
Create Date: 2026-05-29 00:01:00.000000

Plan §"Post-M4 deferred hardening": the M1 `_maybe_replay` idempotency path
pairs the i-th user message with the i-th assistant message ordered by
`(created_at, id)`. That works for M1's "one assistant per user" invariant,
but is fragile against regenerate, edit, and any future tool/branch shapes.
This migration adds an explicit `responds_to_message_id` FK on assistant
rows pointing at the user message whose reply they are.

Schema choices:
- Nullable: existing rows pre-migration get NULL. `_maybe_replay` keeps the
  pair-by-index fallback so legacy data still replays correctly.
- Self-referential FK to `message.id` with ON DELETE SET NULL: if a user
  message gets removed (e.g. edit-truncate), the assistant row's pointer
  becomes NULL rather than dangling — and the assistant row itself is
  already cascaded out by the conversation-level cascade, so SET NULL is
  defensive only.
- Index `ix_message_responds_to` to make the "find assistant for this user
  message" lookup an O(log n) seek instead of a full-conversation scan.

Cross-dialect notes:
- Postgres: standard self-referential FK + index, no surprises.
- SQLite (tests): `render_as_batch=True` in env.py rewrites ALTER TABLE
  ADD COLUMN with FK as a CREATE TABLE + copy. We don't need explicit
  batch_alter_table here because op.add_column is supported on SQLite for
  nullable columns without defaults.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_message_responds_to"
down_revision: Union[str, Sequence[str], None] = "0004_users_email_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.add_column(
            sa.Column(
                "responds_to_message_id",
                _uuid(),
                sa.ForeignKey(
                    "message.id",
                    ondelete="SET NULL",
                    name="fk_message_responds_to_message_id_message",
                ),
                nullable=True,
            )
        )
    op.create_index(
        "ix_message_responds_to",
        "message",
        ["responds_to_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_responds_to", table_name="message")
    with op.batch_alter_table("message") as batch_op:
        batch_op.drop_column("responds_to_message_id")
