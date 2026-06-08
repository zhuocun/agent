"""Memory-fact repository (transparent long-term memory v1, D19).

Thin async data-access over `MemoryFact`. All reads/writes are scoped to a
`user_id` so a fact can never leak across users. The editable ledger is the
glass-box differentiator: list/add/edit/delete back the `/api/account/memory`
CRUD surface, and `list_for_injection` returns the content the streaming handler
folds into the user turn when memory is opt-in enabled.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MemoryFact

# Cap on facts injected into a single turn. Memory is wrapped into the user turn
# (no system-prompt seam in this codebase), so a runaway ledger must not blow out
# the prompt. Newest facts win when the ledger exceeds this.
INJECTION_LIMIT = 50


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[MemoryFact]:
    """Return the caller's facts, newest-first. Scoped to `user_id`."""
    stmt = (
        select(MemoryFact)
        .where(MemoryFact.user_id == user_id)
        .order_by(MemoryFact.created_at.desc(), MemoryFact.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


async def list_for_injection(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int = INJECTION_LIMIT,
) -> list[str]:
    """Return up to `limit` fact contents (oldest-first) for prompt injection.

    Oldest-first so the natural narrative order reads sensibly when wrapped into
    the turn; bounded by `limit` so a large ledger can't dominate the prompt.
    """
    stmt = (
        select(MemoryFact.content)
        .where(MemoryFact.user_id == user_id)
        .order_by(MemoryFact.created_at.asc(), MemoryFact.id.asc())
        .limit(limit)
    )
    return [row for row in (await db.execute(stmt)).scalars().all()]


async def list_for_injection_with_ids(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int = INJECTION_LIMIT,
) -> list[tuple[str, str]]:
    """Like `list_for_injection`, but returns `(id, content)` pairs.

    The id is stringified so callers can record the injected fact ids on the
    turn attribution (the FE links the "Memory used here" chip back to the
    exact ledger rows). Same oldest-first ordering and `limit` bound.
    """
    stmt = (
        select(MemoryFact.id, MemoryFact.content)
        .where(MemoryFact.user_id == user_id)
        .order_by(MemoryFact.created_at.asc(), MemoryFact.id.asc())
        .limit(limit)
    )
    return [(str(row[0]), row[1]) for row in (await db.execute(stmt)).all()]


async def count_for_user(db: AsyncSession, user_id: UUID) -> int:
    """Return the number of facts owned by `user_id` (for the per-user cap)."""
    stmt = select(func.count()).select_from(MemoryFact).where(MemoryFact.user_id == user_id)
    return int((await db.execute(stmt)).scalar_one())


async def get_for_user(
    db: AsyncSession,
    *,
    fact_id: UUID,
    user_id: UUID,
) -> MemoryFact | None:
    """Return one fact by id IFF it belongs to `user_id`, else None."""
    stmt = select(MemoryFact).where(
        MemoryFact.id == fact_id,
        MemoryFact.user_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def add(
    db: AsyncSession,
    *,
    user_id: UUID,
    content: str,
    source: str = "manual",
    source_conversation_id: UUID | None = None,
) -> MemoryFact:
    row = MemoryFact(
        user_id=user_id,
        content=content,
        source=source,
        source_conversation_id=source_conversation_id,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def update_content(
    db: AsyncSession,
    *,
    fact_id: UUID,
    user_id: UUID,
    content: str,
) -> MemoryFact | None:
    """Edit a fact's content. Returns the updated row, or None if not owned."""
    row = await get_for_user(db, fact_id=fact_id, user_id=user_id)
    if row is None:
        return None
    row.content = content
    # `updated_at` has no onupdate hook; touch it explicitly (mirrors the
    # preferences repo) so the column reflects the mutation time.
    row.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(row)
    return row


async def delete(
    db: AsyncSession,
    *,
    fact_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a fact. Returns True if a row was removed, False if not owned."""
    row = await get_for_user(db, fact_id=fact_id, user_id=user_id)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True
