"""Conversation routes.

M0: `GET /api/conversations/:id`.
M1: `POST /api/conversations` (create), `POST /api/conversations/:id/messages`
    (the streaming endpoint).

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
from app.db.repositories import conversations as conversations_repo
from app.db.repositories import messages as messages_repo
from app.db.session import get_db
from app.errors import AppError, ErrorEnvelope, not_found
from app.providers.factory import build_provider
from app.providers.protocol import ChatMessage as ProviderChatMessage
from app.providers.tiers import get_binding
from app.schemas.conversation import Conversation as ConversationSchema
from app.schemas.conversation import CreateConversationRequest, SendMessageRequest
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


def _not_implemented(code: str, body: str) -> AppError:
    return AppError(
        ErrorEnvelope(
            code=code,
            severity="error",
            title="Not implemented",
            body=body,
        ),
        status.HTTP_501_NOT_IMPLEMENTED,
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
    prior_user_msg = await messages_repo.get_by_client_message_id(
        db, conversation_id, client_uuid
    )
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
        asst_msgs[user_index]
        if user_index is not None and user_index < len(asst_msgs)
        else None
    )
    # Gate replay on `status` rather than `attribution is not None`. A
    # `status="stopped"` row also has attribution (an estimate), but the
    # original turn never emitted `terminal`. We replay both done and stopped —
    # for stopped, the client sees the same partial text + a terminal carrying
    # the stored `costConfidence="estimate"` attribution. From the wire's
    # perspective this is a regular replay; the FE does not currently render
    # the done/stopped distinction.
    if assistant_row is not None and assistant_row.status in ("done", "stopped"):
        # Replay path. Reconstruct prior answer text from parts.
        texts: list[str] = []
        for part in cast(list[dict[str, object]], assistant_row.parts or []):
            if part.get("type") == "text":
                texts.append(str(part.get("text", "")))
        return _replay_response(
            user_message_id=prior_user_msg.id,
            assistant_message_id=assistant_row.id,
            answer_text="".join(texts),
            attribution_dict=cast(
                dict[str, object], assistant_row.attribution
            ),
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
    - 501 on `regenerate=true` or `editMessageId` (M2 features).
    - Idempotency: if a prior assistant message exists for this
      `(conversation_id, client_message_id)`, replay it as one frame.
    - Ownership: 404 if the conversation isn't owned by the caller (and isn't
      a known temporary id for them).
    - Unknown tier: 400.
    """
    # M2 feature gating.
    if body.regenerate:
        raise _not_implemented("NOT_IMPLEMENTED", "regenerate is not implemented yet.")
    if body.edit_message_id is not None:
        raise _not_implemented(
            "NOT_IMPLEMENTED", "editMessageId is not implemented yet."
        )

    # Tier validation.
    binding = get_binding(body.tier_id)
    if binding is None:
        raise _invalid_input("INVALID_TIER", f"Unknown tier id {body.tier_id!r}.")

    # client_message_id must be a UUID.
    try:
        client_uuid = UUID(body.client_message_id)
    except ValueError as exc:
        raise _invalid_input(
            "INVALID_INPUT", "clientMessageId must be a UUID."
        ) from exc

    is_temp = body.is_temporary or _is_temp_for_user(user.id, conversation_id)

    # Ownership / existence check.
    if not is_temp:
        owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
        if owner_row is None:
            raise not_found("conversation")

    # Idempotency: prior user message for this client_message_id?
    if not is_temp:
        replay = await _maybe_replay(db, conversation_id, client_uuid)
        if replay is not None:
            return replay

    # Persist the user message (skipped for temporary). Load history BEFORE
    # the new user message is persisted — the provider gets the prior turns
    # only; the just-submitted user_text is passed separately.
    user_message_id: UUID
    history: list[ProviderChatMessage]
    if is_temp:
        user_message_id = uuid4()
        history = []
    else:
        history = await messages_repo.load_history(db, conversation_id)
        try:
            user_msg_row = await messages_repo.create_user_message(
                db=db,
                conversation_id=conversation_id,
                client_message_id=client_uuid,
                text=body.text,
            )
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

    provider = build_provider()

    async def _event_stream() -> AsyncIterator[ServerSentEvent]:
        async for sse_event in stream_and_persist(
            request=request,
            db=db,
            provider=provider,
            binding=binding,
            requested_tier_id=body.tier_id,
            conversation_id=None if is_temp else conversation_id,
            user_message_id=user_message_id,
            user_text=body.text,
            history=history,
            is_temporary=is_temp,
        ):
            yield sse_event

    return _eventsource_response(
        _event_stream(),
        media_type="text/event-stream",
    )


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
