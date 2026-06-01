"""Write-only audit-event repository.

Routes may append sensitive account events and account export may include the
caller's own prior events. There is deliberately no general read route.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent


async def record(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    row = AuditEvent(
        user_id=user_id,
        event_type=event_type,
        details=details or {},
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[AuditEvent]:
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.user_id == user_id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
