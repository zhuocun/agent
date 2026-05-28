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
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import ServerSentEvent

from app.db.repositories import messages as messages_repo
from app.db.session import get_session_factory
from app.errors import ErrorEnvelope
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
from app.providers.tiers import TierBinding
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
) -> AsyncIterator[ServerSentEvent]:
    """Drive the provider, persist, yield wire SSE events.

    `conversation_id` is None for temporary chats — persistence is skipped.
    The caller MUST have already persisted the user message (or generated a
    synthetic id for temporary chats) before invoking this.
    """
    # Emit `submitted` immediately.
    yield encode_submitted(SubmittedEvent(message_id=str(user_message_id)))

    # Accumulators for parts + usage.
    reasoning_buf: list[str] = []
    answer_buf: list[str] = []
    final_usage = UsageUpdate()
    emitted_reasoning_done = False

    # Wrap the provider iteration in a Task so we can cancel on disconnect.
    provider_iter = provider.stream(
        model_id=binding.model_id,
        history=history,
        user_text=user_text,
    )

    queue: asyncio.Queue[ProviderEvent | None] = asyncio.Queue()

    async def _pump() -> None:
        """Drain the provider iterator into the queue."""
        try:
            async for ev in provider_iter:
                await queue.put(ev)
        finally:
            await queue.put(None)

    pump_task = asyncio.create_task(_pump())

    async def _persist_assistant(
        *,
        status: str,
        attribution: ModelAttribution,
        session: AsyncSession | None = None,
    ) -> None:
        if is_temporary or conversation_id is None:
            return
        parts: list[dict[str, Any]] = []
        if reasoning_buf:
            parts.append({"type": "reasoning", "text": "".join(reasoning_buf)})
        parts.append({"type": "text", "text": "".join(answer_buf)})
        # Stop-path uses a fresh session (passed via `session=`); terminal-success
        # reuses the request-scoped `db`. Asymmetry: at disconnect the request
        # lifecycle is winding down and the route's get_db cleanup may
        # double-commit, so we decouple by opening a new session for stopped.
        target_session = session if session is not None else db
        await messages_repo.create_assistant_message(
            db=target_session,
            conversation_id=conversation_id,
            parts=parts,
            status=status,
            attribution=attribution.model_dump(by_alias=True, exclude_none=True),
        )
        await target_session.commit()

    def _apply_event(ev: ProviderEvent) -> None:
        """Fold a queue event into accumulators (no yields).

        Used to drain any remaining UsageUpdate / Complete events after
        cancelling the pump on disconnect, so `final_usage` reflects the
        latest cumulative usage even on stopped turns.
        """
        nonlocal final_usage
        if isinstance(ev, ReasoningDelta):
            reasoning_buf.append(ev.text)
        elif isinstance(ev, AnswerDelta):
            answer_buf.append(ev.text)
        elif isinstance(ev, UsageUpdate):
            final_usage = ev
        elif isinstance(ev, Complete):
            final_usage = ev.usage

    try:
        while True:
            # Disconnect-detect between yields (per plan §"Streaming" rule 6).
            if await request.is_disconnected():
                pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump_task
                # Drain any events the pump already enqueued before cancel —
                # the pump may have pushed a final UsageUpdate / Complete that
                # we'd otherwise lose, leaving `final_usage` empty on stopped.
                while not queue.empty():
                    drained = queue.get_nowait()
                    if drained is None:
                        continue
                    _apply_event(drained)
                # Flush accumulators, persist with status=stopped + estimate.
                breakdown = compute_cost_breakdown(usage=final_usage, binding=binding)
                attribution = build_attribution(
                    requested_tier_id=requested_tier_id,
                    binding=binding,
                    breakdown=breakdown,
                    cost_confidence="estimate",
                )
                # Use a fresh session for stop-path persist (see helper docstring).
                async with get_session_factory()() as fresh_db:
                    await _persist_assistant(
                        status="stopped",
                        attribution=attribution,
                        session=fresh_db,
                    )
                return  # No terminal on disconnect (socket closed).

            try:
                ev = await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            if ev is None:
                break  # Provider exhausted.

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

        # Provider finished cleanly. Compute attribution and emit terminal.
        breakdown = compute_cost_breakdown(usage=final_usage, binding=binding)
        attribution = build_attribution(
            requested_tier_id=requested_tier_id,
            binding=binding,
            breakdown=breakdown,
            cost_confidence="exact",
        )

        # Persist the assistant message (skipped for temporary).
        # TODO(M2): fire `asyncio.create_task(autogen_title(...))` here on
        # first terminal — plan §"Behavior" + §"Title autogen".
        assistant_id: UUID | None = None
        if not is_temporary and conversation_id is not None:
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
            )
            await db.commit()
            assistant_id = row.id

        # Terminal frame. For temporary chats the message is never persisted,
        # so we mint a fresh uuid4 per turn — using a constant placeholder
        # would collide across consecutive temp turns in one tab and break
        # FE-side vote/copy actions that key off `messageId`.
        terminal_message_id = (
            str(assistant_id) if assistant_id is not None else str(uuid4())
        )
        yield encode_terminal(
            TerminalEvent(message_id=terminal_message_id, attribution=attribution)
        )

    except asyncio.CancelledError:
        # CancelledError IS an Exception in 3.8+; re-raise so the event loop
        # sees the cancellation rather than swallowing it into a fake `error`
        # envelope. The `finally` clause still cancels the pump task below.
        raise
    except Exception as exc:
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pump_task
        envelope = ErrorEnvelope(
            code="PROVIDER_UPSTREAM",
            severity="error",
            title="Streaming failed",
            body=str(exc) or "The provider stream errored.",
        )
        yield encode_error(envelope)
        # `error` does NOT persist (plan §"Persistence" rule).
        return
    finally:
        if not pump_task.done():
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pump_task
