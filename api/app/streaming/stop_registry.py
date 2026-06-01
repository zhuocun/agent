"""Stop signal store for streaming turns (PRD 04 §5.1).

Bridges a stop *request* (the `POST /{id}/stop` route, running on one
request/session) to the running stream *generator* (`stream_and_persist`, on a
different request/session). The stop route records the durable intent on the
`stream` row and sets the live signal here; the generator polls the async
`is_stop_requested_async(...)` store API between yields and tears the turn down
as `stopped`.

Default backend is still single-process memory. Behind multiple uvicorn workers
a memory-backed stop requested on worker A will NOT reach a stream running on
worker B; the durable `stream.status="stopped"` row is still written, but the
live generator on the other worker keeps going until its own disconnect check
fires. The async store interface is the shared-state seam for a future Redis
pub/sub (or similar) backend. The `stream` table remains the durable record;
this store is the best-effort live cancel.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

_STOP_REQUESTS: set[UUID] = set()


class StopSignalStore(Protocol):
    """Async stop-signal store contract used by routes and stream handlers."""

    async def request_stop(self, stream_id: UUID) -> None:
        """Record a live stop request."""
        ...

    async def is_stop_requested(self, stream_id: UUID) -> bool:
        """Return whether a stop request is live."""
        ...

    async def clear_stop(self, stream_id: UUID) -> None:
        """Clear a live stop request."""
        ...


class InMemoryStopSignalStore:
    """Process-local stop-signal store preserving the existing behavior."""

    def __init__(self, requests: set[UUID]) -> None:
        self._requests = requests

    async def request_stop(self, stream_id: UUID) -> None:
        self._requests.add(stream_id)

    async def is_stop_requested(self, stream_id: UUID) -> bool:
        return stream_id in self._requests

    async def clear_stop(self, stream_id: UUID) -> None:
        self._requests.discard(stream_id)


_MEMORY_STORE = InMemoryStopSignalStore(_STOP_REQUESTS)
_store: StopSignalStore = _MEMORY_STORE


def set_store(store: StopSignalStore) -> None:
    """Install a stop-signal store implementation for this process."""
    global _store
    _store = store


def use_memory_store() -> None:
    """Reset to the default process-local store."""
    set_store(_MEMORY_STORE)


async def request_stop_async(stream_id: UUID) -> None:
    """Signal the running generator for `stream_id` to stop at its next poll."""
    await _store.request_stop(stream_id)


async def is_stop_requested_async(stream_id: UUID) -> bool:
    """True if a stop has been requested for `stream_id` and not yet cleared."""
    return await _store.is_stop_requested(stream_id)


async def clear_stop_async(stream_id: UUID) -> None:
    """Drop the stop signal for `stream_id`. Idempotent."""
    await _store.clear_stop(stream_id)


def request_stop(stream_id: UUID) -> None:
    """Memory-backend sync compatibility wrapper for older direct tests."""
    _STOP_REQUESTS.add(stream_id)


def is_stop_requested(stream_id: UUID) -> bool:
    """Memory-backend sync compatibility wrapper for older direct tests."""
    return stream_id in _STOP_REQUESTS


def clear_stop(stream_id: UUID) -> None:
    """Memory-backend sync compatibility wrapper for older direct tests."""
    _STOP_REQUESTS.discard(stream_id)
