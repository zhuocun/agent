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
    stmt = select(PromptTemplate).where(
        PromptTemplate.id == template_id,
        PromptTemplate.user_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


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
    await db.flush()
    await db.refresh(row)
    return row


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
    # `updated_at` has no onupdate hook; touch it explicitly (mirrors the
    # memory-facts repo) so the column reflects the mutation time.
    row.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(row)
    return row


async def delete(
    db: AsyncSession,
    *,
    template_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a template. Returns True if removed, False if not owned."""
    row = await get_for_user(db, template_id=template_id, user_id=user_id)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True
