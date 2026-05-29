"""usage_rollup repository.

Per the M0 budget review: "per-turn counter for MVP". M3 increments by 1 per
terminal (including stopped-flush) and reads the current calendar-month row on
bootstrap. The `is_byok` column on a row records whether THAT period's last
write was a BYOK turn -- analytics-only today (the FE shows
`UsageBudget.isByok` from the user's current key state, not historical writes).

Post-M4: increments use a dialect-specific `INSERT ... ON CONFLICT DO UPDATE`
to eliminate the SELECT-then-INSERT race. Two concurrent terminals for the
same (user_id, period_start) key both go through one atomic upsert; the DB
serializes them so the final `used` reflects every write.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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

    Atomic `INSERT ... ON CONFLICT DO UPDATE` keyed on the composite primary
    key `(user_id, period_start)`. Two concurrent terminals for the same
    period both go through one statement; the DB serializes the conflict so
    the final `used` reflects every write. `is_byok` last-write-wins (column
    is analytics-only -- see module docstring).

    Dialect-specific imports:
    - Postgres (production): `sqlalchemy.dialects.postgresql.insert` gives us
      `.on_conflict_do_update(...)`.
    - SQLite (tests): the matching `sqlalchemy.dialects.sqlite.insert`
      surface. SQLite 3.24+ supports `ON CONFLICT DO UPDATE`; aiosqlite ships
      a recent libsqlite3 in our test env.

    The caller must commit -- this function flushes but leaves the
    transaction open so it can be part of the same commit as the persisted
    assistant message.
    """
    period = period_start if period_start is not None else _month_start()

    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    if dialect == "postgresql":
        stmt_pg = pg_insert(UsageRollup).values(
            user_id=user_id,
            period_start=period,
            used=used_delta,
            limit_value=_DEFAULT_LIMIT,
            is_byok=is_byok,
        )
        stmt_pg = stmt_pg.on_conflict_do_update(
            index_elements=["user_id", "period_start"],
            set_={
                # The excluded row carries our INSERT's `used_delta`; add it to
                # the current `used` instead of replacing it so concurrent
                # writers don't clobber each other.
                "used": UsageRollup.used + stmt_pg.excluded.used,
                "is_byok": stmt_pg.excluded.is_byok,
            },
        )
        await db.execute(stmt_pg)
    else:
        # SQLite (test) and other dialects: use the SQLite-specific surface.
        stmt_sq = sqlite_insert(UsageRollup).values(
            user_id=user_id,
            period_start=period,
            used=used_delta,
            limit_value=_DEFAULT_LIMIT,
            is_byok=is_byok,
        )
        stmt_sq = stmt_sq.on_conflict_do_update(
            index_elements=["user_id", "period_start"],
            set_={
                "used": UsageRollup.used + stmt_sq.excluded.used,
                "is_byok": stmt_sq.excluded.is_byok,
            },
        )
        await db.execute(stmt_sq)
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
