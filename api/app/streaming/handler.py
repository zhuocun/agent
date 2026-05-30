"""Stream-and-persist orchestration.

Consumes `ProviderEvent`s and:
1. Yields wire SSE events (`submitted` → `reasoning_delta*` → `reasoning_done?`
   → `answer_delta*` → `terminal | error`).
2. Persists the assistant message on terminal (status=done) OR on client
   disconnect (status=stopped, costConfidence=estimate).
3. Skips ALL persistence when `is_temporary` is True.

Cancellation: the provider iteration runs inside an `asyncio.Task`; the
generator polls `request.is_disconnected()` between yields. On disconnect:
cancel the task, flush accumulators into parts, persist with `status=stopped`,
and exit WITHOUT yielding terminal (socket is already closed).

Per plan §"Streaming" invariant: exactly one `reasoning_done` precedes any
`answer_delta`. We track `_emitted_answer_delta` and `_emitted_reasoning_done`
to enforce this — if the provider yields an `AnswerDelta` before
`ReasoningDone` but after at least one `ReasoningDelta`, we emit
`ReasoningDone` first (defensive).

Title autogen: on the FIRST terminal of a conversation (count(role=assistant)
== 0 immediately before persistence), schedule a detached `asyncio.Task`
that calls `provider.complete(...)` on the small/fast tier and writes
`conversation.title`. Fire-and-forget — does NOT block the streaming
response. If the worker dies before the task completes, title stays "New
chat" until next turn fires the check again (plan §"Explicit non-features").
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import ServerSentEvent

from app.db.repositories import conversations as conversations_repo
from app.db.repositories import messages as messages_repo
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.db.session import get_session_factory
from app.errors import AppError, ErrorEnvelope
from app.providers.factory import build_provider
from app.providers.pricing import build_attribution, compute_cost_breakdown
from app.providers.protocol import (
    AnswerDelta,
    ChatMessage,
    Complete,
    Provider,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    UsageUpdate,
)
from app.providers.tiers import TierBinding, get_binding
from app.schemas.common import ModelTierId
from app.schemas.message import ModelAttribution
from app.schemas.stream_events import (
    AnswerDeltaEvent,
    ReasoningDeltaEvent,
    ReasoningDoneEvent,
    SubmittedEvent,
    TerminalEvent,
)
from app.streaming.sse import (
    encode_answer_delta,
    encode_error,
    encode_reasoning_delta,
    encode_reasoning_done,
    encode_submitted,
    encode_terminal,
)
from app.streaming.stop_registry import clear_stop, is_stop_requested

log = logging.getLogger(__name__)
_struct_log = structlog.get_logger(__name__)

# Detached background tasks (title autogen). `asyncio.create_task` only holds
# a weak reference to the returned Task; without a strong ref the task can
# be garbage-collected mid-flight under some event-loop policies. Keep a
# module-level strong-ref set and discard each entry in the done callback.
_BG_TASKS: set[asyncio.Task[None]] = set()


@dataclass(frozen=True)
class _PumpError:
    """Carries a provider exception from the pump task to the consumer.

    The pump drains the provider iterator on its own task; if the iterator
    raises mid-stream we must surface that to the consumer loop rather than
    swallow it. Enqueuing this sentinel lets the consumer re-raise the
    original exception so the top-level handler emits an `error` frame and
    skips persistence (plan §"Persistence": `error` does not persist).
    """

    exc: BaseException


def _derive_session_factory(
    db: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    """Build a sessionmaker pointing at the same engine as `db`.

    The detached title-autogen task needs a fresh session — the request
    scope is closing. We can't use `get_session_factory()` because in tests
    that's the process-wide factory bound to env DATABASE_URL, NOT the
    per-test SQLite file the request session was bound to.

    Falls back to `get_session_factory()` if the bind can't be extracted
    (defensive — should not happen in practice; `AsyncSession.bind`
    is an `AsyncEngine` once the session has executed anything).
    """
    bind = db.bind
    if bind is None:
        return get_session_factory()
    return async_sessionmaker(
        bind=bind,
        expire_on_commit=False,
        autoflush=False,
    )

# Prompt used for title autogen. Kept short — the small/fast tier sees the
# user's first turn plus this instruction and returns a 4-6 word title.
# Phrased as the user side of a single turn (no system prompt seam in our
# Protocol) so the provider treats it as a normal completion.
_TITLE_AUTOGEN_PROMPT = (
    "Summarize the following user message as a concise 4-6 word title. "
    "Return ONLY the title — no quotes, no punctuation at the end, no "
    "explanation.\n\nMessage: "
)


async def _autogen_title(
    *,
    conversation_id: UUID,
    user_text: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Detached task: call the fast tier, write `conversation.title`.

    Owns its own session (the request scope is already closed by the time
    this runs). The session factory is passed in by the caller so tests can
    point the task at the per-test SQLite file rather than the process-wide
    factory (which is built lazily from env DATABASE_URL — wrong in tests).

    Swallows all exceptions — title autogen is best-effort and must never
    propagate into the streaming response or leak as an unhandled task
    exception.
    """
    try:
        binding = get_binding("fast")
        if binding is None:
            # Registry misconfigured — log and bail. Title stays "New chat".
            log.warning("autogen_title.no_fast_binding")
            return
        provider = build_provider()
        title = await provider.complete(
            model_id=binding.model_id,
            history=[],
            user_text=_TITLE_AUTOGEN_PROMPT + user_text,
        )
        # Strip surrounding whitespace/quotes/trailing period defensively —
        # providers sometimes ignore "no quotes" instructions.
        cleaned = title.strip().strip('"').strip("'").rstrip(".")
        if not cleaned:
            log.warning("autogen_title.empty_response")
            return
        # Cap at a sane length so a runaway model can't blow out the column.
        cleaned = cleaned[:120]
        async with session_factory() as session:
            await conversations_repo.update_title(
                session,
                conversation_id=conversation_id,
                title=cleaned,
            )
            await session.commit()
    except Exception as exc:
        log.warning("autogen_title.failed", exc_info=exc)


async def stream_and_persist(
    *,
    request: Request,
    db: AsyncSession,
    provider: Provider,
    binding: TierBinding,
    requested_tier_id: ModelTierId,
    conversation_id: UUID | None,
    user_message_id: UUID,
    user_text: str,
    history: list[ChatMessage],
    is_temporary: bool,
    is_initial: bool = True,
    user_id: UUID | None = None,
    api_key: str | None = None,
    stream_id: UUID | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """Drive the provider, persist, yield wire SSE events.

    `conversation_id` is None for temporary chats — persistence is skipped.
    The caller MUST have already persisted the user message (or generated a
    synthetic id for temporary chats) before invoking this.

    `is_initial=True` means this is a fresh user send (not a regen, not an
    edit). Title autogen requires BOTH `is_initial` AND `count_assistant_messages
    == 0` so a regen/edit-of-first-turn (which truncates assistants → count
    returns 0) does NOT re-fire autogen and overwrite a user-renamed title.
    Defaults to True so single-call sites without explicit passing keep
    behaving as fresh sends.

    `user_id` + `api_key` (both M3):
    - `user_id` is the caller; required for usage_rollup increments. None is
      accepted only for temporary chats (no persistence, no rollup).
    - `api_key` is the resolved BYOK key for this turn (None means platform
      default). Passed through to `provider.stream(...)`. The `is_byok` flag
      on the rollup row is derived from `api_key is not None`.
    """
    # Emit `submitted` immediately.
    yield encode_submitted(SubmittedEvent(message_id=str(user_message_id)))
    turn_started_at = time.monotonic()

    # Accumulators for parts + usage.
    reasoning_buf: list[str] = []
    answer_buf: list[str] = []
    final_usage = UsageUpdate()
    emitted_reasoning_done = False
    is_byok_turn = api_key is not None
    # M4: substitution metadata threads from the provider's Complete event
    # through to build_attribution(...). When the provider didn't substitute
    # this stays None and the wire emits no `substitution` field.
    sub_code: str | None = None
    sub_provider: str | None = None
    sub_model: str | None = None
    sub_label: str | None = None

    # Wrap the provider iteration in a Task so we can cancel on disconnect.
    provider_iter = provider.stream(
        model_id=binding.model_id,
        history=history,
        user_text=user_text,
        api_key=api_key,
    )

    queue: asyncio.Queue[ProviderEvent | _PumpError | None] = asyncio.Queue()

    async def _pump() -> None:
        """Drain the provider iterator into the queue.

        A provider exception is forwarded to the consumer as a `_PumpError`
        sentinel so the consumer can re-raise it (→ `error` frame, no
        persistence). `CancelledError` (disconnect/cleanup cancel) is NOT
        forwarded — it just ends the pump. The terminal `None` always closes
        the queue so the consumer never blocks.
        """
        try:
            async for ev in provider_iter:
                await queue.put(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await queue.put(_PumpError(exc))
        finally:
            await queue.put(None)

    pump_task = asyncio.create_task(_pump())

    async def _persist_assistant(
        *,
        status: str,
        attribution: ModelAttribution,
        session: AsyncSession | None = None,
        commit: bool = True,
        cost_usd: float | None = None,
    ) -> UUID | None:
        if is_temporary or conversation_id is None:
            return None
        parts: list[dict[str, Any]] = []
        if reasoning_buf:
            parts.append({"type": "reasoning", "text": "".join(reasoning_buf)})
        parts.append({"type": "text", "text": "".join(answer_buf)})
        # Stop-path uses a fresh session (passed via `session=`); terminal-success
        # reuses the request-scoped `db`. Asymmetry: at disconnect the request
        # lifecycle is winding down and the route's get_db cleanup may
        # double-commit, so we decouple by opening a new session for stopped.
        target_session = session if session is not None else db
        row = await messages_repo.create_assistant_message(
            db=target_session,
            conversation_id=conversation_id,
            parts=parts,
            status=status,
            attribution=attribution.model_dump(by_alias=True, exclude_none=True),
            responds_to_message_id=user_message_id,
            cost_usd=cost_usd,
        )
        # When the caller owns the session (stop/fresh-session case, commit=False)
        # we only flush here and let the caller commit AFTER bumping usage, so the
        # assistant row and the meter increment land in ONE commit. The
        # terminal-success path passes no session and commits here as before.
        if commit:
            await target_session.commit()
        else:
            await target_session.flush()
        return row.id

    def _apply_event(ev: ProviderEvent) -> None:
        """Fold a queue event into accumulators (no yields).

        Used to drain any remaining UsageUpdate / Complete events after
        cancelling the pump on disconnect, so `final_usage` reflects the
        latest cumulative usage even on stopped turns.
        """
        nonlocal final_usage, sub_code, sub_provider, sub_model, sub_label
        if isinstance(ev, ReasoningDelta):
            reasoning_buf.append(ev.text)
        elif isinstance(ev, AnswerDelta):
            answer_buf.append(ev.text)
        elif isinstance(ev, UsageUpdate):
            final_usage = ev
        elif isinstance(ev, Complete):
            final_usage = ev.usage
            sub_code = ev.substitution
            sub_provider = ev.substituted_provider
            sub_model = ev.substituted_model
            sub_label = ev.substituted_display_label

    try:
        while True:
            # Tear down on EITHER a server-side stop request (the dedicated stop
            # endpoint set the in-process signal for this stream_id) OR the
            # client closing the socket (disconnect, per plan §"Streaming" rule
            # 6). Both persist the same `status="stopped"` row.
            if (
                stream_id is not None and is_stop_requested(stream_id)
            ) or await request.is_disconnected():
                pump_task.cancel()
                # Suppress ONLY the CancelledError from the cancel we just
                # issued; the pump forwards real provider exceptions through
                # the queue (drained below), so nothing genuine is hidden.
                with contextlib.suppress(asyncio.CancelledError):
                    await pump_task
                # Drain any events the pump already enqueued before cancel —
                # the pump may have pushed a final UsageUpdate / Complete that
                # we'd otherwise lose, leaving `final_usage` empty on stopped.
                while not queue.empty():
                    drained = queue.get_nowait()
                    if drained is None or isinstance(drained, _PumpError):
                        # Disconnect takes precedence over a late provider
                        # error: we're persisting `stopped`, not erroring, so
                        # a forwarded `_PumpError` is dropped here.
                        continue
                    _apply_event(drained)
                # Flush accumulators, persist with status=stopped + estimate.
                breakdown = compute_cost_breakdown(usage=final_usage, binding=binding)
                # Per-turn cost: matches what build_attribution exposes as
                # `attribution.costUsd` (pricing.py) so the ledger and the
                # wire stay consistent.
                turn_cost = breakdown.subtotal_usd + breakdown.session_surcharge_usd
                attribution = build_attribution(
                    requested_tier_id=requested_tier_id,
                    binding=binding,
                    breakdown=breakdown,
                    cost_confidence="estimate",
                    is_byok=is_byok_turn,
                    substitution=sub_code,
                    substituted_provider=sub_provider,
                    substituted_model=sub_model,
                    substituted_display_label=sub_label,
                )
                # Use a fresh session for stop-path persist (see helper docstring).
                # The assistant row and the usage_rollup bump land in ONE commit:
                # the persist flushes (commit=False), the meter bumps, then a
                # single fresh_db.commit() makes both durable atomically. Mirrors
                # the happy path (bump BEFORE its single commit) so a crash
                # between writes can never persist a stopped row without usage.
                async with _derive_session_factory(db)() as fresh_db:
                    stopped_assistant_id = await _persist_assistant(
                        status="stopped",
                        attribution=attribution,
                        session=fresh_db,
                        commit=False,
                        cost_usd=turn_cost,
                    )
                    # Stopped turn still cost partial tokens -- bump the meter.
                    # `is_temporary` already gates persistence; only increment
                    # if we actually have a real user / conversation.
                    if (
                        not is_temporary
                        and conversation_id is not None
                        and user_id is not None
                    ):
                        await usage_repo.increment_for_period(
                            fresh_db,
                            user_id=user_id,
                            cost_usd_delta=turn_cost,
                            is_byok=is_byok_turn,
                        )
                    # Land the durable stream lifecycle in the SAME commit as the
                    # stopped assistant row + meter bump. `message_id` points at
                    # the just-persisted assistant row (may be None for
                    # temporary, but the stop path only runs non-temporary
                    # streams).
                    if stream_id is not None:
                        await streams_repo.mark_status(
                            fresh_db,
                            stream_id=stream_id,
                            status="stopped",
                            message_id=stopped_assistant_id,
                        )
                    await fresh_db.commit()
                # Drop the live signal now that the turn is fully torn down.
                if stream_id is not None:
                    clear_stop(stream_id)
                # M4: stop-path turn log at warn level with cost_confidence=estimate.
                _struct_log.warning(
                    "turn.stopped",
                    status="stopped",
                    conversation_id=str(conversation_id) if conversation_id else None,
                    turn_ms=int((time.monotonic() - turn_started_at) * 1000),
                    prompt_tokens=final_usage.input_tokens,
                    completion_tokens=final_usage.output_tokens,
                    reasoning_tokens=final_usage.reasoning_tokens,
                    cost_usd=breakdown.subtotal_usd,
                    cost_confidence="estimate",
                    is_byok=is_byok_turn,
                    tier_id=binding.tier.id,
                )
                return  # No terminal on disconnect (socket closed).

            try:
                ev = await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            if ev is None:
                break  # Provider exhausted.
            if isinstance(ev, _PumpError):
                # Provider raised mid-stream. Re-raise into the top-level
                # `except Exception` so we emit an `error` frame and persist
                # nothing (the assistant row was never committed).
                raise ev.exc

            if isinstance(ev, ReasoningDelta):
                reasoning_buf.append(ev.text)
                yield encode_reasoning_delta(ReasoningDeltaEvent(text=ev.text))
            elif isinstance(ev, ReasoningDone):
                if not emitted_reasoning_done:
                    yield encode_reasoning_done(ReasoningDoneEvent())
                    emitted_reasoning_done = True
            elif isinstance(ev, AnswerDelta):
                # Invariant: emit ReasoningDone before the first AnswerDelta,
                # if any reasoning_delta has been seen but done hasn't fired.
                if reasoning_buf and not emitted_reasoning_done:
                    yield encode_reasoning_done(ReasoningDoneEvent())
                    emitted_reasoning_done = True
                answer_buf.append(ev.text)
                yield encode_answer_delta(AnswerDeltaEvent(text=ev.text))
            elif isinstance(ev, UsageUpdate):
                final_usage = ev
            elif isinstance(ev, Complete):
                final_usage = ev.usage
                sub_code = ev.substitution
                sub_provider = ev.substituted_provider
                sub_model = ev.substituted_model
                sub_label = ev.substituted_display_label

        # Provider finished cleanly. Compute attribution and emit terminal.
        breakdown = compute_cost_breakdown(usage=final_usage, binding=binding)
        # Per-turn cost: matches what build_attribution exposes as
        # `attribution.costUsd` (pricing.py) so the cost ledger row and the
        # wire attribution agree.
        turn_cost = breakdown.subtotal_usd + breakdown.session_surcharge_usd
        attribution = build_attribution(
            requested_tier_id=requested_tier_id,
            binding=binding,
            breakdown=breakdown,
            cost_confidence="exact",
            is_byok=is_byok_turn,
            substitution=sub_code,
            substituted_provider=sub_provider,
            substituted_model=sub_model,
            substituted_display_label=sub_label,
        )

        # Persist the assistant message (skipped for temporary).
        # First-terminal check happens BEFORE the create so we don't count
        # the row we're about to insert. Plan §"Behavior" + §"Title autogen":
        # only fire on the FIRST assistant message for the conversation.
        assistant_id: UUID | None = None
        is_first_terminal = False
        if not is_temporary and conversation_id is not None:
            # Title autogen gate: BOTH "no prior assistant rows" AND "this is a
            # fresh send" (not regen, not edit). Regen / edit-of-first-turn
            # delete the prior assistant(s) → count returns 0, which would
            # otherwise re-fire autogen and clobber a user-renamed title.
            is_first_terminal = is_initial and (
                await messages_repo.count_assistant_messages(db, conversation_id) == 0
            )
            parts: list[dict[str, Any]] = []
            if reasoning_buf:
                parts.append({"type": "reasoning", "text": "".join(reasoning_buf)})
            parts.append({"type": "text", "text": "".join(answer_buf)})
            row = await messages_repo.create_assistant_message(
                db=db,
                conversation_id=conversation_id,
                parts=parts,
                status="done",
                attribution=attribution.model_dump(by_alias=True, exclude_none=True),
                responds_to_message_id=user_message_id,
                cost_usd=turn_cost,
            )
            # Bump usage_rollup before the commit so both writes land
            # atomically. `user_id` is set on every non-temporary path (the
            # route always passes it for owned conversations). If callers
            # forget to pass it we skip the increment rather than 500 -- the
            # FE meter just stays cold.
            if user_id is not None:
                await usage_repo.increment_for_period(
                    db,
                    user_id=user_id,
                    cost_usd_delta=turn_cost,
                    is_byok=is_byok_turn,
                )
            # Transition the durable stream lifecycle to `done` and point it at
            # the assistant row, within the SAME transaction as the assistant
            # row + meter bump so the whole turn commits atomically.
            if stream_id is not None:
                await streams_repo.mark_status(
                    db,
                    stream_id=stream_id,
                    status="done",
                    message_id=row.id,
                )
            await db.commit()
            assistant_id = row.id

            if is_first_terminal:
                # Fire-and-forget. The task owns its own session; if the
                # worker dies before completion, title stays "New chat" until
                # the next turn re-fires the check (acceptable per plan).
                # Note: we don't `await` here — the streaming response must
                # close immediately after `terminal`. We do hold a reference
                # via a module-level set to keep the task alive against GC
                # in case the asyncio event-loop policy drops weakrefs.
                # The session factory is derived from the request-scoped
                # session's bind so tests can point at the per-test SQLite
                # file. In prod the bind is the process engine; either way
                # the factory targets the right DB.
                task = asyncio.create_task(
                    _autogen_title(
                        conversation_id=conversation_id,
                        user_text=user_text,
                        session_factory=_derive_session_factory(db),
                    )
                )
                _BG_TASKS.add(task)
                task.add_done_callback(_BG_TASKS.discard)

        # Terminal frame. For temporary chats the message is never persisted,
        # so we mint a fresh uuid4 per turn — using a constant placeholder
        # would collide across consecutive temp turns in one tab and break
        # FE-side vote/copy actions that key off `messageId`.
        terminal_message_id = (
            str(assistant_id) if assistant_id is not None else str(uuid4())
        )
        # M4: terminal-success turn log. Bound contextvars (request_id,
        # user_id) are merged in automatically; here we add per-turn keys.
        _struct_log.info(
            "turn.done",
            status="done",
            conversation_id=str(conversation_id) if conversation_id else None,
            turn_ms=int((time.monotonic() - turn_started_at) * 1000),
            prompt_tokens=final_usage.input_tokens,
            completion_tokens=final_usage.output_tokens,
            reasoning_tokens=final_usage.reasoning_tokens,
            cost_usd=breakdown.subtotal_usd,
            cost_confidence="exact",
            is_byok=is_byok_turn,
            tier_id=binding.tier.id,
            message_id=terminal_message_id,
        )
        yield encode_terminal(
            TerminalEvent(message_id=terminal_message_id, attribution=attribution)
        )

    except asyncio.CancelledError:
        # Hard cancel: worker shutdown / deploy / ASGI task cancel mid-stream.
        # Before re-raising we close out the durable stream bookkeeping so the
        # `stream` row doesn't strand at `status="active"` forever and the live
        # stop signal doesn't leak. Mirrors the `except Exception` branch's
        # fresh-session + best-effort pattern.
        #
        # Terminal status here is `"stopped"`, not `"error"`: the turn was
        # cancelled (the work was interrupted), not failed by the provider —
        # `"stopped"` matches the disconnect/explicit-stop semantics. We do NOT
        # persist a partial assistant row in this branch; there is no clean
        # partial-persist contract for a hard cancel, so we only close the
        # stream-lifecycle bookkeeping.
        #
        # A hard worker *crash* (SIGKILL / OOM) delivers no CancelledError, so
        # this cleanup never runs and the row would stay `active`. That gap is
        # closed by the orphan-stream reaper (`app.streaming.reaper` +
        # `streams_repo.reap_stale_active`), which sweeps stale `active` rows to
        # `"error"` on startup and on an interval (PRD 04 §5.1).
        if stream_id is not None:
            with contextlib.suppress(Exception):
                async with _derive_session_factory(db)() as cancel_db:
                    await streams_repo.mark_status(
                        cancel_db, stream_id=stream_id, status="stopped"
                    )
                    await cancel_db.commit()
            with contextlib.suppress(Exception):
                clear_stop(stream_id)
        # Re-raise so the event loop sees the cancellation rather than
        # swallowing it into a fake `error` envelope. The cleanup above must
        # NEVER suppress the cancellation. The `finally` clause still cancels
        # the pump task below.
        raise
    except Exception as exc:
        pump_task.cancel()
        # Suppress ONLY CancelledError from this cleanup cancel. The provider
        # error is already captured in `exc`; the pump forwards via the queue
        # and never re-raises on await, so no real exception is hidden here.
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
        if isinstance(exc, AppError):
            # Provider raised a typed error (e.g. RATE_LIMITED with
            # retryAfterMs); surface its envelope verbatim.
            envelope = exc.envelope
        else:
            # Unknown failure: generic upstream error. Never leak the raw
            # exception text to the client.
            envelope = ErrorEnvelope(
                code="PROVIDER_UPSTREAM",
                severity="error",
                title="Streaming failed",
                body="The provider stream errored.",
            )
        yield encode_error(envelope)
        # `error` does NOT persist an assistant row (plan §"Persistence" rule).
        # But the durable `stream` row SHOULD reflect the failure so the
        # lifecycle is observable. Best-effort + fresh session: the request
        # session may be poisoned after the provider error (a failed flush
        # leaves it in a rolled-back-pending state), so we open a clean one and
        # swallow any failure — stream-status bookkeeping must never turn a
        # provider error into a 500 or mask the `error` frame already yielded.
        if stream_id is not None:
            try:
                async with _derive_session_factory(db)() as err_db:
                    await streams_repo.mark_status(
                        err_db, stream_id=stream_id, status="error"
                    )
                    await err_db.commit()
            except Exception as mark_exc:  # pragma: no cover - defensive
                log.warning("stream.mark_error.failed", exc_info=mark_exc)
            with contextlib.suppress(Exception):
                clear_stop(stream_id)
        return
    finally:
        if not pump_task.done():
            pump_task.cancel()
            # Suppress ONLY CancelledError from this final cleanup cancel; a
            # genuine provider exception would have surfaced via the queue.
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
