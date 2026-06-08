"""Ephemeral expiry + sensitivity flag on conversation (D31 / T13).

Revision ID: 0026_conversation_expiry_sensitive
Revises: 0025_conversation_tags_archive
Create Date: 2026-06-08 00:00:00.000000

Adds two columns to `conversation`:
- `expires_at`: a nullable timezone-aware timestamp. NULL = no hard expiry; when
  set, the retention purge deletes the conversation once `now >= expires_at`.
  This is how an `isEphemeral` chat auto-deletes after a fixed lifetime.
- `is_sensitive`: a NOT NULL boolean (server_default false) marking a thread the
  user designated sensitive.

Cross-dialect notes (mirrors 0025): env.py uses `render_as_batch=True` for
SQLite, so both ADDs are wrapped in `op.batch_alter_table`. `_timestamp_tz()`
resolves to `TIMESTAMP WITH TIME ZONE` on Postgres and a reflected `TIMESTAMP`
on SQLite (the timezone flag can't round-trip there — see test_migrations.py).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_conversation_expiry_sensitive"
down_revision: str | Sequence[str] | None = "0025_conversation_tags_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.add_column(
            sa.Column("expires_at", _timestamp_tz(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "is_sensitive",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.drop_column("is_sensitive")
        batch_op.drop_column("expires_at")
