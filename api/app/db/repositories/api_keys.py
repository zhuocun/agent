"""api_key repository (M0 only needs the existence check for `isByok`)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiKey


async def user_has_any_key(db: AsyncSession, user_id: UUID) -> bool:
    stmt = select(ApiKey.id).where(ApiKey.user_id == user_id).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none() is not None
