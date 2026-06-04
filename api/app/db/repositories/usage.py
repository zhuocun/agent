"""usage_rollup repository.

The integer `used` meter increments by 1 per terminal (including
stopped-flush) and reads the current calendar-month row on bootstrap. The
`is_byok` column on a row records whether THAT period's last write was a BYOK
turn -- analytics-only (the FE shows `UsageBudget.isByok` from the user's
current key state, not historical writes).

Increments use a dialect-specific `INSERT ... ON CONFLICT DO UPDATE` to
eliminate the SELECT-then-INSERT race. Two concurrent terminals for the
same (user_id, period_start) key both go through one atomic upsert; the DB
serializes them so the final `used` reflects every write.

Meter semantics: `usage_rollup.cost_usd` / `used` is a CUMULATIVE METER of all
work performed in the period, NOT the sum of surviving `message.cost_usd`. Every
generation that was triggered increments it — including regenerated or edited
turns whose assistant messages were later deleted. "You pay for every generation
you triggered." So the rollup will exceed the cost of the messages currently in
the conversation; that divergence is intentional.
"""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageCreditLedger, UsageRollup, User
from app.schemas.account import UsageBudget, UsageLedgerEntry

# Default monthly cap for the integer `used` meter. The FE renders
# `used / limit` raw with no unit, so the number is informational. Cost-based
# caps (PRD 07) are the enforced gate today — see `get_period_cost` and the
# `usage_budget_usd` / `monthly_budget_usd` checks in `send_message`.
_DEFAULT_LIMIT = 1000
_DEFAULT_PERIOD = "this month"
_LEDGER_RECENT_LIMIT = 10
LedgerEntryType = Literal["grant", "platform_debit", "adjustment"]
_ENTRY_TYPES: set[LedgerEntryType] = {"grant", "platform_debit", "adjustment"}
_USAGE_LOCKS: weakref.WeakValueDictionary[UUID, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


def _month_start(now: datetime | None = None) -> datetime:
    """Calendar-month UTC start for the current (or given) instant."""
    ref = now if now is not None else datetime.now(UTC)
    return ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _round_usd(amount: float) -> float:
    return round(float(amount), 6)


def _effective_quota_usd(settings_cap: float, user_cap: float | None) -> float:
    """Compose the operator quota and the user's own cap into one enforced cap.

    A cap is "active" only when positive. When both the operator
    `USAGE_BUDGET_USD` and the user's `monthly_budget_usd` are set, the LOWER one
    wins (the stricter limit). Returns 0.0 (= "no cap") when neither is positive,
    preserving the existing budget-disabled mode.
    """
    caps = [c for c in (settings_cap, user_cap or 0.0) if c > 0]
    return min(caps) if caps else 0.0


def _usage_lock_for(user_id: UUID) -> asyncio.Lock:
    lock = _USAGE_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USAGE_LOCKS[user_id] = lock
    return lock


async def _lock_user_for_usage_update(db: AsyncSession, *, user_id: UUID) -> None:
    """Serialize per-user usage/credit accounting in databases that support it."""
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())


def _to_ledger_entry(row: UsageCreditLedger) -> UsageLedgerEntry:
    return UsageLedgerEntry(
        id=str(row.id),
        entry_type=cast(LedgerEntryType, row.entry_type),
        amount_usd=float(row.amount_usd),
        description=row.description,
        reference_type=row.reference_type,
        reference_id=row.reference_id,
        created_at=row.created_at.isoformat(),
    )


async def add_credit_entry(
    db: AsyncSession,
    *,
    user_id: UUID,
    entry_type: str,
    amount_usd: float,
    description: str | None = None,
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> UsageCreditLedger:
    """Append a signed USD ledger entry.

    `grant` entries must be positive. `platform_debit` entries must be
    negative. `adjustment` entries may be positive or negative, but not zero.
    The caller owns the commit.
    """
    amount = _round_usd(amount_usd)
    if entry_type not in _ENTRY_TYPES:
        raise ValueError(f"unsupported credit ledger entry_type {entry_type!r}")
    if amount == 0:
        raise ValueError("credit ledger amount_usd must be non-zero")
    if entry_type == "grant" and amount <= 0:
        raise ValueError("grant amount_usd must be positive")
    if entry_type == "platform_debit" and amount >= 0:
        raise ValueError("platform_debit amount_usd must be negative")

    row = UsageCreditLedger(
        user_id=user_id,
        entry_type=entry_type,
        amount_usd=amount,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    db.add(row)
    await db.flush()
    return row


async def grant_credits(
    db: AsyncSession,
    *,
    user_id: UUID,
    amount_usd: float,
    description: str | None = "Credit grant",
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> UsageCreditLedger:
    """Test/local-dev friendly credit grant helper."""
    return await add_credit_entry(
        db,
        user_id=user_id,
        entry_type="grant",
        amount_usd=amount_usd,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
    )


async def adjust_credits(
    db: AsyncSession,
    *,
    user_id: UUID,
    amount_usd: float,
    description: str | None = "Credit adjustment",
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> UsageCreditLedger:
    """Append a signed manual credit adjustment."""
    return await add_credit_entry(
        db,
        user_id=user_id,
        entry_type="adjustment",
        amount_usd=amount_usd,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
    )


async def get_credit_balance(db: AsyncSession, *, user_id: UUID) -> float:
    """Return the user's available USD credit balance, clamped to zero."""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(UsageCreditLedger.amount_usd), 0)).where(
                UsageCreditLedger.user_id == user_id
            )
        )
    ).scalar_one()
    return max(0.0, _round_usd(float(total)))


async def list_recent_credit_entries(
    db: AsyncSession,
    *,
    user_id: UUID,
    limit: int = _LEDGER_RECENT_LIMIT,
) -> list[UsageLedgerEntry]:
    """Return newest-first ledger entries for bootstrap/settings surfaces."""
    stmt = (
        select(UsageCreditLedger)
        .where(UsageCreditLedger.user_id == user_id)
        .order_by(desc(UsageCreditLedger.created_at), desc(UsageCreditLedger.id))
        .limit(max(0, limit))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_ledger_entry(row) for row in rows]


async def list_credit_entries_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> list[UsageLedgerEntry]:
    """Return the full signed credit ledger for account export."""
    stmt = (
        select(UsageCreditLedger)
        .where(UsageCreditLedger.user_id == user_id)
        .order_by(UsageCreditLedger.created_at.asc(), UsageCreditLedger.id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_ledger_entry(row) for row in rows]


async def _debit_platform_credits_unlocked(
    db: AsyncSession,
    *,
    user_id: UUID,
    amount_usd: float,
    description: str | None = "Platform model usage",
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> UsageCreditLedger | None:
    """Debit available credits for platform-model usage.

    Debits are capped at the current positive balance so the available-credit
    ledger does not go negative when a single post-paid turn overshoots the
    remaining balance. The overshoot is still captured by `usage_rollup`.
    """
    requested = _round_usd(amount_usd)
    if requested <= 0:
        return None
    balance = await get_credit_balance(db, user_id=user_id)
    debit = min(requested, balance)
    if debit <= 0:
        return None
    return await add_credit_entry(
        db,
        user_id=user_id,
        entry_type="platform_debit",
        amount_usd=-debit,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
    )


async def debit_platform_credits(
    db: AsyncSession,
    *,
    user_id: UUID,
    amount_usd: float,
    description: str | None = "Platform model usage",
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> UsageCreditLedger | None:
    """Debit platform credits under the per-user accounting lock."""
    lock = _usage_lock_for(user_id)
    async with lock:
        await _lock_user_for_usage_update(db, user_id=user_id)
        return await _debit_platform_credits_unlocked(
            db,
            user_id=user_id,
            amount_usd=amount_usd,
            description=description,
            reference_type=reference_type,
            reference_id=reference_id,
        )


async def _increment_for_period_unlocked(
    db: AsyncSession,
    *,
    user_id: UUID,
    used_delta: int = 1,
    cost_usd_delta: float = 0.0,
    is_byok: bool = False,
    period_start: datetime | None = None,
    monthly_quota_usd: float = 0.0,
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> None:
    """Upsert the (user_id, period_start) rollup row, bumping `used` + cost.

    Atomic `INSERT ... ON CONFLICT DO UPDATE` keyed on the composite primary
    key `(user_id, period_start)`. Two concurrent terminals for the same
    period both go through one statement; the DB serializes the conflict so
    the final `used` reflects every write. `is_byok` last-write-wins (column
    is analytics-only -- see module docstring).

    `cost_usd_delta` accumulates alongside `used` on the same atomic upsert so
    the cost ledger stays in lockstep with the per-turn counter. Defaults to
    0.0 so existing callers (and the integer-only meter) are unchanged.

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
    previous_cost = await get_period_cost(db, user_id=user_id, period_start=period)
    cost_delta = _round_usd(cost_usd_delta)

    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    if dialect == "postgresql":
        stmt_pg = pg_insert(UsageRollup).values(
            user_id=user_id,
            period_start=period,
            used=used_delta,
            cost_usd=cost_delta,
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
                "cost_usd": UsageRollup.cost_usd + stmt_pg.excluded.cost_usd,
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
            cost_usd=cost_delta,
            limit_value=_DEFAULT_LIMIT,
            is_byok=is_byok,
        )
        stmt_sq = stmt_sq.on_conflict_do_update(
            index_elements=["user_id", "period_start"],
            set_={
                "used": UsageRollup.used + stmt_sq.excluded.used,
                "cost_usd": UsageRollup.cost_usd + stmt_sq.excluded.cost_usd,
                "is_byok": stmt_sq.excluded.is_byok,
            },
        )
        await db.execute(stmt_sq)

    if monthly_quota_usd > 0 and cost_delta > 0 and not is_byok:
        previous_overage = max(0.0, previous_cost - monthly_quota_usd)
        next_overage = max(0.0, previous_cost + cost_delta - monthly_quota_usd)
        credit_debit = _round_usd(next_overage - previous_overage)
        await _debit_platform_credits_unlocked(
            db,
            user_id=user_id,
            amount_usd=credit_debit,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    await db.flush()


async def increment_for_period(
    db: AsyncSession,
    *,
    user_id: UUID,
    used_delta: int = 1,
    cost_usd_delta: float = 0.0,
    is_byok: bool = False,
    period_start: datetime | None = None,
    monthly_quota_usd: float = 0.0,
    reference_type: str | None = None,
    reference_id: str | None = None,
) -> None:
    """Serialize and record a usage-rollup increment plus any credit debit."""
    lock = _usage_lock_for(user_id)
    async with lock:
        await _lock_user_for_usage_update(db, user_id=user_id)
        await _increment_for_period_unlocked(
            db,
            user_id=user_id,
            used_delta=used_delta,
            cost_usd_delta=cost_usd_delta,
            is_byok=is_byok,
            period_start=period_start,
            monthly_quota_usd=monthly_quota_usd,
            reference_type=reference_type,
            reference_id=reference_id,
        )


async def get_period_cost(
    db: AsyncSession,
    *,
    user_id: UUID,
    period_start: datetime | None = None,
) -> float:
    """Return the accumulated USD cost for the current (or given) period.

    Reads the `(user_id, period_start)` rollup row's `cost_usd`. Returns 0.0
    when no row exists yet (first turn of the period). Drives the cost-based
    budget gate in `send_message`.
    """
    period = period_start if period_start is not None else _month_start()
    stmt = select(UsageRollup).where(
        UsageRollup.user_id == user_id,
        UsageRollup.period_start == period,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return float(row.cost_usd) if row is not None else 0.0


async def get_platform_remaining_usd(
    db: AsyncSession,
    *,
    user_id: UUID,
    monthly_quota_usd: float,
    period_start: datetime | None = None,
) -> float | None:
    """Return remaining platform allowance from quota plus available credits.

    `monthly_quota_usd <= 0` preserves the existing "budget disabled" mode and
    returns None. Otherwise the allowance is current quota remainder plus the
    positive credit balance. The next turn is still post-paid, so enforcement
    is best-effort just like the existing monthly cap.
    """
    if monthly_quota_usd <= 0:
        return None
    period_cost = await get_period_cost(
        db,
        user_id=user_id,
        period_start=period_start,
    )
    credit_balance = await get_credit_balance(db, user_id=user_id)
    quota_remaining = max(0.0, monthly_quota_usd - period_cost)
    return quota_remaining + credit_balance


async def has_platform_allowance(
    db: AsyncSession,
    *,
    user_id: UUID,
    monthly_quota_usd: float,
) -> bool:
    """Whether a platform-key turn may start under quota + credits."""
    remaining = await get_platform_remaining_usd(
        db,
        user_id=user_id,
        monthly_quota_usd=monthly_quota_usd,
    )
    return remaining is None or remaining > 0


async def get_current_budget(
    db: AsyncSession,
    user_id: UUID,
    is_byok: bool,
    monthly_quota_usd: float = 0.0,
    user_budget_usd: float | None = None,
) -> UsageBudget:
    """Return the current month's rollup as a FE-shape `UsageBudget`.

    `is_byok` reflects the caller's current key state, not the rollup row's
    historical flag -- the column is analytics-only (see plan §"UsageBudget
    semantics"). Returns the default-zero budget when no row exists for the
    period yet.

    `user_budget_usd` is the user's own monthly cap (from preferences). The
    effective enforced cap is the LOWER of it and the operator quota
    (`monthly_quota_usd`); `platform_remaining_usd` is computed against that
    effective cap so the FE meter reflects the limit actually enforced.
    """
    period = _month_start()
    stmt = select(UsageRollup).where(
        UsageRollup.user_id == user_id,
        UsageRollup.period_start == period,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    used = int(row.used) if row is not None else 0
    limit = int(row.limit_value) if row is not None else _DEFAULT_LIMIT
    monthly_spend_usd = float(row.cost_usd) if row is not None else 0.0
    credit_balance_usd = await get_credit_balance(db, user_id=user_id)
    effective = _effective_quota_usd(monthly_quota_usd, user_budget_usd)
    platform_remaining_usd = (
        _round_usd(max(0.0, effective - monthly_spend_usd) + credit_balance_usd)
        if effective > 0
        else None
    )
    recent_entries = await list_recent_credit_entries(db, user_id=user_id)
    return UsageBudget(
        used=used,
        limit=limit,
        period_label=_DEFAULT_PERIOD,
        is_byok=is_byok,
        monthly_spend_usd=_round_usd(monthly_spend_usd),
        monthly_quota_usd=_round_usd(monthly_quota_usd),
        credit_balance_usd=credit_balance_usd,
        platform_remaining_usd=platform_remaining_usd,
        user_budget_usd=user_budget_usd,
        effective_quota_usd=effective or None,
        recent_ledger_entries=recent_entries,
    )


async def list_rollups_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[UsageRollup]:
    """Return all persisted usage periods for account export."""
    stmt = (
        select(UsageRollup)
        .where(UsageRollup.user_id == user_id)
        .order_by(UsageRollup.period_start.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
