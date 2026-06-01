"""Constrain usage credit ledger values.

Revision ID: 0013_usage_credit_ledger_constraints
Revises: 0012_usage_credit_ledger
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_usage_credit_ledger_constraints"
down_revision: str | Sequence[str] | None = "0012_usage_credit_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTRY_TYPE_CHECK = "entry_type IN ('grant', 'platform_debit', 'adjustment')"
_AMOUNT_SIGN_CHECK = (
    "("
    "entry_type = 'grant' AND amount_usd > 0"
    ") OR ("
    "entry_type = 'platform_debit' AND amount_usd < 0"
    ") OR ("
    "entry_type = 'adjustment' AND amount_usd <> 0"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table("usage_credit_ledger") as batch_op:
        batch_op.create_check_constraint(
            "ck_usage_credit_ledger_entry_type",
            _ENTRY_TYPE_CHECK,
        )
        batch_op.create_check_constraint(
            "ck_usage_credit_ledger_amount_sign",
            _AMOUNT_SIGN_CHECK,
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_credit_ledger") as batch_op:
        batch_op.drop_constraint(
            "ck_usage_credit_ledger_amount_sign",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_usage_credit_ledger_entry_type",
            type_="check",
        )
