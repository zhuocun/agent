"""In-process resumable-stream replay registry (PRD 04 §5.1 P1).

Same-device resumable-stream replay, gated behind the default-off
`Settings.resumable_streams_enabled` flag. This module is the IN-PROCESS replay
log: a per-process map `stream_id -> ReplayBuffer`, where a `ReplayBuffer` holds
the ordered list of SSE events a DETACHED producer has emitted so far, a `done`
flag, and an `asyncio.Condition` that wakes subscribers when new events land.

When the flag is on, the provider pump runs detached from the HTTP connection
(`app.streaming.handler.run_detached_producer`). The detached producer appends
every wire event here as it produces them; the original POST connection and any
`GET .../stream/{stream_id}` reconnect SUBSCRIBE to the buffer, replay all
buffered events from offset 0, then tail live until the producer is `done`.
Multiple concurrent subscribers are supported — each reads from its own offset,
so each receives the complete ordered sequence exactly once.

NO REDIS — same single-process MVP compromise as `app.streaming.stop_registry`,
`app.routes.conversations._TEMP_IDS`, and the slowapi in-memory rate limiter.
The buffer lives in ONE Python process. Behind multiple uvicorn workers a
reconnect that lands on a different worker than the producer finds no buffer and
404s; the durable `stream` row is still the cross-worker lifecycle record.
Multi-worker resumable streams need a shared Redis replay log here.

Missed-wakeup safety: the buffer's `asyncio.Condition` serializes appends and
subscriber waits. A subscriber only `await`s `cond.wait()` while HOLDING the
condition lock AND having observed it is caught up (`offset == len(events)`) and
not yet `done`. Any `append` / `mark_done` must first acquire the same lock
(blocked until the waiter releases it inside `wait()`), then `notify_all()`.
So a subscriber can never miss an event appended between its catch-up check and
its wait — the lock closes that window. This is the canonical CV pattern.

TTL / eviction: after the producer marks a buffer `done`, it is retained for
`Settings.resumable_buffer_ttl_seconds` so a late same-device reconnect can
still replay the full final sequence. Eviction is lazy: every `get` /
`create` sweeps expired-done buffers (a cheap O(n) scan over a tiny map — at
most a handful of in-flight/recently-finished streams per process). No
background machinery is added; the lazy sweep is sufficient for the MVP single
process. The monotonic clock is injectable (`now()` arg) so tests can drive TTL
expiry deterministically without wall-clock waits.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from uuid import UUID

from sse_starlette import ServerSentEvent

# Per-process registry. One entry per live (or recently-finished, within TTL)
# resumable stream. Cleared between tests (see `tests/conftest.py`).
_BUFFERS: dict[UUID, ReplayBuffer] = {}


class ReplayBuffer:
    """Ordered, append-only SSE event log for one detached producer.

    Producers `append` events and `mark_done` at terminal/stopped/error.
    Subscribers iterate via `subscribe`, which replays buffered events from
    offset 0 then tails live until `done`. See the module docstring for the
    missed-wakeup safety argument.
    """

    def __init__(self) -> None:
        self._events: list[ServerSentEvent] = []
        self._done = False
        # Terminal kind for observability: "done" | "stopped" | "error" | None.
        self._terminal_kind: str | None = None
        # Monotonic timestamp set when `mark_done` runs; drives TTL eviction.
        self._done_at: float | None = None
        self._cond = asyncio.Condition()

    @property
    def done(self) -> bool:
        return self._done

    @property
    def terminal_kind(self) -> str | None:
        return self._terminal_kind

    def done_at(self) -> float | None:
        """Monotonic time the buffer was marked done, or None if still live."""
        return self._done_at

    async def append(self, event: ServerSentEvent) -> None:
        """Append a wire event and wake all waiting subscribers.

        No-op after `mark_done` (a producer should never append post-terminal,
        but guard defensively so a late event can't reopen a closed buffer).
        """
        async with self._cond:
            if self._done:
                return
            self._events.append(event)
            self._cond.notify_all()

    async def mark_done(
        self, *, terminal_kind: str, now: float | None = None
    ) -> None:
        """Mark the buffer complete and wake subscribers so they drain + close.

        Idempotent: a second `mark_done` (e.g. shutdown cancel after a natural
        terminal) leaves the first terminal kind / timestamp intact.
        """
        async with self._cond:
            if self._done:
                return
            self._done = True
            self._terminal_kind = terminal_kind
            self._done_at = now if now is not None else time.monotonic()
            self._cond.notify_all()

    async def subscribe(self) -> ReplaySubscription:
        """Open a subscription reading from offset 0 (full replay then tail)."""
        return ReplaySubscription(self)


class ReplaySubscription:
    """A single subscriber's cursor over a `ReplayBuffer`.

    `events()` is an async generator: it yields every buffered event from the
    subscriber's offset forward, then awaits new events until the producer is
    `done`, yielding each exactly once in order.
    """

    def __init__(self, buffer: ReplayBuffer) -> None:
        self._buffer = buffer
        self._offset = 0

    async def events(self) -> AsyncIterator[ServerSentEvent]:
        buf = self._buffer
        cond = buf._cond
        while True:
            async with cond:
                # Drain everything buffered past our cursor while holding the
                # lock, so the catch-up check below is consistent with `_done`.
                pending = buf._events[self._offset :]
                self._offset += len(pending)
                if not pending:
                    if buf._done:
                        return
                    # Caught up and not done: wait for the next append/done.
                    # Holding `cond` here closes the missed-wakeup window — any
                    # append must re-acquire `cond` to notify, which it cannot
                    # until `wait()` releases the lock.
                    await cond.wait()
                    continue
            # Yield OUTSIDE the lock so a slow consumer can't block the
            # producer's appends (which need the lock to notify).
            for event in pending:
                yield event


def _evict_expired(ttl_seconds: float, *, now: float | None = None) -> None:
    """Drop done buffers older than `ttl_seconds`. Lazy sweep; O(n) over a
    tiny map. `now` is injectable for deterministic TTL tests."""
    clock = now if now is not None else time.monotonic()
    expired = [
        sid
        for sid, buf in _BUFFERS.items()
        if buf.done_at() is not None and (clock - buf.done_at()) >= ttl_seconds  # type: ignore[operator]
    ]
    for sid in expired:
        _BUFFERS.pop(sid, None)


def create(stream_id: UUID, *, ttl_seconds: float, now: float | None = None) -> ReplayBuffer:
    """Create (or replace) the buffer for `stream_id`. Sweeps expired first.

    Called by the detached producer before it starts appending. Replacing an
    existing entry is intentional: a fresh producer for the same stream id (a
    retry) starts a clean buffer.
    """
    _evict_expired(ttl_seconds, now=now)
    buffer = ReplayBuffer()
    _BUFFERS[stream_id] = buffer
    return buffer


def get(stream_id: UUID, *, ttl_seconds: float, now: float | None = None) -> ReplayBuffer | None:
    """Return the live (or within-TTL done) buffer for `stream_id`, else None.

    Sweeps expired-done buffers first, so a reconnect after the TTL window gets
    None (→ the route 404s) rather than a stale buffer.
    """
    _evict_expired(ttl_seconds, now=now)
    return _BUFFERS.get(stream_id)


def evict(stream_id: UUID) -> None:
    """Forget a buffer immediately. Idempotent."""
    _BUFFERS.pop(stream_id, None)
