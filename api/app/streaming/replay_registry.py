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
import json
import math
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol
from uuid import UUID

from sse_starlette import ServerSentEvent

# Per-process registry. One entry per live (or recently-finished, within TTL)
# resumable stream. Cleared between tests (see `tests/conftest.py`).
_BUFFERS: dict[UUID, ReplayBuffer] = {}


class ReplayLogTruncatedError(RuntimeError):
    """Raised when a replay log no longer has its prefix from sequence 1."""


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


def _decode_redis_value(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _redis_value_len(value: object) -> int:
    if isinstance(value, bytes):
        return len(value)
    return len(str(value).encode("utf-8"))


def _event_to_redis_json(seq: int, event: ServerSentEvent) -> str:
    """Serialize the subset of ServerSentEvent fields this API emits."""
    payload = {
        "seq": seq,
        "event": getattr(event, "event", None),
        "data": getattr(event, "data", None),
        "id": getattr(event, "id", None),
        "retry": getattr(event, "retry", None),
        "comment": getattr(event, "comment", None),
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _event_from_redis_json(raw: object) -> tuple[int, ServerSentEvent]:
    payload = json.loads(_decode_redis_value(raw))
    seq = int(payload["seq"])
    event = ServerSentEvent(
        event=payload.get("event"),
        data=payload.get("data"),
        id=payload.get("id"),
        retry=payload.get("retry"),
        comment=payload.get("comment"),
    )
    return seq, event


class RedisReplayLogBuffer:
    """Redis-backed replay log for one stream.

    Events are stored in a Redis list as JSON envelopes carrying a monotonic
    sequence number. Subscribers replay from the oldest retained sequence and
    then wait on a pub/sub wakeup channel for new events or terminal state.
    Redis trims the oldest events when the configured count or byte budget is
    exceeded. Live keys carry a refreshed orphan TTL; once terminal, that is
    replaced by the shorter replay TTL.
    """

    def __init__(
        self,
        client: Any,
        stream_id: UUID,
        *,
        ttl_seconds: float,
        live_ttl_seconds: float,
        max_events: int,
        max_bytes: int,
        key_prefix: str,
        done: bool = False,
        terminal_kind: str | None = None,
    ) -> None:
        self._client = client
        self._stream_id = stream_id
        self._ttl_seconds = ttl_seconds
        self._live_ttl_seconds = live_ttl_seconds
        self._max_events = max(1, max_events)
        self._max_bytes = max(1, max_bytes)
        self._key_prefix = key_prefix
        self._done = done
        self._terminal_kind = terminal_kind

    @property
    def done(self) -> bool:
        return self._done

    @property
    def terminal_kind(self) -> str | None:
        return self._terminal_kind

    @property
    def _events_key(self) -> str:
        return f"{self._key_prefix}:replay:{self._stream_id}:events"

    @property
    def _meta_key(self) -> str:
        return f"{self._key_prefix}:replay:{self._stream_id}:meta"

    @property
    def _seq_key(self) -> str:
        return f"{self._key_prefix}:replay:{self._stream_id}:seq"

    @property
    def _channel_key(self) -> str:
        return f"{self._key_prefix}:replay:{self._stream_id}:wake"

    def _ttl_ms(self) -> int:
        return max(1, math.ceil(self._ttl_seconds * 1000))

    def _live_ttl_ms(self) -> int:
        return max(1, math.ceil(self._live_ttl_seconds * 1000))

    async def _expire_keys(self, ttl_ms: int) -> None:
        await self._client.pexpire(self._events_key, ttl_ms)
        await self._client.pexpire(self._meta_key, ttl_ms)
        await self._client.pexpire(self._seq_key, ttl_ms)

    async def _expire_live_keys(self) -> None:
        await self._expire_keys(self._live_ttl_ms())

    async def _expire_terminal_keys(self) -> None:
        await self._expire_keys(self._ttl_ms())

    async def _meta_done(self) -> tuple[bool, str | None]:
        meta = await self._client.hgetall(self._meta_key)
        done_raw = meta.get(b"done") or meta.get("done")
        terminal_raw = meta.get(b"terminal_kind") or meta.get("terminal_kind")
        done = _decode_redis_value(done_raw) == "1" if done_raw is not None else False
        terminal_kind = (
            _decode_redis_value(terminal_raw) if terminal_raw is not None else None
        )
        if done:
            self._done = True
            self._terminal_kind = terminal_kind
        return done, terminal_kind

    async def _last_sequence(self) -> int | None:
        raw = await self._client.get(self._seq_key)
        return int(_decode_redis_value(raw)) if raw is not None else None

    async def has_retained_prefix(self) -> bool:
        """Whether Redis still has a replayable prefix starting at seq 1."""
        done, _terminal_kind = await self._meta_done()
        raw_events = await self._client.lrange(self._events_key, 0, 0)
        if raw_events:
            first_seq, _event = _event_from_redis_json(raw_events[0])
            return first_seq == 1
        # An empty list is valid only before the producer has appended anything.
        # If seq advanced but the list is empty, Redis trimmed/expired the prefix.
        last_seq = await self._last_sequence()
        if not done:
            # Avoid rejecting during the small INCR -> RPUSH append window.
            return True
        return last_seq == 0

    async def _trim_bounds(self) -> None:
        """Trim oldest retained events until count and byte budgets are met."""
        while int(await self._client.llen(self._events_key)) > self._max_events:
            raw = await self._client.lpop(self._events_key)
            if raw is None:
                break
            await self._client.hincrby(self._meta_key, "bytes", -_redis_value_len(raw))

        while True:
            raw_total = await self._client.hget(self._meta_key, "bytes")
            total = int(_decode_redis_value(raw_total)) if raw_total is not None else 0
            if total <= self._max_bytes:
                break
            # Retain at least one event so an oversized single event is still
            # replayable; subsequent appends will evict it if needed.
            if int(await self._client.llen(self._events_key)) <= 1:
                break
            raw = await self._client.lpop(self._events_key)
            if raw is None:
                break
            await self._client.hincrby(self._meta_key, "bytes", -_redis_value_len(raw))

    async def append(self, event: ServerSentEvent) -> None:
        done, _terminal_kind = await self._meta_done()
        if done:
            return
        seq = int(await self._client.incr(self._seq_key))
        payload = _event_to_redis_json(seq, event)
        encoded_len = len(payload.encode("utf-8"))
        await self._client.rpush(self._events_key, payload)
        await self._client.hincrby(self._meta_key, "bytes", encoded_len)
        await self._trim_bounds()
        await self._expire_live_keys()
        await self._client.publish(self._channel_key, "append")

    async def mark_done(
        self, *, terminal_kind: str, now: float | None = None
    ) -> None:
        done, _existing = await self._meta_done()
        if done:
            return
        done_at = now if now is not None else time.monotonic()
        await self._client.hset(
            self._meta_key,
            mapping={
                "done": "1",
                "terminal_kind": terminal_kind,
                "done_at": str(done_at),
            },
        )
        await self._expire_terminal_keys()
        self._done = True
        self._terminal_kind = terminal_kind
        await self._client.publish(self._channel_key, "done")

    async def subscribe(self) -> ReplaySubscriptionHandle:
        return RedisReplaySubscription(self)


class RedisReplaySubscription:
    """Subscriber cursor for a Redis-backed replay buffer."""

    def __init__(self, buffer: RedisReplayLogBuffer) -> None:
        self._buffer = buffer
        self._next_seq = 1

    async def _pending(self) -> list[ServerSentEvent]:
        raw_events = await self._buffer._client.lrange(self._buffer._events_key, 0, -1)
        out: list[ServerSentEvent] = []
        seen_next = self._next_seq
        if not raw_events:
            done, _terminal_kind = await self._buffer._meta_done()
            last_seq = await self._buffer._last_sequence()
            if done and last_seq is not None and last_seq >= self._next_seq:
                raise ReplayLogTruncatedError(
                    f"replay log for stream {self._buffer._stream_id} lost "
                    f"sequence {self._next_seq}"
                )
            return out
        for raw in raw_events:
            seq, event = _event_from_redis_json(raw)
            if seq < seen_next:
                continue
            if seq != seen_next:
                raise ReplayLogTruncatedError(
                    f"replay log for stream {self._buffer._stream_id} lost "
                    f"sequence {seen_next}"
                )
            if seq >= self._next_seq:
                out.append(event)
                seen_next = seq + 1
        self._next_seq = seen_next
        return out

    async def events(self) -> AsyncIterator[ServerSentEvent]:
        pubsub = self._buffer._client.pubsub()
        await pubsub.subscribe(self._buffer._channel_key)
        try:
            while True:
                pending = await self._pending()
                if pending:
                    for event in pending:
                        yield event
                    continue
                done, _terminal_kind = await self._buffer._meta_done()
                if done:
                    return
                await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
        finally:
            await pubsub.unsubscribe(self._buffer._channel_key)
            await pubsub.close()


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


class RedisReplayLogStore:
    """Redis replay-log store shared across API workers."""

    def __init__(
        self,
        client: Any,
        *,
        max_events: int,
        max_bytes: int,
        live_ttl_seconds: float,
        key_prefix: str = "olune:stream",
    ) -> None:
        self._client = client
        self._max_events = max_events
        self._max_bytes = max_bytes
        self._live_ttl_seconds = live_ttl_seconds
        self._key_prefix = key_prefix

    def _buffer(self, stream_id: UUID, *, ttl_seconds: float) -> RedisReplayLogBuffer:
        return RedisReplayLogBuffer(
            self._client,
            stream_id,
            ttl_seconds=ttl_seconds,
            live_ttl_seconds=self._live_ttl_seconds,
            max_events=self._max_events,
            max_bytes=self._max_bytes,
            key_prefix=self._key_prefix,
        )

    def _events_key(self, stream_id: UUID) -> str:
        return f"{self._key_prefix}:replay:{stream_id}:events"

    def _meta_key(self, stream_id: UUID) -> str:
        return f"{self._key_prefix}:replay:{stream_id}:meta"

    def _seq_key(self, stream_id: UUID) -> str:
        return f"{self._key_prefix}:replay:{stream_id}:seq"

    async def create(
        self, stream_id: UUID, *, ttl_seconds: float, now: float | None = None
    ) -> ReplayLogBuffer:
        del now  # Redis key expiry, not an injected monotonic clock, drives TTL.
        await self._client.delete(
            self._events_key(stream_id),
            self._meta_key(stream_id),
            self._seq_key(stream_id),
        )
        await self._client.hset(
            self._meta_key(stream_id),
            mapping={"done": "0", "bytes": "0"},
        )
        buffer = self._buffer(stream_id, ttl_seconds=ttl_seconds)
        await self._client.set(buffer._seq_key, "0", px=buffer._live_ttl_ms())
        await buffer._expire_live_keys()
        return buffer

    async def get(
        self, stream_id: UUID, *, ttl_seconds: float, now: float | None = None
    ) -> ReplayLogBuffer | None:
        del now  # Redis key expiry, not an injected monotonic clock, drives TTL.
        if not await self._client.exists(self._meta_key(stream_id)):
            return None
        buffer = self._buffer(stream_id, ttl_seconds=ttl_seconds)
        if not await buffer.has_retained_prefix():
            raise ReplayLogTruncatedError(
                f"replay log for stream {stream_id} no longer has its prefix"
            )
        await buffer._meta_done()
        return buffer

    async def evict(self, stream_id: UUID) -> None:
        await self._client.delete(
            self._events_key(stream_id),
            self._meta_key(stream_id),
            self._seq_key(stream_id),
        )


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
