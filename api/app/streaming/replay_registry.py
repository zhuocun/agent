"""Resumable-stream replay registry (PRD 04 §5.1 P1).

Same-device resumable-stream replay, gated behind the default-off
`Settings.resumable_streams_enabled` flag. The default backend is the existing
IN-PROCESS replay log: a per-process map `stream_id -> ReplayBuffer`, where a
`ReplayBuffer` holds the ordered list of SSE events a DETACHED producer has
emitted so far, a `done` flag, and an `asyncio.Condition` that wakes subscribers
when new events land.

When the flag is on, the provider pump runs detached from the HTTP connection
(`app.streaming.handler.run_detached_producer`). The detached producer appends
every wire event here as it produces them; the original POST connection and any
`GET .../stream/{stream_id}` reconnect SUBSCRIBE to the buffer, replay all
buffered events from offset 0, then tail live until the producer is `done`.
Multiple concurrent subscribers are supported — each reads from its own offset,
so each receives the complete ordered sequence exactly once.

The memory backend has the same single-process MVP compromise as
`app.streaming.stop_registry`, `app.routes.conversations._TEMP_IDS`, and the
slowapi in-memory rate limiter. The buffer lives in ONE Python process. Behind
multiple uvicorn workers a reconnect that lands on a different worker than the
producer finds no buffer and 404s; the durable `stream` row is still the
cross-worker lifecycle record. The async store interface below is the seam for a
future shared Redis replay log.

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
from typing import Protocol
from uuid import UUID

from sse_starlette import ServerSentEvent

# Per-process registry. One entry per live (or recently-finished, within TTL)
# resumable stream. Cleared between tests (see `tests/conftest.py`).
_BUFFERS: dict[UUID, ReplayBuffer] = {}


class ReplaySubscriptionHandle(Protocol):
    """Cursor over a replay log."""

    def events(self) -> AsyncIterator[ServerSentEvent]:
        """Yield replay events from this cursor."""
        ...


class ReplayLogBuffer(Protocol):
    """Minimal replay log contract consumed by detached producers/subscribers."""

    @property
    def done(self) -> bool:
        """Whether the replay log has reached a terminal state."""
        ...

    @property
    def terminal_kind(self) -> str | None:
        """Terminal kind: done, stopped, error, or None."""
        ...

    async def append(self, event: ServerSentEvent) -> None:
        """Append one wire event."""
        ...

    async def mark_done(
        self, *, terminal_kind: str, now: float | None = None
    ) -> None:
        """Mark the replay log terminal and wake subscribers."""
        ...

    async def subscribe(self) -> ReplaySubscriptionHandle:
        """Open a replay cursor from the beginning."""
        ...


class ReplayLogStore(Protocol):
    """Async store contract for stream replay logs."""

    async def create(
        self, stream_id: UUID, *, ttl_seconds: float, now: float | None = None
    ) -> ReplayLogBuffer:
        """Create or replace one replay log."""
        ...

    async def get(
        self, stream_id: UUID, *, ttl_seconds: float, now: float | None = None
    ) -> ReplayLogBuffer | None:
        """Return a live or within-TTL terminal replay log."""
        ...

    async def evict(self, stream_id: UUID) -> None:
        """Forget one replay log."""
        ...


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


def _evict_expired(
    buffers: dict[UUID, ReplayBuffer],
    ttl_seconds: float,
    *,
    now: float | None = None,
) -> None:
    """Drop done buffers older than `ttl_seconds`. Lazy sweep; O(n) over a
    tiny map. `now` is injectable for deterministic TTL tests."""
    clock = now if now is not None else time.monotonic()
    expired: list[UUID] = []
    for sid, buf in buffers.items():
        done_at = buf.done_at()
        if done_at is not None and (clock - done_at) >= ttl_seconds:
            expired.append(sid)
    for sid in expired:
        buffers.pop(sid, None)


class InMemoryReplayLogStore:
    """Process-local replay-log store preserving the existing behavior."""

    def __init__(self, buffers: dict[UUID, ReplayBuffer]) -> None:
        self._buffers = buffers

    async def create(
        self, stream_id: UUID, *, ttl_seconds: float, now: float | None = None
    ) -> ReplayLogBuffer:
        _evict_expired(self._buffers, ttl_seconds, now=now)
        buffer = ReplayBuffer()
        self._buffers[stream_id] = buffer
        return buffer

    async def get(
        self, stream_id: UUID, *, ttl_seconds: float, now: float | None = None
    ) -> ReplayLogBuffer | None:
        _evict_expired(self._buffers, ttl_seconds, now=now)
        return self._buffers.get(stream_id)

    async def evict(self, stream_id: UUID) -> None:
        self._buffers.pop(stream_id, None)


_MEMORY_STORE = InMemoryReplayLogStore(_BUFFERS)
_store: ReplayLogStore = _MEMORY_STORE


def set_store(store: ReplayLogStore) -> None:
    """Install a replay-log store implementation for this process."""
    global _store
    _store = store


def use_memory_store() -> None:
    """Reset to the default process-local store."""
    set_store(_MEMORY_STORE)


async def create_async(
    stream_id: UUID, *, ttl_seconds: float, now: float | None = None
) -> ReplayLogBuffer:
    """Create (or replace) the replay log for `stream_id`."""
    return await _store.create(stream_id, ttl_seconds=ttl_seconds, now=now)


async def get_async(
    stream_id: UUID, *, ttl_seconds: float, now: float | None = None
) -> ReplayLogBuffer | None:
    """Return the live (or within-TTL done) replay log for `stream_id`."""
    return await _store.get(stream_id, ttl_seconds=ttl_seconds, now=now)


async def evict_async(stream_id: UUID) -> None:
    """Forget a replay log immediately. Idempotent."""
    await _store.evict(stream_id)


def create(stream_id: UUID, *, ttl_seconds: float, now: float | None = None) -> ReplayBuffer:
    """Create (or replace) the buffer for `stream_id`. Sweeps expired first.

    Called by the detached producer before it starts appending. Replacing an
    existing entry is intentional: a fresh producer for the same stream id (a
    retry) starts a clean buffer.
    """
    _evict_expired(_BUFFERS, ttl_seconds, now=now)
    buffer = ReplayBuffer()
    _BUFFERS[stream_id] = buffer
    return buffer


def get(stream_id: UUID, *, ttl_seconds: float, now: float | None = None) -> ReplayBuffer | None:
    """Return the live (or within-TTL done) buffer for `stream_id`, else None.

    Sweeps expired-done buffers first, so a reconnect after the TTL window gets
    None (→ the route 404s) rather than a stale buffer.
    """
    _evict_expired(_BUFFERS, ttl_seconds, now=now)
    return _BUFFERS.get(stream_id)


def evict(stream_id: UUID) -> None:
    """Forget a buffer immediately. Idempotent."""
    _BUFFERS.pop(stream_id, None)
