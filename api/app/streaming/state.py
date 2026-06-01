"""Live stream-state backend configuration.

The resumable-stream and stop-signal paths currently run on an in-memory store.
This module centralizes backend selection so the route/handler code talks to
async store interfaces instead of process-global data structures directly. That
keeps default behavior unchanged while making a future Redis backend a local
implementation swap rather than another route-level refactor.
"""

from __future__ import annotations

from app.config import Settings
from app.streaming import replay_registry, stop_registry


def configure_stream_state(settings: Settings) -> None:
    """Configure live stream-state stores for this process.

    `memory` is the only implemented backend today. `redis` is intentionally a
    fail-fast reserved value: the config/env contract exists, but Redis replay
    log + pub/sub semantics are not implemented in this change.
    """
    if settings.stream_state_backend == "memory":
        stop_registry.use_memory_store()
        replay_registry.use_memory_store()
        return

    if settings.redis_url is None:
        raise RuntimeError("REDIS_URL is required when STREAM_STATE_BACKEND=redis")
    raise RuntimeError(
        "STREAM_STATE_BACKEND=redis is reserved but not implemented yet; "
        "use STREAM_STATE_BACKEND=memory"
    )
