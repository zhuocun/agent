"""usage_rollup repository.

Per the M0 budget review: "per-turn counter for MVP". M3 increments by 1 per
terminal (including stopped-flush) and reads the current calendar-month row on
bootstrap. The `is_byok` column on a row records whether THAT period's last
write was a BYOK turn -- analytics-only today (the FE shows
`UsageBudget.isByok` from the user's current key state, not historical writes).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageRollup
from app.schemas.account import UsageBudget

# Default monthly cap until real cost data drives the limit. The FE renders
# `used / limit` raw with no unit, so the number is informational. M4 swaps
# this for cost-based caps via PRD 07.
_DEFAULT_LIMIT = 1000
_DEFAULT_PERIOD = "this month"


def _month_start(now: datetime | None = None) -> datetime:
    """Calendar-month UTC start for the current (or given) instant."""
    ref = now if now is not None else datetime.now(UTC)
    return ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def increment_for_period(
    db: AsyncSession,
    *,
    user_id: UUID,
    used_delta: int = 1,
    is_byok: bool = False,
    period_start: datetime | None = None,
) -> None:
    """Upsert the (user_id, period_start) rollup row, bumping `used`.

    Cross-dialect select-then-update-or-insert; same pattern the preferences
    and votes repos use. The `period_start` defaults to the current calendar
    month so all turns in the same month land on the same row. The caller
    must commit -- this function flushes but leaves the transaction open so
    it can be part of the same commit as the persisted assistant message.
    """
    period = period_start if period_start is not None else _month_start()
    # MVP: SELECT-then-INSERT/UPDATE; concurrent terminals for the same period
    # may race and undercount. M4 to use ON CONFLICT DO UPDATE / SELECT FOR UPDATE.
    stmt = select(UsageRollup).where(
        UsageRollup.user_id == user_id,
        UsageRollup.period_start == period,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = UsageRollup(
            user_id=user_id,
            period_start=period,
            used=used_delta,
            limit_value=_DEFAULT_LIMIT,
            is_byok=is_byok,
        )
        db.add(row)
    else:
        row.used = row.used + used_delta
        # `is_byok` reflects the LATEST write's BYOK state -- last-write-wins.
        # The FE-facing `UsageBudget.isByok` is computed separately at read
        # time from the user's current key state (see `get_current_budget`),
        # so this column is analytics-only today.
        row.is_byok = is_byok
    await db.flush()


async def get_current_budget(
    db: AsyncSession,
    user_id: UUID,
    is_byok: bool,
) -> UsageBudget:
    """Return the current month's rollup as a FE-shape `UsageBudget`.

    `is_byok` reflects the caller's current key state, not the rollup row's
    historical flag -- the column is analytics-only (see plan §"UsageBudget
    semantics"). Returns the default-zero budget when no row exists for the
    period yet.
    """
    period = _month_start()
    stmt = select(UsageRollup).where(
        UsageRollup.user_id == user_id,
        UsageRollup.period_start == period,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    used = int(row.used) if row is not None else 0
    limit = int(row.limit_value) if row is not None else _DEFAULT_LIMIT
    return UsageBudget(
        used=used,
        limit=limit,
        period_label=_DEFAULT_PERIOD,
        is_byok=is_byok,
    )
