"""Persist Model/Reasoning popup selections on preferences.

Revision ID: 0027_preferences_popup_selections
Revises: 0026_conversation_expiry_sensitive
Create Date: 2026-06-18 00:00:00.000000

Adds five columns to `preferences` so the composer's Model/Reasoning popup
selections survive a reload instead of resetting to the hard defaults:

- `default_reasoning_effort_id`: NOT NULL string, server_default 'auto'. The
  per-turn reasoning effort the composer reopens with ("auto" defers to the
  tier binding's default).
- `default_provider_id`: nullable string. NULL = no explicit provider
  preference (platform default routing).
- `web_search_default` / `json_mode_default` / `deep_research_default`: NOT
  NULL booleans, server_default false — the persisted composer toggles.

Cross-dialect notes (mirrors 0024 / 0026): env.py uses `render_as_batch=True`,
so every ADD is wrapped in `op.batch_alter_table(...)` for SQLite (tests)
safety. Postgres handles the plain ADD COLUMN equally well through the batch
shim. NOT NULL columns carry a `server_default` so existing rows backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_preferences_popup_selections"
down_revision: str | Sequence[str] | None = "0026_conversation_expiry_sensitive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_reasoning_effort_id",
                sa.String(),
                nullable=False,
                server_default=sa.text("'auto'"),
            )
        )
        batch_op.add_column(
            sa.Column("default_provider_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "web_search_default",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "json_mode_default",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "deep_research_default",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("deep_research_default")
        batch_op.drop_column("json_mode_default")
        batch_op.drop_column("web_search_default")
        batch_op.drop_column("default_provider_id")
        batch_op.drop_column("default_reasoning_effort_id")
