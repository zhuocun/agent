"""Tag repository (Conversation Org v2).

Thin async data-access over `Tag`. All reads/writes are scoped to a `user_id`
so a tag can never leak across users — the same caller-scoping the projects repo
uses. Tags are thin user-scoped labels: list/get/create/update/delete back the
`/api/tags` CRUD surface, and the assigned tag ids ride along on conversation
summaries / bodies.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationTag, Tag


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[Tag]:
    """Return the caller's tags, name-ordered. Scoped to `user_id`."""
    stmt = (
        select(Tag)
        .where(Tag.user_id == user_id)
        .order_by(Tag.name.asc(), Tag.id.asc())
    )
    return (await db.execute(stmt)).scalars().all()


async def get_for_user(
    db: AsyncSession,
    *,
    tag_id: UUID,
    user_id: UUID,
) -> Tag | None:
    """Return one tag by id IFF it belongs to `user_id`, else None."""
    stmt = select(Tag).where(
        Tag.id == tag_id,
        Tag.user_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    color: str | None = None,
) -> Tag:
    row = Tag(user_id=user_id, name=name, color=color)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


class _Unset:
    """Sentinel distinguishing "don't touch" from an explicit `None`.

    `color` is nullable and `None` is meaningful ("clear the color"), so a
    default of `None` could not also mean "leave the column unchanged." A PATCH
    that omits `color` must leave it alone; a PATCH that sends `null` must clear
    it.
    """


_UNSET = _Unset()


async def update_for_user(
    db: AsyncSession,
    *,
    tag_id: UUID,
    user_id: UUID,
    name: str | None = None,
    color: str | None | _Unset = _UNSET,
) -> Tag | None:
    """Update an owned tag. Returns the refreshed row, or None if not owned.

    `name` uses `None` as "don't touch" (it is non-nullable, so a clear is
    meaningless). `color` is three-valued via the `_UNSET` sentinel: omitted
    leaves the column unchanged; an explicit `None` clears it. `updated_at` is
    touched manually (no onupdate hook).
    """
    row = await get_for_user(db, tag_id=tag_id, user_id=user_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if not isinstance(color, _Unset):
        row.color = color
    row.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(row)
    return row


async def delete_for_user(
    db: AsyncSession,
    *,
    tag_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a tag. Returns True if a row was removed, False if not owned.

    The `conversation_tag` join rows referencing this tag have `tag_id` ON DELETE
    CASCADE on Postgres, but SQLite (tests) does not enforce FK cascades, so we
    remove the assignment rows explicitly first — idempotent on Postgres, where
    the CASCADE also fires. Scoped to `user_id` so a forged id can never delete
    another user's tag (returns False instead).
    """
    row = await get_for_user(db, tag_id=tag_id, user_id=user_id)
    if row is None:
        return False
    # Explicit join cleanup for cross-dialect safety (SQLite doesn't enforce the
    # CASCADE). The tag is owned (checked above), so the join rows are this
    # user's too.
    await db.execute(
        sa_delete(ConversationTag).where(ConversationTag.tag_id == tag_id)
    )
    await db.delete(row)
    await db.flush()
    return True
