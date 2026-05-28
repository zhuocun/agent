"""Add `password_hash` to `users`.

Revision ID: 0003_user_password_hash
Revises: 0002_preferences
Create Date: 2026-05-28 02:00:00.000000

M3 introduces `POST /api/auth/upgrade`. Email is required; password is optional
for MVP (we'll ship magic links / passkeys later). When the caller supplies a
password we store its bcrypt digest; otherwise the column stays NULL so the
user can only sign back in via the future passwordless flow.

Nullable column — does not need a default. Existing rows (anonymous users
created prior to this migration) get NULL on upgrade, matching the new-row
default.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_password_hash"
down_revision: Union[str, Sequence[str], None] = "0002_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash")
