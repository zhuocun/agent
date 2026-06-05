"""Prompt library + user-authored templates (D23).

Revision ID: 0023_prompt_library
Revises: 0021_memory_ledger
Create Date: 2026-06-05 00:00:00.000000

Adds:
- `prompt_template`: user-owned, reusable prompt templates with variable
  placeholders (e.g. `{{topic}}`). Selecting a template prefills the composer —
  a pure composer prefill with NO model/cost/provider change. One row per
  template, owned by a user (CASCADE on delete so account erasure removes them;
  the users repo also deletes them explicitly, matching the SQLite-no-cascade
  pattern). `title`/`body` are required; `description` is an optional label.

Cross-dialect notes (mirrors 0021): `_uuid()/_timestamp_tz()` resolve to
PG-native types on Postgres and SQLite-friendly variants in tests. env.py uses
`render_as_batch=True` on SQLite; this migration only creates a table, so no
batch wrapping is needed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_prompt_library"
down_revision: str | Sequence[str] | None = "0021_memory_ledger"
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
        "prompt_template",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_prompt_template_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        "ix_prompt_template_user_created",
        "prompt_template",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prompt_template_user_created", table_name="prompt_template"
    )
    op.drop_table("prompt_template")
