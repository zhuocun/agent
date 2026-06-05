"""Add customizable keyboard-shortcut overrides to preferences.

Revision ID: 0024_keyboard_shortcuts
Revises: 0021_memory_ledger
Create Date: 2026-06-05 00:00:00.000000

A per-user map of keyboard-shortcut remaps (D23). Keyed by stable action id
(`ShortcutId`) -> override combo `{key, mod?, shift?}`. Empty map (the default)
means every action uses its built-in default. The effective binding (default
merged with override) drives both the live keydown matcher and the shortcuts
dialog on the FE.

Cross-dialect notes:
- env.py uses `render_as_batch=True`, so we wrap the ALTER in
  `op.batch_alter_table(...)` for SQLite (tests) safety. Postgres handles the
  plain ADD COLUMN equally well through the batch shim.
- JSONB on Postgres, JSON on SQLite (mirrors `app.db.types.JsonVariant`).
- `server_default="'{}'"` backfills existing rows so the column is never NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024_keyboard_shortcuts"
down_revision: str | Sequence[str] | None = "0023_prompt_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb() -> sa.types.TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "keyboard_shortcuts",
                _jsonb(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("keyboard_shortcuts")
