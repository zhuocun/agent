"""First-party analytics event repository.

Events are deliberately small, structured, and user-owned. Callers pass only
non-content metadata; this repository enforces the user's telemetry preference
before writing unless explicitly told otherwise.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent, Preferences
from app.schemas.analytics import (
    analytics_property_key_is_blocked,
    analytics_value_looks_sensitive,
)

_log = structlog.get_logger(__name__)

_MAX_PROPERTY_KEYS = 24
_MAX_PROPERTY_KEY_LENGTH = 80
_MAX_PROPERTY_VALUE_LENGTH = 160


async def telemetry_enabled(db: AsyncSession, user_id: UUID) -> bool:
    stmt = select(Preferences.telemetry_enabled).where(Preferences.user_id == user_id)
    value = (await db.execute(stmt)).scalar_one_or_none()
    return True if value is None else bool(value)


def clean_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    """Drop unsafe analytics properties rather than risking content retention."""
    if not properties:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in properties.items():
        if len(cleaned) >= _MAX_PROPERTY_KEYS:
            break
        if not isinstance(key, str) or len(key) > _MAX_PROPERTY_KEY_LENGTH:
            continue
        if analytics_property_key_is_blocked(key):
            continue
        if not isinstance(value, (str, int, float, bool, type(None))):
            continue
        if isinstance(value, str):
            if len(value) > _MAX_PROPERTY_VALUE_LENGTH:
                continue
            if analytics_value_looks_sensitive(value):
                continue
        cleaned[key] = value
    return cleaned


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
        properties=clean_properties(properties),
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
        properties=clean_properties(properties),
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        _log.debug(
            "analytics.duplicate_event",
            user_id=str(user_id),
            event_type=event_type,
        )
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
