"""Add per-conversation retention override to conversation.

Revision ID: 0020_conversation_retention
Revises: 0019_preferences_per_conversation_budget
Create Date: 2026-06-05 00:00:00.000000

A per-conversation retention override (D31). NULL means "inherit the user's
global `preferences.retention_days`" (which is itself NULL = retain forever).
A non-NULL integer N expires the conversation once `now - updated_at > N days`,
independent of the global preference — letting a user keep one thread longer
(or purge it sooner) than their default. Keyed on `updated_at` to match the
existing global opportunistic purge semantics.

Cross-dialect notes:
- env.py uses `render_as_batch=True`, so we wrap the ALTER in
  `op.batch_alter_table(...)` for SQLite (tests) safety. Postgres handles the
  plain ADD COLUMN equally well through the batch shim.
- The physical table is `conversation` (singular), matching the ORM
  `Conversation.__tablename__`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_conversation_retention"
down_revision: str | Sequence[str] | None = "0019_preferences_per_conversation_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.add_column(sa.Column("retention_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.drop_column("retention_days")
