"""Transparent long-term memory v1 (D19): fact ledger + opt-in toggle.

Revision ID: 0020_memory_ledger
Revises: 0019_preferences_per_conversation_budget
Create Date: 2026-06-05 00:00:00.000000

Adds:
- `preferences.memory_enabled`: opt-in toggle, default False. When True (and a
  turn is not temporary) the user's saved facts are injected into the turn.
- `memory_fact`: the editable, attributed fact ledger — the glass-box
  differentiator. One row per saved fact, owned by a user (CASCADE on delete so
  account erasure removes them; the users repo also deletes them explicitly,
  matching the SQLite-no-cascade pattern). `source` records whether the fact was
  added manually or distilled from a conversation; `source_conversation_id` is a
  best-effort back-reference (SET NULL so deleting a conversation never blocks).

Cross-dialect notes (mirrors 0011): `_uuid()/_json()/_timestamp_tz()` resolve to
PG-native types on Postgres and SQLite-friendly variants in tests. env.py uses
`render_as_batch=True`, so the column ADD is wrapped in `op.batch_alter_table`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_memory_ledger"
down_revision: str | Sequence[str] | None = "0019_preferences_per_conversation_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(
        sa.CHAR(36), "sqlite"
    )


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "memory_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.create_table(
        "memory_fact",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_memory_fact_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.String(),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column(
            "source_conversation_id",
            _uuid(),
            sa.ForeignKey(
                "conversation.id",
                ondelete="SET NULL",
                name="fk_memory_fact_source_conversation_id_conversation",
            ),
            nullable=True,
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
    op.create_index(
        "ix_memory_fact_user_created",
        "memory_fact",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_fact_user_created", table_name="memory_fact")
    op.drop_table("memory_fact")
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("memory_enabled")
