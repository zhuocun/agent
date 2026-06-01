"""Live stream-state backend configuration.

The resumable-stream and stop-signal paths talk to async store interfaces. This
module wires those interfaces to either the default process-local memory stores
or Redis-backed stores for cross-worker replay/stop coordination.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.streaming import replay_registry, stop_registry

_redis_client: Any | None = None


def _load_redis_modules() -> tuple[Any, Any]:
    try:
        import redis
        from redis import asyncio as redis_async
    except ImportError as exc:  # pragma: no cover - exercised only without deps
        raise RuntimeError(
            "STREAM_STATE_BACKEND=redis requires the 'redis' Python package"
        ) from exc
    return redis, redis_async


def _ping_redis_url(redis_url: str) -> None:
    redis, _redis_async = _load_redis_modules()
    client = redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=False,
    )
    try:
        client.ping()
    except Exception as exc:
        raise RuntimeError(
            "STREAM_STATE_BACKEND=redis could not connect to REDIS_URL"
        ) from exc
    finally:
        client.close()


async def _maybe_await(value: Any) -> None:
    if hasattr(value, "__await__"):
        await value


def configure_stream_state(settings: Settings) -> None:
    """Configure live stream-state stores for this process.

    `memory` preserves existing single-process behavior. `redis` validates the
    URL at startup, then installs Redis-backed stop and replay stores.
    """
    global _redis_client
    if settings.stream_state_backend == "memory":
        stop_registry.use_memory_store()
        replay_registry.use_memory_store()
        _redis_client = None
        return

    if settings.redis_url is None:
        raise RuntimeError("REDIS_URL is required when STREAM_STATE_BACKEND=redis")
    _ping_redis_url(settings.redis_url)
    _redis, redis_async = _load_redis_modules()
    client = redis_async.Redis.from_url(settings.redis_url, decode_responses=False)
    _redis_client = client
    replay_live_ttl_seconds = max(
        settings.resumable_buffer_ttl_seconds,
        float(settings.stream_reap_after_seconds)
        if settings.stream_reap_after_seconds > 0
        else settings.resumable_buffer_ttl_seconds,
    )
    stop_registry.set_store(
        stop_registry.RedisStopSignalStore(
            client,
            ttl_seconds=settings.stream_stop_ttl_seconds,
        )
    )
    replay_registry.set_store(
        replay_registry.RedisReplayLogStore(
            client,
            max_events=settings.resumable_buffer_max_events,
            max_bytes=settings.resumable_buffer_max_bytes,
            live_ttl_seconds=replay_live_ttl_seconds,
        )
    )


async def close_stream_state() -> None:
    """Close any process-wide Redis stream-state client and restore memory stores."""
    global _redis_client
    client = _redis_client
    _redis_client = None
    stop_registry.use_memory_store()
    replay_registry.use_memory_store()
    if client is None:
        return

    if hasattr(client, "aclose"):
        await _maybe_await(client.aclose())
    elif hasattr(client, "close"):
        await _maybe_await(client.close())

    pool = getattr(client, "connection_pool", None)
    if pool is not None:
        if hasattr(pool, "aclose"):
            await _maybe_await(pool.aclose())
        elif hasattr(pool, "disconnect"):
            await _maybe_await(pool.disconnect())
