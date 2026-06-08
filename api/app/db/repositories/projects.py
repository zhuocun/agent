"""Project/Space repository (D20).

Thin async data-access over `Project`. All reads/writes are scoped to a
`user_id` so a Project can never leak across users — the same caller-scoping the
memory-fact repo uses. Projects are thin scoping containers: list/get/add/update/
delete back the `/api/projects` CRUD surface, and the resolved settings
(default tier, retention, budget sub-cap, shared instructions) are read on the
send path to scope a conversation's behavior.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Project
from app.db.repositories._helpers import flush_and_refresh, get_owned
from app.db.repositories._sentinel import UNSET, _Unset


async def list_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Sequence[Project]:
    """Return the caller's projects, newest-first. Scoped to `user_id`."""
    stmt = (
        select(Project)
        .where(Project.user_id == user_id)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    return (await db.execute(stmt)).scalars().all()


async def get_for_user(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
) -> Project | None:
    """Return one project by id IFF it belongs to `user_id`, else None."""
    return await get_owned(db, Project, row_id=project_id, user_id=user_id)


async def add(
    db: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    custom_instructions: str | None = None,
    default_tier_id: str | None = None,
    retention_days: int | None = None,
    per_conversation_budget_usd: float | None = None,
) -> Project:
    row = Project(
        user_id=user_id,
        name=name,
        custom_instructions=custom_instructions,
        default_tier_id=default_tier_id,
        retention_days=retention_days,
        per_conversation_budget_usd=per_conversation_budget_usd,
    )
    db.add(row)
    return await flush_and_refresh(db, row)


async def update(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    name: str | None = None,
    custom_instructions: str | None | _Unset = UNSET,
    default_tier_id: str | None | _Unset = UNSET,
    retention_days: int | None | _Unset = UNSET,
    per_conversation_budget_usd: float | None | _Unset = UNSET,
) -> Project | None:
    """Update an owned project. Returns the refreshed row, or None if not owned.

    `name` uses `None` as "don't touch" (it is non-nullable, so a clear is
    meaningless). The four settings columns are three-valued via the `UNSET`
    sentinel: omitted leaves the column unchanged; an explicit `None` clears it
    back to inherit. `updated_at` is touched manually (no onupdate hook).
    """
    row = await get_for_user(db, project_id=project_id, user_id=user_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if not isinstance(custom_instructions, _Unset):
        row.custom_instructions = custom_instructions
    if not isinstance(default_tier_id, _Unset):
        row.default_tier_id = default_tier_id
    if not isinstance(retention_days, _Unset):
        row.retention_days = retention_days
    if not isinstance(per_conversation_budget_usd, _Unset):
        row.per_conversation_budget_usd = per_conversation_budget_usd
    row.updated_at = datetime.now(UTC)
    return await flush_and_refresh(db, row)


async def delete(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a project. Returns True if a row was removed, False if not owned.

    Conversations filed under the project have `project_id` SET NULL on the FK,
    so they are un-filed rather than deleted. SQLite (tests) does not enforce FK
    actions (no `PRAGMA foreign_keys=ON`), so we null the membership explicitly
    first — idempotent on Postgres, where the SET NULL FK also fires. Scoped to
    `user_id` so the un-file can only touch the owner's own conversations.
    """
    row = await get_for_user(db, project_id=project_id, user_id=user_id)
    if row is None:
        return False
    # Explicit un-file for cross-dialect safety (SQLite doesn't enforce SET NULL).
    await db.execute(
        sa_update(Conversation)
        .where(
            Conversation.project_id == project_id,
            Conversation.user_id == user_id,
        )
        .values(project_id=None)
    )
    await db.delete(row)
    await db.flush()
    return True
