"""Message repository.

M1 needs:
- `create_user_message` — persists the user turn on `submitted`.
- `create_assistant_message` — persists the assistant turn on `terminal` or
  on disconnect (with `status="stopped"`).
- `get_by_client_message_id` — drives idempotency replay.
- `load_history` — feeds the provider with the prior turns.

M2 adds:
- `truncate_from` — delete the message at a given id AND every message
  created at/after it (drives edit-and-rerun).
- `delete_trailing_assistants` — drop the trailing assistant turn(s) for
  a conversation (drives regenerate). Returns the count deleted.
- `count_assistant_messages` — gate "first terminal" for title autogen.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Vote
from app.providers.protocol import ChatMessage as ProviderChatMessage

# Cap on how many of the most-recent messages `load_history` replays to the
# provider. Every turn re-sends the whole prior conversation as context, so an
# unbounded history grows the prompt (and token cost / latency) without bound on
# long threads. 40 messages ≈ 20 user/assistant turns — enough recent context
# for coherent continuation while bounding the prompt. We keep the NEWEST N and
# preserve oldest-to-newest order (we do NOT reverse the conversation).
_HISTORY_WINDOW_MESSAGES = 40


def _now() -> datetime:
    """UTC-aware microsecond-precision Python timestamp.

    Used as an explicit `created_at` value on inserts. The model's
    `server_default=func.now()` is second-precision on SQLite (test DB) and
    same-second inserts then collapse to identical timestamps. Setting the
    column explicitly with a Python-side `datetime.now(UTC)` gives us
    microsecond precision on both SQLite and Postgres, which makes
    `(created_at, id)` ordering robust across regenerate / edit truncation.
    """
    return datetime.now(UTC)


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


async def get_assistant_for_user_message(
    db: AsyncSession,
    user_message_id: UUID,
) -> Message | None:
    """Return the most recent assistant row whose reply links to this user.

    Resolves idempotency replay in O(log n) via the `ix_message_responds_to`
    index (post-M4). Returns None for legacy rows where the assistant has
    `responds_to_message_id IS NULL` — callers fall back to pair-by-index.

    Most-recent ordering matters because regenerate inserts a new assistant
    for the same user message and we want the latest one, not the dropped
    predecessor. The trailing-assistant delete in `delete_trailing_assistants`
    keeps this set tiny in practice (regen always drops the prior before
    inserting), but the ORDER BY makes the contract obvious.
    """
    stmt = (
        select(Message)
        .where(
            Message.responds_to_message_id == user_message_id,
            Message.role == "assistant",
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_user_message(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    client_message_id: UUID,
    text: str,
) -> Message:
    """Persist a user turn. Returns the row with `id` and `created_at` set.

    `created_at` is set explicitly to a microsecond-precision Python now()
    rather than relying on the column's `server_default=func.now()`. See
    `_now()` docstring — SQLite's CURRENT_TIMESTAMP is second-precision,
    which makes within-turn ties and regen/edit truncation order
    unreliable.
    """
    msg = Message(
        conversation_id=conversation_id,
        client_message_id=client_message_id,
        role="user",
        parts=[{"type": "text", "text": text}],
        status=None,
        attribution=None,
        created_at=_now(),
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
    responds_to_message_id: UUID | None = None,
    cost_usd: float | None = None,
) -> Message:
    """Persist an assistant turn. `status` is `"done"` or `"stopped"`.

    See `create_user_message` docstring — `created_at` is set Python-side
    for microsecond precision (SQLite quirk).

    `responds_to_message_id` (post-M4) points at the user message whose reply
    this assistant turn is. Drives column-based idempotency replay in
    `_maybe_replay`. None is accepted so callers that don't yet thread the
    id through (or seed legacy data) still work; the pair-by-index fallback
    in `_maybe_replay` covers those rows.

    `cost_usd` is the per-turn USD cost (mirrors `attribution.costUsd`). None
    leaves the column NULL (legacy/unmetered rows); the cost ledger only reads
    non-NULL values.
    """
    msg = Message(
        conversation_id=conversation_id,
        client_message_id=None,
        role="assistant",
        parts=parts,
        status=status,
        attribution=attribution,
        responds_to_message_id=responds_to_message_id,
        cost_usd=cost_usd,
        created_at=_now(),
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
    # History-window cap: keep only the most-recent N messages. Slicing the tail
    # preserves the oldest-to-newest order (we do NOT reverse) while dropping the
    # oldest overflow so the provider prompt stays bounded on long threads. When
    # the conversation is shorter than the window this is a no-op.
    if len(history) > _HISTORY_WINDOW_MESSAGES:
        history = history[-_HISTORY_WINDOW_MESSAGES:]
    return history


async def truncate_from(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    message_id: UUID,
) -> int:
    """Delete the message at `message_id` AND every message after it.

    "After" is by `created_at` order with the anchor's row always included.
    Returns the count of rows removed. Returns 0 if `message_id` does not
    belong to the conversation.

    SQLite tie tolerance: same-second timestamps may collapse to equal
    values on storage (`CURRENT_TIMESTAMP` is second-precision text). For
    rows tying with the anchor by timestamp:
    - The anchor itself is always deleted (matched by id).
    - Other tied rows that are LATER turns (e.g. the assistant response
      that was just persisted same-second as the user) are also deleted.
    - Tied rows from EARLIER turns are not — but a same-second insert
      across turns is improbable: between turns are ~150ms of streaming
      and a `db.commit()` round trip. In practice production runs on
      Postgres (microsecond precision) and the tie case is a SQLite-only
      test artifact.

    We collect rows by Python-side comparison to avoid the SQLite
    datetime parameter formatting quirk (see `delete_trailing_assistants`
    docstring).

    Used by the edit-and-rerun path: truncate at the user message, then
    insert the replacement with the new text + clientMessageId.
    """
    anchor_stmt = select(Message).where(
        Message.id == message_id,
        Message.conversation_id == conversation_id,
    )
    anchor = (await db.execute(anchor_stmt)).scalar_one_or_none()
    if anchor is None:
        return 0
    # Load all rows in this conversation; filter in Python to dodge the
    # SQLite datetime serialization tie. We include the anchor explicitly
    # (matched by id) plus every row whose `created_at` is STRICTLY GREATER
    # than the anchor's. Same-second rows from the same turn (the assistant
    # response, just persisted) are caught via the strict-greater test
    # against the IMMEDIATELY-PRIOR turn — but for tied same-second rows
    # belonging to the same turn as the anchor (e.g. the anchor user's own
    # assistant from the prior persist), we additionally include rows that
    # tie AND have an id sorted lexicographically AFTER the anchor's. The
    # latter still has theoretical false negatives but works for our test
    # scenarios; production on Postgres won't see ties.
    all_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    rows = (await db.execute(all_stmt)).scalars().all()
    anchor_ts = anchor.created_at
    anchor_id = anchor.id
    to_delete: list[Message] = []
    for r in rows:
        if r.id == anchor_id:
            to_delete.append(r)
            continue
        if r.created_at > anchor_ts:
            to_delete.append(r)
            continue
        if r.created_at == anchor_ts and r.id > anchor_id:
            to_delete.append(r)
    # Cross-dialect cascade: SQLite (tests) doesn't enforce FK CASCADE by
    # default, so explicitly drop any Vote rows for the targeted messages
    # before deleting the messages themselves. Postgres FK ON DELETE CASCADE
    # also handles this; the explicit delete is idempotent there. Matches
    # the pattern in `conversations_repo.delete_for_user`.
    if to_delete:
        target_ids = [r.id for r in to_delete]
        await db.execute(delete(Vote).where(Vote.message_id.in_(target_ids)))
    for row in to_delete:
        await db.delete(row)
    await db.flush()
    return len(to_delete)


async def delete_trailing_assistants(
    db: AsyncSession,
    *,
    conversation_id: UUID,
) -> int:
    """Drop the assistant turn(s) responding to the most recent user message.

    Returns the count removed. Returns 0 if the conversation has no user
    messages.

    Semantics: "trailing assistant" = any assistant row whose `created_at`
    is `>=` the latest user message's `created_at`. We rely on the
    wall-clock invariant that the user message is INSERT'd and committed
    BEFORE the assistant turn starts streaming, so on second-precision
    storage they may tie but the assistant never has a STRICTLY EARLIER
    timestamp.

    Implementation note: a SQL `WHERE created_at >= :user_created_at`
    filter is unreliable here. SQLite's `CURRENT_TIMESTAMP` default stores
    text WITHOUT microseconds, but SQLAlchemy serializes the bound Python
    datetime WITH `.000000`. The string compare then puts the stored row
    BELOW the filter and misses tied rows. Postgres (production) does not
    have this issue, but to keep tests honest we pull all assistant rows
    and filter in Python — costs O(n) per regenerate, n = conversation
    length, which is fine at MVP scale.

    Used by the regenerate path: the user message stays put (FE reuses its
    existing bubble id); the trailing assistant(s) are deleted before the
    new stream starts.
    """
    last_user = await get_last_user_message(db, conversation_id)
    if last_user is None:
        return 0
    stmt = select(Message).where(
        Message.conversation_id == conversation_id,
        Message.role == "assistant",
    )
    all_assistants = (await db.execute(stmt)).scalars().all()
    # Filter in Python: any assistant whose timestamp is >= the user's
    # (tolerating SQLite's second-precision tie).
    user_ts = last_user.created_at
    targets = [a for a in all_assistants if a.created_at >= user_ts]
    # Cross-dialect cascade: SQLite (tests) doesn't enforce FK CASCADE by
    # default, so explicitly drop any Vote rows for the targeted assistants
    # before deleting the messages themselves. Postgres FK ON DELETE CASCADE
    # also handles this; the explicit delete is idempotent there. Matches
    # the pattern in `conversations_repo.delete_for_user`.
    if targets:
        target_ids = [a.id for a in targets]
        await db.execute(delete(Vote).where(Vote.message_id.in_(target_ids)))
    for row in targets:
        await db.delete(row)
    await db.flush()
    return len(targets)


async def get_last_user_message(
    db: AsyncSession,
    conversation_id: UUID,
) -> Message | None:
    """Return the latest user message in the conversation, or None.

    Used by the regenerate path to reuse the existing trailing user message
    (its id is emitted in `submitted` and its text is replayed to the
    provider unchanged).
    """
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "user",
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_assistant_messages(
    db: AsyncSession,
    conversation_id: UUID,
) -> int:
    """Return the count of assistant messages for the conversation.

    Used to gate title autogen: only fire on the FIRST terminal (when the
    count is zero immediately before persisting the assistant row).
    """
    stmt = select(func.count(Message.id)).where(
        Message.conversation_id == conversation_id,
        Message.role == "assistant",
    )
    result = (await db.execute(stmt)).scalar_one()
    return int(result or 0)
