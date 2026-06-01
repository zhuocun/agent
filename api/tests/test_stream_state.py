"""Stream live-state backend foundation tests."""

from __future__ import annotations

import re
from uuid import uuid4

import pytest

from app.config import Settings
from app.schemas.stream_events import SubmittedEvent
from app.streaming import replay_registry, stop_registry
from app.streaming.sse import encode_submitted
from app.streaming.state import configure_stream_state


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


def test_configure_stream_state_rejects_reserved_redis_backend() -> None:
    settings = Settings(
        STREAM_STATE_BACKEND="redis",
        REDIS_URL="redis://localhost:6379/0",
    )
    with pytest.raises(
        RuntimeError,
        match=re.escape("STREAM_STATE_BACKEND=redis is reserved"),
    ):
        configure_stream_state(settings)
