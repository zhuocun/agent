"""Vote repository (M0: declared, used in M2)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Vote


async def get_for_message(db: AsyncSession, message_id: UUID) -> Vote | None:
    stmt = select(Vote).where(Vote.message_id == message_id)
    return (await db.execute(stmt)).scalar_one_or_none()
