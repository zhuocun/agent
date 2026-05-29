"""Stream repository (PRD 04 §5.1).

Durable lifecycle of a streaming turn. One row per non-temporary streaming
turn: created `active` when the turn starts, transitioned to `done` /
`stopped` / `error` by the handler, and intent-marked `stopped` by the
dedicated stop endpoint.

The in-process stop *signal* lives in `app.streaming.stop_registry`; this
module is the durable record. Keep the two in sync at the call sites (the
handler / stop route), not here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Stream


async def create_stream(
    db: AsyncSession,
    *,
    conversation_id: UUID,
) -> Stream:
    """Insert an `active` stream row for the conversation. Flush + refresh."""
    row = Stream(
        conversation_id=conversation_id,
        status="active",
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def mark_status(
    db: AsyncSession,
    *,
    stream_id: UUID,
    status: str,
    message_id: UUID | None = None,
) -> None:
    """Set `status` (and optionally `message_id`) + bump `updated_at`. Flush.

    Silent no-op if the row is gone. `message_id` is only written when a
    non-None value is passed so a later status transition doesn't clobber a
    pointer set by an earlier one.
    """
    stmt = select(Stream).where(Stream.id == stream_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    row.status = status
    if message_id is not None:
        row.message_id = message_id
    row.updated_at = datetime.now(UTC)
    await db.flush()


async def get_active_for_conversation(
    db: AsyncSession,
    *,
    conversation_id: UUID,
) -> Stream | None:
    """Return the newest `active` stream row for the conversation, else None."""
    stmt = (
        select(Stream)
        .where(
            Stream.conversation_id == conversation_id,
            Stream.status == "active",
        )
        .order_by(Stream.created_at.desc(), Stream.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
