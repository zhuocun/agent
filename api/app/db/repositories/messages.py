"""Message repository.

M1 needs:
- `create_user_message` — persists the user turn on `submitted`.
- `create_assistant_message` — persists the assistant turn on `terminal` or
  on disconnect (with `status="stopped"`).
- `get_by_client_message_id` — drives idempotency replay.
- `load_history` — feeds the provider with the prior turns.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message
from app.providers.protocol import ChatMessage as ProviderChatMessage


async def get_by_id(db: AsyncSession, message_id: UUID) -> Message | None:
    stmt = select(Message).where(Message.id == message_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_by_client_message_id(
    db: AsyncSession,
    conversation_id: UUID,
    client_message_id: UUID,
) -> Message | None:
    """Look up a user message by its `(conversation_id, client_message_id)`.

    The unique constraint `message_client_msg_uniq` guarantees at most one row.
    Returns None if no prior submission for this client id.
    """
    stmt = select(Message).where(
        Message.conversation_id == conversation_id,
        Message.client_message_id == client_message_id,
        Message.role == "user",
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_user_message(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    client_message_id: UUID,
    text: str,
) -> Message:
    """Persist a user turn. Returns the row with `id` and `created_at` set."""
    msg = Message(
        conversation_id=conversation_id,
        client_message_id=client_message_id,
        role="user",
        parts=[{"type": "text", "text": text}],
        status=None,
        attribution=None,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def create_assistant_message(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    parts: list[dict[str, Any]],
    status: str,
    attribution: dict[str, Any],
) -> Message:
    """Persist an assistant turn. `status` is `"done"` or `"stopped"`."""
    msg = Message(
        conversation_id=conversation_id,
        client_message_id=None,
        role="assistant",
        parts=parts,
        status=status,
        attribution=attribution,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def load_history(
    db: AsyncSession,
    conversation_id: UUID,
    before_assistant_id: UUID | None = None,
) -> list[ProviderChatMessage]:
    """Return prior turns as ProviderChatMessages, ordered by creation.

    `before_assistant_id` is reserved for M2 (regenerate/edit truncation);
    M1 always passes None. When set, returns history strictly before that
    assistant message's `created_at`.
    """
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    if before_assistant_id is not None:
        anchor = next((r for r in rows if r.id == before_assistant_id), None)
        if anchor is not None:
            rows = [r for r in rows if r.created_at < anchor.created_at]

    history: list[ProviderChatMessage] = []
    for row in rows:
        if row.role not in ("user", "assistant"):
            continue
        # Flatten parts into text. M1 only emits text + reasoning; reasoning
        # is internal-only and shouldn't be replayed to the provider.
        text_chunks: list[str] = []
        parts = row.parts or []
        for part in parts:
            if part.get("type") == "text":
                text_chunks.append(str(part.get("text", "")))
        if not text_chunks:
            continue
        role = cast(Any, row.role)  # narrowed by the role check above
        history.append(ProviderChatMessage(role=role, text="".join(text_chunks)))
    return history
