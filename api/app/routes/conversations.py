"""Conversation routes.

M0: `GET /api/conversations/:id`.
M1: `POST /api/conversations` (create), `POST /api/conversations/:id/messages`
    (the streaming endpoint).
M2: `PATCH/DELETE /api/conversations/:id`; `regenerate` and `editMessageId`
    paths in `send_message`; title autogen via fire-and-forget asyncio task.

Temporary chats are tracked in a module-level `_TEMP_IDS` dict keyed by user.
This is in-process state — multi-worker prod will need Redis or a signed-
cookie token (M2+). Documented as M1-only.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.auth.dependency import current_user
from app.db.models import Message, User
from app.db.repositories import api_keys as api_keys_repo
from app.db.repositories import conversations as conversations_repo
from app.db.repositories import messages as messages_repo
from app.db.session import get_db
from app.errors import AppError, ErrorEnvelope, not_found
from app.providers.factory import build_provider
from app.providers.protocol import ChatMessage as ProviderChatMessage
from app.providers.tiers import get_binding
from app.schemas.conversation import Conversation as ConversationSchema
from app.schemas.conversation import (
    CreateConversationRequest,
    PatchConversationRequest,
    SendMessageRequest,
)
from app.schemas.message import ModelAttribution
from app.schemas.stream_events import (
    AnswerDeltaEvent,
    SubmittedEvent,
    TerminalEvent,
)
from app.streaming.handler import stream_and_persist
from app.streaming.sse import (
    encode_answer_delta,
    encode_submitted,
    encode_terminal,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# Multi-worker note: this dict only lives in one process. Behind multiple
# uvicorn workers, a temporary chat created on worker A and posted to from
# worker B will 404. M2 may swap this for Redis or a signed-cookie token.
_TEMP_IDS: dict[UUID, set[UUID]] = defaultdict(set)


def _eventsource_response(*args: Any, **kwargs: Any) -> EventSourceResponse:
    """Construct an EventSourceResponse with `no-store` (not `no-cache`).

    sse-starlette ships a default `Cache-Control: no-cache` header and some
    versions do not let the constructor `headers=` arg override it cleanly.
    Post-mutating `response.headers` after construction is reliable.
    """
    r = EventSourceResponse(*args, **kwargs)
    r.headers["Cache-Control"] = "no-store"
    r.headers["X-Accel-Buffering"] = "no"
    return r


def _invalid_input(code: str, body: str) -> AppError:
    return AppError(
        ErrorEnvelope(
            code=code,
            severity="error",
            title="Invalid input",
            body=body,
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _duplicate_in_flight() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="DUPLICATE_IN_FLIGHT",
            severity="error",
            title="Duplicate request",
            body="A prior submission with this clientMessageId is still in flight.",
        ),
        status.HTTP_409_CONFLICT,
    )


@router.get("/{conversation_id}", response_model=ConversationSchema)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    convo = await conversations_repo.get_for_user(db, conversation_id, user.id)
    if convo is None:
        raise not_found("conversation")
    return convo


@router.post(
    "",
    response_model=ConversationSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: CreateConversationRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    if get_binding(body.selected_tier_id) is None:
        raise _invalid_input("INVALID_TIER", f"Unknown tier id {body.selected_tier_id!r}.")

    if body.is_temporary:
        synthetic_id = uuid4()
        _TEMP_IDS[user.id].add(synthetic_id)
        return ConversationSchema(
            id=str(synthetic_id),
            title="New chat",
            messages=[],
            selected_tier_id=body.selected_tier_id,
            is_temporary=True,
        )

    convo = await conversations_repo.create_for_user(
        db,
        user_id=user.id,
        selected_tier_id=body.selected_tier_id,
    )
    return ConversationSchema(
        id=str(convo.id),
        title=convo.title,
        messages=[],
        selected_tier_id=body.selected_tier_id,
        is_temporary=False,
    )


@router.patch("/{conversation_id}", response_model=ConversationSchema)
async def patch_conversation(
    conversation_id: UUID,
    body: PatchConversationRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    """Rename and/or pin the conversation. Returns the full updated body so the
    FE avoids a follow-up GET.

    Empty patch (`{}` or all-nulls) -> 400 INVALID_INPUT. Not-owned -> 404.
    """
    patch_dict = body.model_dump(exclude_unset=True)
    # Reject `{}` AND `{"title": null, "pinned": null}` — both are no-ops.
    # `exclude_unset` keeps explicit nulls in the dict (they ARE "set"), so a
    # plain truthiness check would let `{title: null, pinned: null}` slip
    # through to `update_for_user`, which would only bump `updated_at`.
    if not any(v is not None for v in patch_dict.values()):
        raise _invalid_input(
            "INVALID_INPUT", "PATCH body must include at least one of: title, pinned."
        )
    updated_row = await conversations_repo.update_for_user(
        db,
        conversation_id,
        user.id,
        title=body.title,
        pinned=body.pinned,
    )
    if updated_row is None:
        raise not_found("conversation")
    # Re-fetch with messages — keeps response shape identical to GET. The patch
    # itself was just a header/pin/title change; messages list won't churn.
    convo = await conversations_repo.get_for_user(db, conversation_id, user.id)
    if convo is None:  # pragma: no cover — would only fire on a concurrent DELETE
        raise not_found("conversation")
    return convo


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete the conversation. Idempotent.

    Idempotency choice: DELETE on a missing (or not-owned) id still returns 204.
    This matches the plan's "Idempotent." wording and lets the FE delete twice
    without surfacing a spurious "not found" toast on the second call. The
    cascade (`message` -> `vote`) is enforced by the FK in the migration.

    Note: anonymous + temporary conversations live in an in-process set; they
    don't have DB rows, but the FE still calls DELETE on them when the user
    drops a temp chat. We silently treat that as 204 — `_TEMP_IDS.discard()`
    cleans up the synthetic id if it was ours.
    """
    if _is_temp_for_user(user.id, conversation_id):
        _TEMP_IDS[user.id].discard(conversation_id)
        return None
    await conversations_repo.delete_for_user(db, conversation_id, user.id)
    return None


def _is_temp_for_user(user_id: UUID, conversation_id: UUID) -> bool:
    return conversation_id in _TEMP_IDS.get(user_id, set())


async def _maybe_replay(
    db: AsyncSession,
    conversation_id: UUID,
    client_uuid: UUID,
) -> EventSourceResponse | None:
    """If a prior user message + completed assistant row exist, return a replay.

    Returns the SSE replay response when the prior turn's assistant row is
    `status in ("done", "stopped")`. Returns None when no prior user message
    exists at all (so the caller can proceed to INSERT). Raises
    DUPLICATE_IN_FLIGHT (409) if the user row exists but no assistant row has
    landed yet (in-flight on a concurrent worker or crashed before persist).
    """
    prior_user_msg = await messages_repo.get_by_client_message_id(db, conversation_id, client_uuid)
    if prior_user_msg is None:
        return None
    # Pair-by-index matching. M1 has exactly one assistant per user message
    # (no regenerate yet), so pairing the i-th user message with the i-th
    # assistant by `(created_at, id)` ordering is reliable even when SQLite
    # TIMESTAMP storage collapses same-second inserts into ties. M2 will need
    # a stricter linking column (e.g. `responds_to_message_id`).
    all_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    all_msgs = (await db.execute(all_stmt)).scalars().all()
    user_msgs = [m for m in all_msgs if m.role == "user"]
    asst_msgs = [m for m in all_msgs if m.role == "assistant"]
    user_index = next(
        (i for i, m in enumerate(user_msgs) if m.id == prior_user_msg.id),
        None,
    )
    assistant_row = (
        asst_msgs[user_index] if user_index is not None and user_index < len(asst_msgs) else None
    )
    # Gate replay on `status` rather than `attribution is not None`. A
    # `status="stopped"` row also has attribution (an estimate), but the
    # original turn never emitted `terminal`. We replay both done and stopped —
    # for stopped, the client sees the same partial text + a terminal carrying
    # the stored `costConfidence="estimate"` attribution. From the wire's
    # perspective this is a regular replay; the FE does not currently render
    # the done/stopped distinction.
    if assistant_row is not None and assistant_row.status in ("done", "stopped"):
        # Defensive: `attribution` is a nullable column. A done/stopped row with
        # `attribution IS NULL` (manually-seeded or partially-migrated) would
        # raise inside `_replay_response`'s `ModelAttribution.model_validate(...)`
        # → generic 500. Fall through to a fresh insert instead of replaying.
        if assistant_row.attribution is None:
            return None
        # Replay path. Reconstruct prior answer text from parts.
        texts: list[str] = []
        for part in cast(list[dict[str, object]], assistant_row.parts or []):
            if part.get("type") == "text":
                texts.append(str(part.get("text", "")))
        return _replay_response(
            user_message_id=prior_user_msg.id,
            assistant_message_id=assistant_row.id,
            answer_text="".join(texts),
            attribution_dict=cast(dict[str, object], assistant_row.attribution),
        )
    # User message exists but no completed assistant row: prior is in flight
    # (or crashed before persisting). Reject as duplicate.
    raise _duplicate_in_flight()


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Stream a turn. SSE response.

    Implementation notes:
    - `regenerate=true`: drop the trailing assistant turn(s), keep the
      existing user message, re-stream against an unchanged history. New
      `clientMessageId` is required (FE generates a fresh one); the
      `submitted` event echoes the EXISTING user message's id so the FE
      keeps the same user bubble.
    - `editMessageId=<uuid>`: truncate at that message (exclusive of nothing
      — the user message at that id is deleted along with everything after).
      Insert a new user message with the request body's `text` +
      `clientMessageId` at the truncation point, then re-stream.
    - Idempotency: if a prior assistant message exists for this
      `(conversation_id, client_message_id)`, replay it as one frame.
      Regenerate / edit by definition use a NEW clientMessageId so this
      branch should never hit on those paths.
    - Ownership: 404 if the conversation isn't owned by the caller (and isn't
      a known temporary id for them).
    - Unknown tier: 400.
    - Mutual exclusion: `regenerate=true` AND `editMessageId` set in the same
      body is 400 INVALID_INPUT (semantically incoherent).
    """
    # Tier validation.
    binding = get_binding(body.tier_id)
    if binding is None:
        raise _invalid_input("INVALID_TIER", f"Unknown tier id {body.tier_id!r}.")

    # client_message_id must be a UUID.
    try:
        client_uuid = UUID(body.client_message_id)
    except ValueError as exc:
        raise _invalid_input("INVALID_INPUT", "clientMessageId must be a UUID.") from exc

    # M2: regenerate and editMessageId are mutually exclusive.
    if body.regenerate and body.edit_message_id is not None:
        raise _invalid_input(
            "INVALID_INPUT",
            "regenerate and editMessageId cannot both be set.",
        )

    is_temp = body.is_temporary or _is_temp_for_user(user.id, conversation_id)

    # Regenerate / edit are not meaningful for temporary chats (no prior
    # rows to drop / truncate). Reject so the FE doesn't silently degrade.
    if is_temp and (body.regenerate or body.edit_message_id is not None):
        raise _invalid_input(
            "INVALID_INPUT",
            "regenerate / editMessageId are not supported on temporary chats.",
        )

    # Ownership / existence check.
    if not is_temp:
        owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
        if owner_row is None:
            raise not_found("conversation")

    # Idempotency: prior user message for this client_message_id?
    # Skipped for regenerate / edit paths — those use a fresh clientMessageId
    # by FE contract; on the off chance an old id is reused, we still want
    # the regen/edit semantics over a stale replay.
    if not is_temp and not body.regenerate and body.edit_message_id is None:
        replay = await _maybe_replay(db, conversation_id, client_uuid)
        if replay is not None:
            return replay

    # Branch by mode:
    #   regenerate -> drop trailing assistant(s), reuse existing user message
    #   editMessageId -> truncate from that user message inclusive, insert new
    #   default -> existing M1 path
    user_message_id: UUID
    history: list[ProviderChatMessage]
    provider_user_text: str

    if body.regenerate:
        user_message_id, history, provider_user_text = await _prepare_regenerate(
            db=db,
            conversation_id=conversation_id,
        )
    elif body.edit_message_id is not None:
        user_message_id, history, provider_user_text = await _prepare_edit(
            db=db,
            conversation_id=conversation_id,
            edit_message_id_str=body.edit_message_id,
            client_uuid=client_uuid,
            new_text=body.text,
        )
    elif is_temp:
        user_message_id = uuid4()
        history = []
        provider_user_text = body.text
    else:
        history = await messages_repo.load_history(db, conversation_id)
        try:
            user_msg_row = await messages_repo.create_user_message(
                db=db,
                conversation_id=conversation_id,
                client_message_id=client_uuid,
                text=body.text,
            )
            # A new turn was accepted — bump the conversation so it rises in
            # the sidebar. Same session/transaction as the user message, so it
            # commits atomically with the turn below (not on idempotent replay,
            # which returns earlier without reaching this insert).
            await conversations_repo.touch_updated_at(db, conversation_id)
            # Commit so the user message is durable before we stream — the
            # EventSourceResponse will reuse this session, so flush+commit now.
            await db.commit()
        except IntegrityError:
            # Concurrent POSTs with the same clientMessageId can both pass the
            # idempotency check above and race on INSERT; one will lose to the
            # `message_client_msg_uniq` unique constraint. Roll back and retry
            # the replay path — if the winner has already produced an assistant
            # row, we replay it; otherwise return 409 DUPLICATE_IN_FLIGHT.
            await db.rollback()
            replay = await _maybe_replay(db, conversation_id, client_uuid)
            if replay is not None:
                return replay
            raise _duplicate_in_flight() from None
        user_message_id = user_msg_row.id
        provider_user_text = body.text

    provider = build_provider()

    # BYOK resolution: pull the user's encrypted key for the bound provider
    # (`binding.provider_id` — e.g. "anthropic" or "openai" depending on the
    # active backend). Anonymous users never have keys; decryption failure
    # inside the repo returns None (logged), so this is silently safe and the
    # call falls back to the platform key.
    resolved_api_key: str | None = None
    if not user.is_anonymous:
        resolved_api_key = await api_keys_repo.get_decrypted_for_user(
            db, user_id=user.id, provider=binding.provider_id
        )

    # Title autogen must not re-fire when a regen / edit-of-first-turn deletes
    # the prior assistant(s) and leaves count_assistant_messages at 0. Gate it
    # explicitly on "this is a fresh send" so the handler can require BOTH
    # conditions before scheduling the detached autogen task.
    is_initial = not body.regenerate and body.edit_message_id is None

    async def _event_stream() -> AsyncIterator[ServerSentEvent]:
        async for sse_event in stream_and_persist(
            request=request,
            db=db,
            provider=provider,
            binding=binding,
            requested_tier_id=body.tier_id,
            conversation_id=None if is_temp else conversation_id,
            user_message_id=user_message_id,
            user_text=provider_user_text,
            history=history,
            is_temporary=is_temp,
            is_initial=is_initial,
            user_id=user.id,
            api_key=resolved_api_key,
        ):
            yield sse_event

    return _eventsource_response(
        _event_stream(),
        media_type="text/event-stream",
    )


async def _prepare_regenerate(
    *,
    db: AsyncSession,
    conversation_id: UUID,
) -> tuple[UUID, list[ProviderChatMessage], str]:
    """Drop trailing assistant(s) and reuse the existing trailing user message.

    Returns `(user_message_id, history, user_text)` for the stream call. The
    returned `user_message_id` is the EXISTING trailing user message's id —
    `submitted` will echo it, the FE keeps the same user bubble. `user_text`
    is the original user message text (the body's `text` is ignored on
    regenerate per plan §"Behavior - Regenerate": user message not re-sent).
    """
    # Must have a trailing user message to regenerate against.
    last_user = await messages_repo.get_last_user_message(db, conversation_id)
    if last_user is None:
        raise _invalid_input(
            "INVALID_INPUT",
            "Cannot regenerate: no prior user message in this conversation.",
        )
    # Drop trailing assistant(s). Returns 0 if the last message is already a
    # user message (no assistant to drop) — that's still a valid regen (e.g.
    # a prior turn was stopped mid-stream and never persisted assistant).
    await messages_repo.delete_trailing_assistants(db, conversation_id=conversation_id)
    # Regenerate accepts a new turn (reusing the existing user message), so
    # bump the conversation to the top of the sidebar. Same session as the
    # trailing-assistant delete; commits atomically with the turn below.
    await conversations_repo.touch_updated_at(db, conversation_id)
    await db.commit()
    # Load history with the trailing assistant(s) gone, then strip the
    # trailing user message — the provider receives prior turns only, plus
    # `user_text` as the current submission.
    full_history = await messages_repo.load_history(db, conversation_id)
    # Trailing user message lives at the end of full_history now; pop it.
    user_text = ""
    if full_history and full_history[-1].role == "user":
        user_text = full_history[-1].text
        full_history = full_history[:-1]
    # Fallback: trust the persisted parts if history flattening lost data.
    if not user_text:
        parts = cast(list[dict[str, object]], last_user.parts or [])
        chunks: list[str] = []
        for part in parts:
            if part.get("type") == "text":
                chunks.append(str(part.get("text", "")))
        user_text = "".join(chunks)
    return last_user.id, full_history, user_text


async def _prepare_edit(
    *,
    db: AsyncSession,
    conversation_id: UUID,
    edit_message_id_str: str,
    client_uuid: UUID,
    new_text: str,
) -> tuple[UUID, list[ProviderChatMessage], str]:
    """Truncate at the edit target and insert a replacement user message.

    Returns `(new_user_message_id, history, user_text)` for the stream call.
    Validates that `editMessageId` parses as a UUID, exists in this
    conversation, and has `role="user"`. Truncation deletes the target row
    AND every row after it; the new user row is inserted with the request's
    `clientMessageId` + `text`.
    """
    try:
        edit_uuid = UUID(edit_message_id_str)
    except ValueError as exc:
        raise _invalid_input("INVALID_INPUT", "editMessageId must be a UUID.") from exc

    # Look up the target message and assert role / conversation membership.
    target = await messages_repo.get_by_id(db, edit_uuid)
    if target is None or target.conversation_id != conversation_id:
        raise _invalid_input(
            "INVALID_INPUT",
            "editMessageId does not reference a message in this conversation.",
        )
    if target.role != "user":
        raise _invalid_input(
            "INVALID_INPUT",
            "editMessageId must reference a user message.",
        )

    # Truncate at the target (inclusive) — drops the user message AND
    # every message that came after it.
    await messages_repo.truncate_from(
        db,
        conversation_id=conversation_id,
        message_id=edit_uuid,
    )
    # Load history BEFORE inserting the new user message — the provider
    # gets prior turns only, plus `user_text` as the current submission.
    history = await messages_repo.load_history(db, conversation_id)
    # Insert the replacement user message at the truncation point.
    try:
        new_row = await messages_repo.create_user_message(
            db=db,
            conversation_id=conversation_id,
            client_message_id=client_uuid,
            text=new_text,
        )
        # Edit-and-rerun accepts a new turn, so bump the conversation to the
        # top of the sidebar. Same session as the replacement user message;
        # commits atomically with the turn below.
        await conversations_repo.touch_updated_at(db, conversation_id)
        await db.commit()
    except IntegrityError as exc:
        # An edit submission with a clientMessageId that collides with an
        # already-existing user row is an error: the FE must mint a fresh id.
        await db.rollback()
        raise _invalid_input(
            "INVALID_INPUT",
            "clientMessageId already exists in this conversation.",
        ) from exc
    return new_row.id, history, new_text


def _replay_response(
    *,
    user_message_id: UUID,
    assistant_message_id: UUID,
    answer_text: str,
    attribution_dict: dict[str, object],
) -> EventSourceResponse:
    """Replay a prior terminal as a single combined frame.

    Plan §"Behavior - Idempotency": yields `submitted` with the prior user
    message id, one `answer_delta` carrying the full prior answer text, then
    `terminal` with the stored attribution. No new DB writes.
    """
    attribution = ModelAttribution.model_validate(attribution_dict)

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        yield encode_submitted(SubmittedEvent(message_id=str(user_message_id)))
        # Single answer_delta carrying the full final text (no mid-stream resume).
        yield encode_answer_delta(AnswerDeltaEvent(text=answer_text))
        yield encode_terminal(
            TerminalEvent(
                message_id=str(assistant_message_id),
                attribution=attribution,
            )
        )
        # Yield to the event loop so the response actually streams in tests.
        await asyncio.sleep(0)

    return _eventsource_response(
        _gen(),
        media_type="text/event-stream",
    )
