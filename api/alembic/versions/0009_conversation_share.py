"""Add `conversation.share_token` for public-by-link sharing.

Revision ID: 0009_conversation_share
Revises: 0008_cost_numeric
Create Date: 2026-05-30 00:00:00.000000

Public share links (PRD 01 §4.10 / PRD 05 §4.3 / PRD 07 §6.4): the owner mints
a URL-safe random token; anyone holding it can read a cost-stripped view of the
conversation without authenticating. The truthiness of `share_token` is the
share state — NULL means unshared (the default), a non-NULL token means shared,
and revoke is "set it back to NULL". A UNIQUE index makes the token an
unguessable lookup key and rejects the (astronomically unlikely) collision.

Columns:
- `conversation.share_token` (nullable String): the share token. Existing rows
  default to NULL (unshared), so the migration needs no backfill.

Cross-dialect notes:
- env.py uses `render_as_batch=True` on SQLite (tests), so the column add goes
  through `op.batch_alter_table(...)` (SQLite has no `ADD COLUMN` for some
  shapes and recreates the table under batch mode). On Postgres (prod) a
  nullable `ADD COLUMN` is a cheap metadata-only change.
- The UNIQUE index is created OUTSIDE the batch block: a plain unique index
  over a nullable column treats NULLs as distinct on both Postgres and SQLite,
  so multiple unshared rows (share_token IS NULL) coexist freely.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_conversation_share"
down_revision: Union[str, Sequence[str], None] = "0008_cost_numeric"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.add_column(sa.Column("share_token", sa.String(), nullable=True))
    op.create_index(
        "ix_conversation_share_token",
        "conversation",
        ["share_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_share_token", table_name="conversation")
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.drop_column("share_token")
