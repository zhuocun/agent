"""Conversation repository.

M0 needs:
- list summaries for the sidebar (bootstrap)
- get a single conversation by id, scoped to the user
- get messages of a conversation (ordered by created_at)

CRUD / mutations land in M1+ and are skeletoned out so the route layer can
import a stable surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message
from app.schemas.common import ModelTierId
from app.schemas.conversation import Conversation as ConversationSchema
from app.schemas.conversation import ConversationSummary
from app.schemas.message import ChatMessage, MessagePart


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _coerce_tier(tier_id: str) -> ModelTierId:
    if tier_id not in ("fast", "smart", "pro", "auto"):
        # Repositories return wire schemas; fall back to "auto" if the DB row
        # somehow holds an unknown tier id (defensive — M1 inserts validate).
        return "auto"
    return cast(ModelTierId, tier_id)


async def list_summaries_for_user(
    db: AsyncSession, user_id: UUID
) -> list[ConversationSummary]:
    """Return sidebar summaries: pinned desc, then updated_at desc."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.pinned.desc(), Conversation.updated_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        ConversationSummary(
            id=str(row.id),
            title=row.title,
            updated_at=_iso(row.updated_at),
            pinned=row.pinned,
        )
        for row in rows
    ]


async def create_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    selected_tier_id: ModelTierId,
) -> Conversation:
    """Persist a new conversation. Returns the row with id/timestamps set."""
    convo = Conversation(
        user_id=user_id,
        title="New chat",
        selected_tier_id=selected_tier_id,
        pinned=False,
    )
    db.add(convo)
    await db.flush()
    await db.refresh(convo)
    return convo


async def owned_by(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> Conversation | None:
    """Return the ORM row if owned by the user, else None.

    Lighter than `get_for_user` (no messages fetch). Used by routes that just
    need to assert ownership.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None
    return row


async def get_for_user(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> ConversationSchema | None:
    """Return the full conversation if owned by the user, else None.

    Ownership-not-found is indistinguishable from missing (callers raise 404).
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None

    messages_stmt = (
        select(Message)
        .where(Message.conversation_id == row.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    message_rows = (await db.execute(messages_stmt)).scalars().all()

    messages: list[ChatMessage] = []
    for m in message_rows:
        # parts and attribution come back as JSON dicts; let Pydantic validate.
        parts_list = cast(list[MessagePart], m.parts) if m.parts is not None else []
        chat_message = ChatMessage.model_validate(
            {
                "id": str(m.id),
                "role": m.role,
                "parts": parts_list,
                "created_at": _iso(m.created_at),
                "status": m.status,
                "attribution": m.attribution,
            }
        )
        messages.append(chat_message)

    return ConversationSchema(
        id=str(row.id),
        title=row.title,
        messages=messages,
        selected_tier_id=_coerce_tier(row.selected_tier_id),
        is_temporary=False,
    )
