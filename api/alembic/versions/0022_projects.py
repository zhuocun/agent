"""Projects/Spaces: thin scoping containers for conversations (D20).

Revision ID: 0022_projects
Revises: 0021_memory_ledger
Create Date: 2026-06-05 00:00:00.000000

Adds:
- `project`: a thin scoping container owned by a user (CASCADE on delete so
  account erasure removes them). Groups conversations and scopes the EXISTING
  wedge controls — `default_tier_id`, `retention_days`,
  `per_conversation_budget_usd`, and shared `custom_instructions`. Every setting
  is a labeled default (NULL = inherit the user-global value), never a lock.
- `conversation.project_id`: the optional Project membership. SET NULL on delete
  so removing a Project un-files its conversations rather than deleting them. A
  `(user_id, project_id)` index backs the sidebar's per-project grouping.

Cross-dialect notes (mirrors 0021): `_uuid()/_timestamp_tz()` resolve to
PG-native types on Postgres and SQLite-friendly variants in tests. env.py uses
`render_as_batch=True`, so the conversation column ADD is wrapped in
`op.batch_alter_table`. The `project` table is created BEFORE the
`conversation.project_id` FK so the reference target exists.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_projects"
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
        "project",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_project_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("custom_instructions", sa.String(length=4000), nullable=True),
        sa.Column("default_tier_id", sa.String(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column(
            "per_conversation_budget_usd",
            sa.Numeric(precision=12, scale=6, asdecimal=False),
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
        "ix_project_user_created",
        "project",
        ["user_id", "created_at"],
    )

    with op.batch_alter_table("conversation") as batch_op:
        batch_op.add_column(
            sa.Column(
                "project_id",
                _uuid(),
                sa.ForeignKey(
                    "project.id",
                    ondelete="SET NULL",
                    name="fk_conversation_project_id_project",
                ),
                nullable=True,
            )
        )
        batch_op.create_index(
            "ix_conversation_user_project",
            ["user_id", "project_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("conversation") as batch_op:
        batch_op.drop_index("ix_conversation_user_project")
        batch_op.drop_column("project_id")
    op.drop_index("ix_project_user_created", table_name="project")
    op.drop_table("project")
