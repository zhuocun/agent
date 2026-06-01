"""First-party analytics event repository.

Events are deliberately small, structured, and user-owned. Callers pass only
non-content metadata; this repository enforces the user's telemetry preference
before writing unless explicitly told otherwise.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent, Preferences


async def telemetry_enabled(db: AsyncSession, user_id: UUID) -> bool:
    stmt = select(Preferences.telemetry_enabled).where(Preferences.user_id == user_id)
    value = (await db.execute(stmt)).scalar_one_or_none()
    return True if value is None else bool(value)


async def record(
    db: AsyncSession,
    *,
    user_id: UUID,
    event_type: str,
    properties: dict[str, Any] | None = None,
    respect_opt_out: bool = True,
) -> AnalyticsEvent | None:
    if respect_opt_out and not await telemetry_enabled(db, user_id):
        return None
    row = AnalyticsEvent(
        user_id=user_id,
        event_type=event_type,
        properties=properties or {},
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def record_once_per_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    event_type: str,
    properties: dict[str, Any] | None = None,
    respect_opt_out: bool = True,
) -> AnalyticsEvent | None:
    if respect_opt_out and not await telemetry_enabled(db, user_id):
        return None
    row = AnalyticsEvent(
        user_id=user_id,
        event_type=event_type,
        properties=properties or {},
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        return None
    return row


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[AnalyticsEvent]:
    stmt = (
        select(AnalyticsEvent)
        .where(AnalyticsEvent.user_id == user_id)
        .order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
