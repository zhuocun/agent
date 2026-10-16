"""Unit tests for app.streaming.state — stream-state backend wiring.

Covers:
- `configure_stream_state` with memory backend.
- `configure_stream_state` with redis backend (missing URL raises).
- `close_stream_state` with and without a Redis client.
- `_load_redis_modules` returns the redis packages.
- `_maybe_await` handles both awaitable and non-awaitable values.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.streaming.state import (
    _load_redis_modules,
    _maybe_await,
    close_stream_state,
    configure_stream_state,
)

pytestmark = pytest.mark.asyncio


class TestConfigureStreamStateMemory:
    async def test_memory_backend(self) -> None:
        """Memory backend installs memory stores and clears any prior client."""
        from app.config import get_settings

        get_settings.cache_clear()
        settings = get_settings()
        # Default test env uses memory.
        configure_stream_state(settings)
        from app.streaming import state

        assert state._redis_client is None


class TestConfigureStreamStateRedis:
    async def test_redis_backend_missing_url_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redis backend without REDIS_URL raises RuntimeError."""
        from app.config import get_settings

        monkeypatch.setenv("STREAM_STATE_BACKEND", "redis")
        monkeypatch.delenv("REDIS_URL", raising=False)
        get_settings.cache_clear()
        try:
            settings = get_settings()
            with pytest.raises(RuntimeError, match="REDIS_URL is required"):
                configure_stream_state(settings)
        finally:
            monkeypatch.delenv("STREAM_STATE_BACKEND", raising=False)
            get_settings.cache_clear()

    async def test_redis_backend_ping_failure_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redis backend raises when ping fails."""
        from app.config import get_settings

        monkeypatch.setenv("STREAM_STATE_BACKEND", "redis")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:63799")
        get_settings.cache_clear()
        try:
            settings = get_settings()
            with pytest.raises(RuntimeError, match="could not connect"):
                configure_stream_state(settings)
        finally:
            monkeypatch.delenv("STREAM_STATE_BACKEND", raising=False)
            monkeypatch.delenv("REDIS_URL", raising=False)
            get_settings.cache_clear()


class TestCloseStreamState:
    async def test_close_with_no_client(self) -> None:
        """close_stream_state is a no-op when no client is set."""
        from app.streaming import state

        state._redis_client = None
        await close_stream_state()
        assert state._redis_client is None

    async def test_close_with_aclose_client(self) -> None:
        """close_stream_state calls aclose() on the client if available."""
        from app.streaming import state

        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        mock_client.connection_pool = None
        state._redis_client = mock_client

        await close_stream_state()

        mock_client.aclose.assert_awaited_once()
        assert state._redis_client is None

    async def test_close_with_close_client(self) -> None:
        """close_stream_state calls close() if aclose is not available."""
        from app.streaming import state

        mock_client = MagicMock(spec=["close", "connection_pool"])
        mock_client.close = AsyncMock()
        mock_client.connection_pool = None
        state._redis_client = mock_client

        await close_stream_state()

        mock_client.close.assert_awaited_once()
        assert state._redis_client is None

    async def test_close_disconnects_pool(self) -> None:
        """close_stream_state also disconnects the connection pool."""
        from app.streaming import state

        mock_pool = MagicMock(spec=["disconnect"])
        mock_pool.disconnect = AsyncMock()
        mock_client = MagicMock(spec=["aclose", "connection_pool"])
        mock_client.aclose = AsyncMock()
        mock_client.connection_pool = mock_pool
        state._redis_client = mock_client

        await close_stream_state()

        mock_pool.disconnect.assert_awaited_once()

    async def test_close_pool_with_aclose(self) -> None:
        """close_stream_state calls pool.aclose() if available."""
        from app.streaming import state

        mock_pool = MagicMock(spec=["aclose"])
        mock_pool.aclose = AsyncMock()
        mock_client = MagicMock(spec=["aclose", "connection_pool"])
        mock_client.aclose = AsyncMock()
        mock_client.connection_pool = mock_pool
        state._redis_client = mock_client

        await close_stream_state()

        mock_pool.aclose.assert_awaited_once()


class TestMaybeAwait:
    async def test_awaitable_value(self) -> None:
        """_maybe_await awaits the value if it has __await__."""
        called = False

        async def coro() -> None:
            nonlocal called
            called = True

        await _maybe_await(coro())
        assert called is True

    async def test_non_awaitable_value(self) -> None:
        """_maybe_await is a no-op for non-awaitable values."""
        await _maybe_await(None)
        await _maybe_await(42)
        await _maybe_await("string")


class TestLoadRedisModules:
    def test_returns_redis_packages(self) -> None:
        """_load_redis_modules returns (redis, redis.asyncio)."""
        redis, redis_async = _load_redis_modules()
        import redis as redis_pkg

        assert redis is redis_pkg
        assert hasattr(redis_async, "Redis")
