"""Server-only message state + parts CAS version (H-012 / H-005).

Revision ID: 0028_message_server_state_parts_version
Revises: 0027_preferences_popup_selections
Create Date: 2026-07-16 00:00:00.000000

Adds two columns on ``message``:

- ``server_state``: nullable JSON for HITL continuations / claim metadata that
  must never appear in private or public API serializers (H-012).
- ``parts_version``: integer CAS counter for conditional claim/settle writes
  that work on SQLite (ignores FOR UPDATE) and Postgres (H-005).

Cross-dialect: env.py uses ``render_as_batch=True`` for SQLite.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_message_server_state_parts_version"
down_revision: str | Sequence[str] | None = "0027_preferences_popup_selections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.add_column(sa.Column("server_state", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "parts_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("message") as batch_op:
        batch_op.drop_column("parts_version")
        batch_op.drop_column("server_state")
