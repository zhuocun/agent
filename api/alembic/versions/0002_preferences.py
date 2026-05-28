"""Preferences table.

Revision ID: 0002_preferences
Revises: 0001_initial_schema
Create Date: 2026-05-28 01:00:00.000000

M2 adds a `preferences` table — one row per user. M0 bootstrap synthesized a
default `UserPreferences` payload because the storage didn't exist; M2 lazily
upserts the defaults on first `GET /api/bootstrap` so the row exists by the
time `PUT /api/preferences` can land. Cross-dialect column types follow the
M0 pattern (Postgres-native + SQLite variants).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_preferences"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "preferences",
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_preferences_user_id_users",
            ),
            primary_key=True,
        ),
        sa.Column(
            "default_tier_id", sa.String(), nullable=False, server_default="auto"
        ),
        sa.Column(
            "temporary_by_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "training_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "send_on_enter",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "auto_expand_reasoning",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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


def downgrade() -> None:
    op.drop_table("preferences")
