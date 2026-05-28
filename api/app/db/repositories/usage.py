"""usage_rollup repository.

M0 returns a default `UsageBudget` — no rollup writes happen yet. Once M3
increments per-terminal we'll read the current period's row here.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.account import UsageBudget

# Default monthly budget for M0. Real cap math lands when we have real cost.
_DEFAULT_LIMIT = 1000
_DEFAULT_PERIOD = "this month"


async def get_current_budget(
    db: AsyncSession,
    user_id: UUID,
    is_byok: bool,
) -> UsageBudget:
    """Synthesize a monthly budget. M3 reads the real rollup row."""
    return UsageBudget(
        used=0,
        limit=_DEFAULT_LIMIT,
        period_label=_DEFAULT_PERIOD,
        is_byok=is_byok,
    )
