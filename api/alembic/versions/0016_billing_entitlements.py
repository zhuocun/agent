"""Add billing customer, entitlement, and webhook idempotency tables.

Revision ID: 0016_billing_entitlements
Revises: 0015_launch_analytics
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_billing_entitlements"
down_revision: str | Sequence[str] | None = "0015_launch_analytics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine[object]:
    return postgresql.UUID(as_uuid=True).with_variant(sa.CHAR(36), "sqlite")


def _jsonb() -> sa.types.TypeEngine[object]:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def _timestamp_tz() -> sa.types.TypeEngine[object]:
    return sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "billing_customer",
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_billing_customer_user_id_users",
            ),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(), primary_key=True),
        sa.Column("external_customer_id", sa.String(), nullable=False),
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
        sa.UniqueConstraint(
            "provider",
            "external_customer_id",
            name="billing_customer_provider_external_uniq",
        ),
    )
    op.create_index(
        "ix_billing_customer_external",
        "billing_customer",
        ["provider", "external_customer_id"],
    )

    op.create_table(
        "billing_entitlement",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_billing_entitlement_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("external_subscription_id", sa.String(), nullable=True),
        sa.Column("external_customer_id", sa.String(), nullable=True),
        sa.Column("current_period_end", _timestamp_tz(), nullable=True),
        sa.Column("external_event_created_at", _timestamp_tz(), nullable=True),
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
        sa.CheckConstraint("plan_id IN ('pro')", name="ck_billing_entitlement_plan"),
        sa.CheckConstraint(
            "status IN ("
            "'active', 'trialing', 'past_due', 'canceled', 'incomplete', "
            "'incomplete_expired', 'unpaid', 'paused'"
            ")",
            name="ck_billing_entitlement_status",
        ),
    )
    op.create_index(
        "ix_billing_entitlement_user",
        "billing_entitlement",
        ["user_id", "plan_id", "status"],
    )
    op.create_index(
        "ix_billing_entitlement_external_subscription",
        "billing_entitlement",
        ["provider", "external_subscription_id"],
        unique=True,
    )

    op.create_table(
        "billing_webhook_event",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", _jsonb(), nullable=False),
        sa.Column(
            "processed_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "billing_fulfillment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("fulfillment_type", sa.String(), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            _timestamp_tz(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "provider",
            "fulfillment_type",
            "object_id",
            name="billing_fulfillment_provider_type_object_uniq",
        ),
    )


def downgrade() -> None:
    op.drop_table("billing_fulfillment")
    op.drop_table("billing_webhook_event")
    op.drop_index(
        "ix_billing_entitlement_external_subscription",
        table_name="billing_entitlement",
    )
    op.drop_index("ix_billing_entitlement_user", table_name="billing_entitlement")
    op.drop_table("billing_entitlement")
    op.drop_index("ix_billing_customer_external", table_name="billing_customer")
    op.drop_table("billing_customer")
