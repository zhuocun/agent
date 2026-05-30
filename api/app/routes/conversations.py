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
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.auth.dependency import current_user
from app.config import get_settings
from app.db.models import Message, User
from app.db.repositories import api_keys as api_keys_repo
from app.db.repositories import conversations as conversations_repo
from app.db.repositories import messages as messages_repo
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.db.session import get_db
from app.errors import AppError, ErrorAction, ErrorEnvelope, not_found
from app.middleware.ratelimit import limiter
from app.providers.factory import build_provider
from app.providers.protocol import ChatMessage as ProviderChatMessage
from app.providers.router import route_auto
from app.providers.tiers import get_binding
from app.schemas.common import SubstitutionReasonCode
from app.schemas.conversation import Conversation as ConversationSchema
from app.schemas.conversation import (
    CreateConversationRequest,
    PatchConversationRequest,
    SendMessageRequest,
)
from app.schemas.message import ModelAttribution
from app.schemas.share import ShareLinkResponse
from app.schemas.stream_events import (
    AnswerDeltaEvent,
    SubmittedEvent,
    TerminalEvent,
)
from app.streaming import replay_registry
from app.streaming.handler import (
    _derive_session_factory,
    spawn_detached_producer,
    stream_and_persist,
)
from app.streaming.sse import (
    encode_answer_delta,
    encode_submitted,
    encode_terminal,
)
from app.streaming.stop_registry import request_stop

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


def _ms_until_next_month(now: datetime | None = None) -> int:
    """Milliseconds from `now` until the next calendar-month UTC start.

    Drives `retry_after_ms` on the budget envelope: the cost ledger resets when
    the period rolls over, so the FE can surface "try again next month". Clamped
    to >= 0 defensively (clock skew should never make this negative).
    """
    ref = now if now is not None else datetime.now(UTC)
    if ref.month == 12:
        nxt = ref.replace(
            year=ref.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        nxt = ref.replace(
            month=ref.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return max(0, int((nxt - ref).total_seconds() * 1000))


def _budget_exceeded() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="BUDGET_EXCEEDED",
            severity="warning",
            title="Usage limit reached",
            body="You've reached your usage budget for this period.",
            retry_after_ms=_ms_until_next_month(),
            actions=[ErrorAction(label="View usage", kind="open_settings")],
        ),
        status.HTTP_429_TOO_MANY_REQUESTS,
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


@router.post("/{conversation_id}/share", response_model=ShareLinkResponse)
async def create_share_link(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareLinkResponse:
    """Mint (or return the existing) public-by-link share token for the convo.

    Public-by-link is the explicit exception to cost transparency: a holder of
    the token reads the conversation + model attribution but NEVER per-message
    cost (see `GET /api/share/{token}` and `app.schemas.share`).

    - Ownership-checked: 404 (not 403) if the caller doesn't own the
      conversation, so the route never leaks that the id exists.
    - Idempotent: re-minting an already-shared conversation returns the SAME
      token (no rotation), so previously distributed links keep working.
    - Anonymous owners can share too — sharing is an ownership affordance, not a
      BYOK-gated one, so there's no `is_anonymous` gate here.
    - Temporary chats have no DB row, so they cannot be shared (treated as not
      owned -> 404).
    """
    if _is_temp_for_user(user.id, conversation_id):
        raise not_found("conversation")
    token = await conversations_repo.mint_share_token(db, conversation_id, user.id)
    if token is None:
        raise not_found("conversation")
    return ShareLinkResponse(share_token=token, share_path=f"/share/{token}")


@router.delete(
    "/{conversation_id}/share", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_share_link(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke the conversation's share token. Ownership-checked, idempotent.

    Clears `share_token` back to NULL so the previously minted public link
    404s. Revoking an unshared (or already-revoked) conversation is a 204 no-op.
    Not owned / missing (incl. temporary chats) -> 404, mirroring the rest of
    this router.
    """
    if _is_temp_for_user(user.id, conversation_id):
        raise not_found("conversation")
    revoked = await conversations_repo.revoke_share_token(db, conversation_id, user.id)
    if not revoked:
        raise not_found("conversation")
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

    Resolution strategy (post-M4):
    1. Column lookup via `responds_to_message_id` — an indexed seek that
       returns the assistant row whose explicit pointer matches the prior
       user message. Cheap and unambiguous.
    2. Pair-by-index fallback — for rows pre-dating the column (legacy data
       with `responds_to_message_id IS NULL`). Pairs the i-th user message
       with the i-th assistant by `(created_at, id)` ordering. M1 invariant
       of "one assistant per user message" still holds for legacy data, so
       the fallback is reliable for those rows.
    """
    prior_user_msg = await messages_repo.get_by_client_message_id(db, conversation_id, client_uuid)
    if prior_user_msg is None:
        return None

    # Primary path: column-based lookup. Indexed; O(log n).
    assistant_row = await messages_repo.get_assistant_for_user_message(
        db, prior_user_msg.id
    )

    # Fallback for legacy rows whose responds_to_message_id is NULL (data
    # written before the 0005 migration). Pair-by-index on the i-th user/i-th
    # assistant by (created_at, id) ordering.
    if assistant_row is None:
        all_stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        all_msgs = (await db.execute(all_stmt)).scalars().all()
        user_msgs = [m for m in all_msgs if m.role == "user"]
        # Only consider legacy (NULL pointer) assistants for the fallback so a
        # mixed conversation (some rows migrated, some not) doesn't double-
        # count an assistant we already failed to match above.
        asst_msgs = [
            m
            for m in all_msgs
            if m.role == "assistant" and m.responds_to_message_id is None
        ]
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
@limiter.limit(lambda: get_settings().rate_limit_messages)
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

    # BYOK resolution + budget gate. Resolved here (before any user-message
    # insert / branch logic) so the cost-based budget gate can tell whether
    # this is a platform-key turn (counts against the cap) or a BYOK turn (the
    # user pays their own provider, so it is exempt). The resolved value is
    # threaded through to `stream_and_persist` unchanged.
    #
    # BYOK: pull the user's encrypted key for the bound provider
    # (`binding.provider_id` — e.g. "anthropic" or "openai" depending on the
    # active backend). Anonymous users never have keys; decryption failure
    # inside the repo returns None (logged), so this is silently safe and the
    # call falls back to the platform key.
    resolved_api_key: str | None = None
    if not user.is_anonymous:
        resolved_api_key = await api_keys_repo.get_decrypted_for_user(
            db, user_id=user.id, provider=binding.provider_id
        )

    # Ownership / existence check.
    if not is_temp:
        owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
        if owner_row is None:
            raise not_found("conversation")

        # Cost-based budget enforcement. Only platform-key turns count against
        # the cap (BYOK turns are exempt — the user pays their own provider).
        # `usage_budget_usd <= 0` disables the cap entirely (the default), so
        # existing behavior is unchanged. The cap is read against the current
        # period's accumulated cost ledger; reaching it refuses the next turn.
        #
        # This gate is BEST-EFFORT / POST-HOC, not a hard ceiling at MVP: it
        # checks the already-accumulated cost before starting a turn, so the
        # current turn's own cost is unbounded by it (a single expensive turn
        # can push the period total past the cap before the NEXT turn is
        # refused), and concurrent in-flight turns can each pass the check then
        # accumulate, overshooting the cap (bounded by concurrency).
        settings = get_settings()
        if settings.usage_budget_usd > 0 and resolved_api_key is None:
            period_cost = await usage_repo.get_period_cost(db, user_id=user.id)
            if period_cost >= settings.usage_budget_usd:
                raise _budget_exceeded()

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

    # Auto-tier routing. When the user picked `auto`, run the v0 complexity
    # heuristic (providers/router.py) to choose the concrete tier that actually
    # serves + bills this turn. We rebind `binding` to the routed tier so:
    #   - pricing bills the model actually served (compute_cost_breakdown reads
    #     `binding`), and
    #   - `resolve_served_tier(binding)` surfaces a concrete served tier on the
    #     wire (the routed binding is fast/smart/pro, never `auto`).
    # `requested_tier_id` stays `auto` (threaded separately), so the FE still
    # shows the user requested Auto.
    #
    # Honest surfacing: when the routed tier is CHEAPER than the auto baseline
    # (`smart`), we set a router-side `auto_downgrade` substitution so the
    # downgrade is visible on the wire — never silent (PRD §2.2.4 / §7.4).
    # `auto_downgrade` is the only auto-routing reason code the FE renders
    # (web/src/lib/types.ts::SubstitutionReasonCode). Routing to baseline or
    # escalating above it emits no substitution. The router-side reason is the
    # SEED; a real provider fallback overwrites it inside the handler (provider
    # fallback wins precedence).
    router_substitution: SubstitutionReasonCode | None = None
    settings_for_routing = get_settings()
    if body.tier_id == "auto" and settings_for_routing.auto_routing_enabled:
        routed = route_auto(provider_user_text, history)
        routed_binding = get_binding(routed.tier_id, settings=settings_for_routing)
        # Defensive: a known concrete tier always has a binding; fall back to the
        # original `auto` binding rather than 500 if the registry ever diverges.
        if routed_binding is not None:
            binding = routed_binding
        if routed.is_downgrade:
            router_substitution = "auto_downgrade"

    # Durable stream lifecycle (PRD 04 §5.1). Persist an `active` stream row for
    # every NON-temporary turn (default / regenerate / edit). The id is threaded
    # into `stream_and_persist`, which transitions it to done / stopped / error
    # and links the assistant `message_id`. Temporary chats persist nothing, so
    # they get no stream row and pass `stream_id=None`. Committed now (its own
    # statement on the request session) so the row is visible to a concurrent
    # `POST /{id}/stop` before the turn finishes.
    stream_id: UUID | None = None
    if not is_temp:
        stream_row = await streams_repo.create_stream(
            db, conversation_id=conversation_id
        )
        stream_id = stream_row.id
        await db.commit()

    # `resolved_api_key` was resolved earlier (before the budget gate) so the
    # cost cap could distinguish platform-key vs BYOK turns; it is threaded
    # through to the stream call below unchanged.

    # Title autogen must not re-fire when a regen / edit-of-first-turn deletes
    # the prior assistant(s) and leaves count_assistant_messages at 0. Gate it
    # explicitly on "this is a fresh send" so the handler can require BOTH
    # conditions before scheduling the detached autogen task.
    is_initial = not body.regenerate and body.edit_message_id is None

    settings = get_settings()

    # Resumable-stream replay (flag ON, non-temporary turns only). Spawn the
    # provider pump as a DETACHED producer that survives this connection and
    # appends every wire event to an in-process ReplayBuffer; this POST then
    # SUBSCRIBES and tails the buffer. A client disconnect stops the tailing but
    # NOT the producer (the semantics inversion). Reconnects re-subscribe via
    # `GET .../stream/{stream_id}`. Temporary chats (no `stream_id`, nothing
    # persisted, nothing to reconnect to) always take the legacy inline path,
    # even with the flag on.
    if settings.resumable_streams_enabled and not is_temp and stream_id is not None:
        ttl = settings.resumable_buffer_ttl_seconds
        buffer = replay_registry.create(stream_id, ttl_seconds=ttl)
        # The detached producer owns a FRESH session derived from THIS request's
        # engine (the request session closes when the POST returns). Using
        # `_derive_session_factory(db)` keeps tests bound to the per-test SQLite
        # file rather than the process-wide env DATABASE_URL factory.
        spawn_detached_producer(
            buffer=buffer,
            session_factory=_derive_session_factory(db),
            provider=provider,
            binding=binding,
            requested_tier_id=body.tier_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            user_text=provider_user_text,
            history=history,
            is_temporary=is_temp,
            is_initial=is_initial,
            user_id=user.id,
            api_key=resolved_api_key,
            stream_id=stream_id,
            router_substitution=router_substitution,
        )

        async def _subscriber_stream() -> AsyncIterator[ServerSentEvent]:
            # Subscribe at offset 0 and tail. On client disconnect we simply
            # stop iterating (the generator is GC'd / aclosed) — the producer
            # keeps running and persisting. Subscribers NEVER persist.
            subscription = await buffer.subscribe()
            async for sse_event in subscription.events():
                if await request.is_disconnected():
                    return
                yield sse_event

        return _eventsource_response(
            _subscriber_stream(),
            media_type="text/event-stream",
        )

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
            stream_id=stream_id,
            router_substitution=router_substitution,
        ):
            yield sse_event

    return _eventsource_response(
        _event_stream(),
        media_type="text/event-stream",
    )


@router.get("/{conversation_id}/stream/{stream_id}")
async def reconnect_stream(
    conversation_id: UUID,
    stream_id: UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Re-attach to a live (or just-finished) resumable stream (PRD 04 §5.1 P1).

    Same-device replay: subscribe to the in-process ReplayBuffer for
    `stream_id`, replay every buffered event from the start, then tail live
    until the detached producer is `done`. If the stream already terminated but
    its buffer is still within TTL, replay the full final sequence then close.

    Gated behind `resumable_streams_enabled` — when the flag is OFF the feature
    is not exposed, so this 404s (feature disabled), matching the rest of the
    router's "never reveal that the id exists" stance.

    Ownership / IDOR (404, never 403):
    - Conversation not owned by the caller (or missing / temporary) → 404.
    - Stream row missing, or belonging to a DIFFERENT conversation → 404.
    - No live/within-TTL buffer for the stream (never started on this worker,
      or evicted past TTL) → 404. Multi-worker: a reconnect that lands on a
      different worker than the producer finds no buffer → 404 (see the
      `replay_registry` module + `resumable_streams_enabled` config caveat).
    """
    settings = get_settings()
    if not settings.resumable_streams_enabled:
        # Feature disabled — do not expose new behavior. 404, not 403.
        raise not_found("stream")

    # Ownership: the conversation must be owned by the caller. Temporary chats
    # have no DB row / stream and are not resumable, so they fall through to 404.
    if _is_temp_for_user(user.id, conversation_id):
        raise not_found("stream")
    owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
    if owner_row is None:
        raise not_found("stream")

    # The stream must exist AND belong to THIS conversation (block cross-convo
    # IDOR: a valid stream id from another of the user's conversations must not
    # leak here either).
    stream_row = await streams_repo.get_by_id(db, stream_id=stream_id)
    if stream_row is None or stream_row.conversation_id != conversation_id:
        raise not_found("stream")

    # Live (or within-TTL done) buffer for this stream on this worker?
    buffer = replay_registry.get(
        stream_id, ttl_seconds=settings.resumable_buffer_ttl_seconds
    )
    if buffer is None:
        raise not_found("stream")

    async def _replay_stream() -> AsyncIterator[ServerSentEvent]:
        # Replay from offset 0 then tail. Disconnect just stops tailing; the
        # producer (and any other subscribers) are unaffected. This subscriber
        # NEVER persists.
        subscription = await buffer.subscribe()
        async for sse_event in subscription.events():
            if await request.is_disconnected():
                return
            yield sse_event

    return _eventsource_response(
        _replay_stream(),
        media_type="text/event-stream",
    )


@router.post("/{conversation_id}/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_stream(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Dedicated server-side stop for an in-flight streaming turn (PRD 04 §5.1).

    P0 foundation for the P1 dedicated-stop / resumable-stream semantics. Today
    "stop" is implicit (the client closing the SSE socket -> the handler's
    `request.is_disconnected()` check); this endpoint makes it explicit and
    durable so a stop survives independent of the streaming connection.

    Mechanism (two halves, both best-effort):
    - Durable intent: mark the conversation's active `stream` row `stopped` so
      the lifecycle is observable even if the live signal never lands.
    - Live cancel: set the in-process stop signal (`request_stop`) so the
      running generator tears the turn down at its next poll. Single-worker
      only — behind multiple uvicorn workers a stop on worker A won't reach a
      stream running on worker B (same caveat as `_TEMP_IDS`). The actual
      generator cancellation is therefore best-effort.

    Idempotent 204:
    - No active stream (already finished / never started) -> 204, no-op.
    - Temporary conversations have no DB row and no stream row; treated as a
      204 no-op (nothing to stop, nothing persisted).
    - Not owned (or missing) -> 404, mirroring the rest of this router.
    """
    # Temporary chats: nothing persisted, nothing to stop. Idempotent 204.
    if _is_temp_for_user(user.id, conversation_id):
        return None

    owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
    if owner_row is None:
        raise not_found("conversation")

    active = await streams_repo.get_active_for_conversation(
        db, conversation_id=conversation_id
    )
    if active is not None:
        # Durable intent first, then the live signal. The running generator
        # (if on this worker) will observe `request_stop` at its next poll,
        # persist the partial assistant row, and transition the same stream row
        # to `stopped` itself — `mark_status` here records the intent up front
        # so a stop is durable even if the generator never sees the signal.
        request_stop(active.id)
        await streams_repo.mark_status(
            db, stream_id=active.id, status="stopped"
        )
        await db.commit()
    return None


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
