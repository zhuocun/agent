"""Stream live-state backend foundation tests."""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from collections.abc import Iterable
from uuid import uuid4

import pytest

from app.config import Settings
from app.schemas.stream_events import SubmittedEvent
from app.streaming import replay_registry, stop_registry
from app.streaming.sse import encode_submitted
from app.streaming.state import configure_stream_state


class _FakePubSub:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._channels: set[str] = set()

    async def subscribe(self, *channels: str) -> None:
        self._channels.update(channels)

    async def unsubscribe(self, *channels: str) -> None:
        for channel in channels:
            self._channels.discard(channel)

    async def close(self) -> None:
        self._channels.clear()

    async def get_message(
        self, *, ignore_subscribe_messages: bool = True, timeout: float = 0.0
    ) -> dict[str, object] | None:
        del ignore_subscribe_messages, timeout
        async with self._redis._cond:
            await self._redis._cond.wait()
        return {"type": "message"}


class _FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = defaultdict(dict)
        self._lists: dict[str, list[str]] = defaultdict(list)
        self._expirations: dict[str, int] = {}
        self._cond = asyncio.Condition()

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += int(
                key in self._values or key in self._hashes or key in self._lists
            )
            self._values.pop(key, None)
            self._hashes.pop(key, None)
            self._lists.pop(key, None)
            self._expirations.pop(key, None)
        return removed

    async def set(self, key: str, value: str, *, px: int) -> bool:
        self._values[key] = value
        self._expirations[key] = px
        return True

    async def exists(self, *keys: str) -> int:
        return sum(
            int(key in self._values or key in self._hashes or key in self._lists)
            for key in keys
        )

    async def hset(
        self,
        key: str,
        field: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int:
        updates = dict(mapping or {})
        if field is not None and value is not None:
            updates[field] = value
        self._hashes[key].update(updates)
        return len(updates)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def hget(self, key: str, field: str) -> str | None:
        return self._hashes.get(key, {}).get(field)

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        current = int(self._hashes[key].get(field, "0")) + amount
        self._hashes[key][field] = str(current)
        return current

    async def incr(self, key: str) -> int:
        current = int(self._values.get(key, "0")) + 1
        self._values[key] = str(current)
        return current

    async def rpush(self, key: str, value: str) -> int:
        self._lists[key].append(value)
        return len(self._lists[key])

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    async def lpop(self, key: str) -> str | None:
        items = self._lists.get(key, [])
        if not items:
            return None
        return items.pop(0)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self._lists.get(key, [])
        stop = None if end == -1 else end + 1
        return list(items[start:stop])

    async def pexpire(self, key: str, ttl_ms: int) -> bool:
        self._expirations[key] = ttl_ms
        return True

    async def publish(self, channel: str, message: str) -> int:
        del channel, message
        async with self._cond:
            self._cond.notify_all()
        return 1

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self)


class _FakeRedisAsyncModule:
    def __init__(self, client: _FakeRedis) -> None:
        self._client = client
        self.Redis = self

    def from_url(self, url: str, *, decode_responses: bool = False) -> _FakeRedis:
        del url, decode_responses
        return self._client


def _event_names(events: Iterable[object]) -> list[str]:
    return [getattr(event, "event", None) or "" for event in events]


@pytest.mark.asyncio
async def test_async_stop_store_preserves_memory_backend() -> None:
    """Async stop-store API drives the same memory signal used by legacy tests."""
    stop_registry.use_memory_store()
    sid = uuid4()

    await stop_registry.request_stop_async(sid)
    assert await stop_registry.is_stop_requested_async(sid) is True
    assert stop_registry.is_stop_requested(sid) is True

    await stop_registry.clear_stop_async(sid)
    assert await stop_registry.is_stop_requested_async(sid) is False


@pytest.mark.asyncio
async def test_async_replay_store_preserves_memory_backend() -> None:
    """Async replay-store API returns the existing in-memory ReplayBuffer shape."""
    replay_registry.use_memory_store()
    sid = uuid4()

    buf = await replay_registry.create_async(sid, ttl_seconds=60.0, now=0.0)
    await buf.append(encode_submitted(SubmittedEvent(message_id="u")))
    await buf.mark_done(terminal_kind="done", now=0.0)

    assert await replay_registry.get_async(sid, ttl_seconds=60.0, now=30.0) is buf
    assert await replay_registry.get_async(sid, ttl_seconds=60.0, now=61.0) is None


def test_configure_stream_state_accepts_memory_backend() -> None:
    settings = Settings(STREAM_STATE_BACKEND="memory")
    configure_stream_state(settings)  # must not raise


def test_configure_stream_state_rejects_redis_backend_without_url() -> None:
    settings = Settings(
        STREAM_STATE_BACKEND="redis",
    )
    with pytest.raises(
        RuntimeError,
        match=re.escape("REDIS_URL is required when STREAM_STATE_BACKEND=redis"),
    ):
        configure_stream_state(settings)


def test_configure_stream_state_rejects_unreachable_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(_url: str) -> None:
        raise RuntimeError("STREAM_STATE_BACKEND=redis could not connect to REDIS_URL")

    monkeypatch.setattr("app.streaming.state._ping_redis_url", _boom)
    settings = Settings(
        STREAM_STATE_BACKEND="redis",
        REDIS_URL="redis://localhost:6379/0",
    )

    with pytest.raises(
        RuntimeError,
        match=re.escape("STREAM_STATE_BACKEND=redis could not connect to REDIS_URL"),
    ):
        configure_stream_state(settings)


@pytest.mark.asyncio
async def test_configure_stream_state_installs_redis_backed_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedis()

    monkeypatch.setattr("app.streaming.state._ping_redis_url", lambda _url: None)
    monkeypatch.setattr(
        "app.streaming.state._load_redis_modules",
        lambda: (object(), _FakeRedisAsyncModule(client)),
    )
    settings = Settings(
        STREAM_STATE_BACKEND="redis",
        REDIS_URL="redis://localhost:6379/0",
        STREAM_STOP_TTL_SECONDS=12.0,
        RESUMABLE_BUFFER_MAX_EVENTS=2,
        RESUMABLE_BUFFER_MAX_BYTES=10_000,
    )

    configure_stream_state(settings)
    try:
        sid = uuid4()
        await stop_registry.request_stop_async(sid)
        assert await stop_registry.is_stop_requested_async(sid) is True
        await stop_registry.clear_stop_async(sid)
        assert await stop_registry.is_stop_requested_async(sid) is False

        buffer = await replay_registry.create_async(sid, ttl_seconds=30.0)
        replay_key_prefix = f"olune:stream:replay:{sid}"
        assert client._expirations[f"{replay_key_prefix}:meta"] == 900_000
        assert client._expirations[f"{replay_key_prefix}:seq"] == 900_000
        await buffer.append(encode_submitted(SubmittedEvent(message_id="first")))
        assert client._expirations[f"{replay_key_prefix}:events"] == 900_000
        await buffer.append(encode_submitted(SubmittedEvent(message_id="second")))
        await buffer.append(encode_submitted(SubmittedEvent(message_id="third")))
        await buffer.mark_done(terminal_kind="done")
        assert client._expirations[f"{replay_key_prefix}:events"] == 30_000
        assert client._expirations[f"{replay_key_prefix}:meta"] == 30_000
        assert client._expirations[f"{replay_key_prefix}:seq"] == 30_000

        retained = await replay_registry.get_async(sid, ttl_seconds=30.0)
        assert retained is not None
        subscription = await retained.subscribe()
        events = [event async for event in subscription.events()]
        # Count-bounded Redis replay drops the oldest event first.
        assert _event_names(events) == ["submitted", "submitted"]
        assert '"third"' in str(getattr(events[-1], "data", ""))
    finally:
        stop_registry.use_memory_store()
        replay_registry.use_memory_store()
