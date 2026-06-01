"""Privacy controls: retention preference and account audit events.

Revision ID: 0011_privacy_controls_audit
Revises: 0010_active_stream_unique
Create Date: 2026-06-01 00:00:00.000000

Adds:
- `preferences.retention_days`: NULL means retain forever; supported finite
  windows are validated by the API as 30 or 90 days.
- `audit_event`: append-only operational trail for sensitive account actions.
  The FK uses SET NULL so account erasure can remove the user row while keeping
  a minimal non-secret delete audit.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_privacy_controls_audit"
down_revision: str | Sequence[str] | None = "0010_active_stream_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.UUID(as_uuid=True).with_variant(
        sa.CHAR(36), "sqlite"
    )


def _json() -> sa.types.TypeEngine[object]:
    return sa.dialects.postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.add_column(sa.Column("retention_days", sa.Integer(), nullable=True))

    op.create_table(
        "audit_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_audit_event_user_id_users",
            ),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("details", _json(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_event_user_created",
        "audit_event",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_event_type_created",
        "audit_event",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_event_type_created", table_name="audit_event")
    op.drop_index("ix_audit_event_user_created", table_name="audit_event")
    op.drop_table("audit_event")
    with op.batch_alter_table("preferences") as batch_op:
        batch_op.drop_column("retention_days")
