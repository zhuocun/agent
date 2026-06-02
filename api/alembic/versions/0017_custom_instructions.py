"""Add custom instructions to preferences.

Revision ID: 0017_custom_instructions
Revises: 0016_billing_entitlements
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_custom_instructions"
down_revision: str | Sequence[str] | None = "0016_billing_entitlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "preferences",
        sa.Column(
            "custom_instructions",
            sa.String(length=4000),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("preferences", "custom_instructions")
