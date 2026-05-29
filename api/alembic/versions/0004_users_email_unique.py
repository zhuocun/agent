"""Partial UNIQUE INDEX on `users.email WHERE email IS NOT NULL`.

Revision ID: 0004_users_email_unique
Revises: 0003_user_password_hash
Create Date: 2026-05-29 00:00:00.000000

Plan §"Post-M4 deferred hardening": today's signup path does a SELECT-then-
UPDATE to enforce email uniqueness, which can race with a concurrent upgrade
on the same email. This migration adds a partial UNIQUE INDEX so the DB
itself rejects the dupe and the auth route can catch IntegrityError and
return EMAIL_TAKEN deterministically.

Cross-dialect notes:
- Postgres: a partial UNIQUE INDEX with `WHERE email IS NOT NULL` is the
  correct shape. NULL emails (anonymous users) are excluded from the
  uniqueness check entirely; we never compare them.
- SQLite (tests): partial indexes are supported (3.8+), and SQLite treats
  multiple NULL values as distinct in a UNIQUE index regardless of the
  partial predicate. We still emit the partial predicate via `sqlite_where`
  for parity with Postgres semantics.

The index name `ix_users_email_unique` matches the project's naming pattern
for distinct ad-hoc indexes (vs. the `uq_<table>_<col>` convention reserved
for plain UNIQUE constraints).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_users_email_unique"
down_revision: Union[str, Sequence[str], None] = "0003_user_password_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_users_email_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
        sqlite_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_unique", table_name="users")
