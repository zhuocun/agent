"""Conversation repository.

M0 needs:
- list summaries for the sidebar (bootstrap)
- get a single conversation by id, scoped to the user
- get messages of a conversation (ordered by created_at)

M2 adds:
- `update_for_user` — patch title and/or pinned on an owned conversation.
- `delete_for_user` — delete an owned conversation. Cascades to messages/votes
  via the FK chain.
- `update_title` — single-field title write used by the title-autogen task
  (no user_id available at call site; the task already trusts that the
  conversation existed when the first terminal fired).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, Vote
from app.schemas.common import ModelTierId
from app.schemas.conversation import Conversation as ConversationSchema
from app.schemas.conversation import ConversationSummary
from app.schemas.message import ChatMessage, MessagePart
from app.schemas.share import PublicAttribution, PublicConversation, PublicMessage

# Share tokens are `secrets.token_urlsafe(_SHARE_TOKEN_BYTES)` — 24 random
# bytes => a 32-char URL-safe base64 string (~192 bits of entropy). Unguessable
# by brute force; the UNIQUE index on `conversation.share_token` is belt-and-
# braces against the astronomically unlikely collision.
_SHARE_TOKEN_BYTES = 24


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
            is_temporary=False,
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


async def update_for_user(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    *,
    title: str | None = None,
    pinned: bool | None = None,
) -> Conversation | None:
    """Update the owned conversation's title/pinned. None args mean "don't touch."

    Returns the refreshed ORM row, or None if the row isn't owned/doesn't exist.
    Bumps `updated_at` so the sidebar's pinned/updated ordering reflects the
    rename or pin/unpin.
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return None
    if title is not None:
        row.title = title
    if pinned is not None:
        row.pinned = pinned
    # Touch updated_at — the column has a server_default but no onupdate hook,
    # so we set it explicitly. Naive datetime is fine for SQLite tests; Postgres
    # accepts tz-aware values via TIMESTAMP(timezone=True).
    row.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(row)
    return row


async def touch_updated_at(
    db: AsyncSession,
    conversation_id: UUID,
) -> None:
    """Bump `updated_at` to now so the conversation rises in the sidebar.

    Called when a NEW turn is accepted (normal send, regenerate, edit) so the
    sidebar's `pinned desc, updated_at desc` ordering reflects activity, not
    just creation order. The column has a `server_default` but no `onupdate`
    hook, so we set it explicitly. Flush only — the caller commits in the same
    transaction that persists the turn's user message (atomic with the turn).

    Silent no-op if the row is gone (mirrors `update_title`). Distinct from
    `update_title`, which deliberately does NOT bump so title autogen alone
    can't reorder the sidebar.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    row.updated_at = datetime.now(UTC)
    await db.flush()


async def update_title(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    title: str,
) -> None:
    """Set `conversation.title`. Silent no-op if the row is gone.

    Used by the title-autogen detached task on the first terminal. The
    caller owns its own session and commit; we only mutate. Does not bump
    `updated_at` — title autogen is an implicit side effect of the same
    turn that already updated the row's children, so keeping the sidebar
    ordering stable is preferable.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    row.title = title
    await db.flush()


async def delete_for_user(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> bool:
    """Delete the owned conversation. Returns True if a row was deleted.

    Cascades to `message`; `vote` cascades transitively via the FK chain on
    Postgres. SQLite (test) doesn't enforce FK cascades by default (no
    `PRAGMA foreign_keys=ON`), so we issue explicit deletes for `vote` and
    `message` first. The Postgres path is unchanged in semantics — the
    explicit deletes are idempotent there too.
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return False
    # Manual cascade for cross-dialect safety. On Postgres the FK ON DELETE
    # CASCADE also fires; the explicit deletes here are idempotent.
    # vote -> message -> conversation deletion order matches the FK chain.
    msg_id_stmt = select(Message.id).where(Message.conversation_id == conversation_id)
    msg_ids = (await db.execute(msg_id_stmt)).scalars().all()
    if msg_ids:
        await db.execute(delete(Vote).where(Vote.message_id.in_(msg_ids)))
    await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await db.flush()
    return True


async def mint_share_token(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> str | None:
    """Mint (or return the existing) share token for an owned conversation.

    Idempotent: re-minting on an already-shared conversation returns the SAME
    token (no rotation) so existing links keep working. Returns None if the
    conversation isn't owned by the user (the route maps that to a 404 so the
    existence of the conversation never leaks).
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return None
    if row.share_token is None:
        row.share_token = secrets.token_urlsafe(_SHARE_TOKEN_BYTES)
        await db.flush()
    return row.share_token


async def revoke_share_token(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> bool:
    """Clear the share token on an owned conversation. Idempotent.

    Returns True if the conversation is owned (whether or not it was shared),
    False if it isn't owned / doesn't exist. Revoking an already-unshared
    conversation is a no-op that still returns True. Once cleared, the public
    GET on the old token 404s.
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return False
    if row.share_token is not None:
        row.share_token = None
        await db.flush()
    return True


async def get_public_by_share_token(
    db: AsyncSession, share_token: str
) -> PublicConversation | None:
    """Return the COST-STRIPPED public view for a share token, or None.

    Public-by-link: NO ownership / auth check. Looks the conversation up by its
    unique `share_token` and builds a `PublicConversation` that structurally
    cannot carry per-message cost (it uses `PublicMessage` / `PublicAttribution`
    which have no cost fields). Unknown / revoked token => None (the route 404s,
    never leaking which tokens once existed).
    """
    stmt = select(Conversation).where(Conversation.share_token == share_token)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None

    messages_stmt = (
        select(Message)
        .where(Message.conversation_id == row.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    message_rows = (await db.execute(messages_stmt)).scalars().all()

    messages: list[PublicMessage] = []
    for m in message_rows:
        parts_list = cast(list[MessagePart], m.parts) if m.parts is not None else []
        # Re-project attribution through PublicAttribution so ONLY model
        # identity survives — cost_usd / costConfidence / breakdown are dropped
        # because the public schema has no field to receive them.
        public_attribution: PublicAttribution | None = None
        if m.attribution is not None:
            attribution_dict = cast(dict[str, object], m.attribution)
            public_attribution = PublicAttribution.model_validate(attribution_dict)
        messages.append(
            PublicMessage.model_validate(
                {
                    "id": str(m.id),
                    "role": m.role,
                    "parts": parts_list,
                    "created_at": _iso(m.created_at),
                    "attribution": public_attribution,
                }
            )
        )

    return PublicConversation(
        id=str(row.id),
        title=row.title,
        messages=messages,
    )
