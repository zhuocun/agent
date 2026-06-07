"""Shared low-level repository helpers.

Thin wrappers around the ``db.flush() -> db.refresh()`` and
``get-then-delete`` sequences that every user-scoped CRUD repository repeats.
Keeping them here avoids four+ identical copies across ``tags``,
``projects``, ``memory_facts``, and ``prompt_templates``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

_T = TypeVar("_T", bound=Base)


async def flush_and_refresh(db: AsyncSession, row: _T) -> _T:
    """Flush pending changes and refresh *row* from the DB.

    Used after ``db.add(row)`` (create) or attribute mutations (update) to
    ensure server-side defaults (``id``, ``created_at``) are populated.
    """
    await db.flush()
    await db.refresh(row)
    return row


async def get_owned(
    db: AsyncSession,
    model: type[_T],
    *,
    row_id: UUID,
    user_id: UUID,
) -> _T | None:
    """Return one row by PK IFF its ``user_id`` matches, else ``None``.

    Expects the model to have ``id`` and ``user_id`` mapped columns -- true for
    every user-scoped entity in this codebase (Tag, Project, MemoryFact,
    PromptTemplate, ...).
    """
    stmt = select(model).where(
        model.id == row_id,  # type: ignore[attr-defined]
        model.user_id == user_id,  # type: ignore[attr-defined]
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def delete_owned(
    db: AsyncSession,
    model: type[Base],
    *,
    row_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a user-owned row. Returns ``True`` if removed, ``False`` if not found.

    Fetches first (via :func:`get_owned`) so the ORM cascade machinery and any
    before-delete hooks fire -- matching the existing repo convention.
    """
    row = await get_owned(db, model, row_id=row_id, user_id=user_id)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True


async def touch_updated_at(db: AsyncSession, row: Base) -> None:
    """Stamp ``row.updated_at`` to now and flush.

    Columns in this codebase use ``server_default`` but no ``onupdate`` hook,
    so mutations must set the timestamp explicitly.
    """
    row.updated_at = datetime.now(UTC)  # type: ignore[attr-defined]
    await db.flush()
