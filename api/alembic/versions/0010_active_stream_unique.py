"""Partial UNIQUE INDEX: at most one active `stream` per conversation.

Revision ID: 0010_active_stream_unique
Revises: 0009_conversation_share
Create Date: 2026-05-31 00:00:00.000000

Concurrency guard (PRD 04 §5.1): a concurrent double-submit / double-regenerate
on the same conversation could open two `active` stream rows, double-streaming
and double-billing the turn. A partial UNIQUE INDEX on `conversation_id`
restricted to `status = 'active'` rows makes the DB itself reject the second
active stream; `streams_repo.create_stream` catches the IntegrityError and the
route maps it to 409 CONFLICT. The route also does a fast precheck via
`get_active_for_conversation`; this index closes the true race the precheck
can't.

Cross-dialect notes (mirrors `0004_users_email_unique`):
- Postgres (prod): a partial UNIQUE INDEX with `WHERE status = 'active'` is the
  real enforcer. Terminal rows (done / stopped / error) are excluded from the
  uniqueness check, so a new turn after the prior stream finished is allowed.
- SQLite (tests): partial indexes are supported (3.8+); tests build the schema
  via `Base.metadata.create_all`, not this migration, so the matching model-side
  `Index(..., sqlite_where=...)` is what tests exercise. We still emit the
  predicate via `sqlite_where` for parity if a migration ever runs on SQLite.

The index name `ix_stream_conversation_active_unique` matches the project's
naming pattern for ad-hoc indexes (vs the `uq_<table>_<col>` convention reserved
for plain UNIQUE constraints).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_active_stream_unique"
down_revision: Union[str, Sequence[str], None] = "0009_conversation_share"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_stream_conversation_active_unique",
        "stream",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("ix_stream_conversation_active_unique", table_name="stream")
