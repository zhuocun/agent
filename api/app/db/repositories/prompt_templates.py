"""Prompt-template repository (prompt library + user-authored templates, D23).

Thin async data-access over `PromptTemplate`. All reads/writes are scoped to a
`user_id` so a template can never leak across users. The library backs the
`/api/account/prompt-templates` CRUD surface; selecting a template prefills the
composer (a pure composer prefill — no model/cost/provider change).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PromptTemplate
from app.db.repositories._helpers import delete_owned, flush_and_refresh, get_owned


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[PromptTemplate]:
    """Return the caller's templates, newest-first. Scoped to `user_id`."""
    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.user_id == user_id)
        .order_by(PromptTemplate.created_at.desc(), PromptTemplate.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


async def get_for_user(
    db: AsyncSession,
    *,
    template_id: UUID,
    user_id: UUID,
) -> PromptTemplate | None:
    """Return one template by id IFF it belongs to `user_id`, else None."""
    return await get_owned(db, PromptTemplate, row_id=template_id, user_id=user_id)


async def add(
    db: AsyncSession,
    *,
    user_id: UUID,
    title: str,
    body: str,
    description: str | None = None,
) -> PromptTemplate:
    row = PromptTemplate(
        user_id=user_id,
        title=title,
        body=body,
        description=description,
    )
    db.add(row)
    return await flush_and_refresh(db, row)


async def update(
    db: AsyncSession,
    *,
    template_id: UUID,
    user_id: UUID,
    title: str,
    body: str,
    description: str | None,
) -> PromptTemplate | None:
    """Edit a template. Returns the updated row, or None if not owned."""
    row = await get_for_user(db, template_id=template_id, user_id=user_id)
    if row is None:
        return None
    row.title = title
    row.body = body
    row.description = description
    row.updated_at = datetime.now(UTC)
    return await flush_and_refresh(db, row)


async def delete(
    db: AsyncSession,
    *,
    template_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a template. Returns True if removed, False if not owned."""
    return await delete_owned(db, PromptTemplate, row_id=template_id, user_id=user_id)
