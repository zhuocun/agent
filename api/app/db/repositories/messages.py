"""Message repository (M0: declared, used in M1).

Placeholder so route modules in M1+ can import a stable surface without
breaking M0's `mypy --strict` check.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message


async def get_by_id(db: AsyncSession, message_id: UUID) -> Message | None:
    stmt = select(Message).where(Message.id == message_id)
    return (await db.execute(stmt)).scalar_one_or_none()
