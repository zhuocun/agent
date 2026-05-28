"""Vote repository.

M2 ships feedback endpoints. The `vote` table has one row per (assistant)
message: `feedback ∈ {"up", "down"}`. The wire `Feedback | null` shape means
"null" deletes any existing row — there is no `none` value in storage.

Ownership is enforced at the route layer via the conversation join (a vote
belongs to a message belongs to a conversation belongs to a user).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, Vote
from app.schemas.common import Feedback


async def get_for_message(db: AsyncSession, message_id: UUID) -> Vote | None:
    stmt = select(Vote).where(Vote.message_id == message_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def message_owned_by(
    db: AsyncSession, message_id: UUID, user_id: UUID
) -> Message | None:
    """Return the message ORM row iff it belongs to a conversation owned by user.

    Used by the feedback route for ownership-check (one query joining message +
    conversation, so the 404 path is a single round-trip).
    """
    stmt = (
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.id == message_id, Conversation.user_id == user_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def upsert(db: AsyncSession, message_id: UUID, feedback: Feedback) -> None:
    """Insert-or-update the vote row for `message_id`.

    Implemented as `select -> update | insert` for cross-dialect support. SQLite
    has `INSERT ... ON CONFLICT DO UPDATE` but the Postgres dialect's
    `insert(...).on_conflict_do_update(...)` requires the `postgresql` dialect;
    a portable repo-level upsert keeps the model migration-clean for tests.
    """
    existing = await get_for_message(db, message_id)
    if existing is None:
        db.add(Vote(message_id=message_id, feedback=feedback))
    else:
        existing.feedback = feedback
    await db.flush()


async def clear(db: AsyncSession, message_id: UUID) -> None:
    """Delete any vote row for `message_id`. Idempotent (no-op if none)."""
    await db.execute(delete(Vote).where(Vote.message_id == message_id))
    await db.flush()
