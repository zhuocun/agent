"""In-process stop signal for streaming turns (PRD 04 §5.1).

Bridges a stop *request* (the `POST /{id}/stop` route, running on one
request/session) to the running stream *generator* (`stream_and_persist`, on a
different request/session). The stop route records the durable intent on the
`stream` row and sets the live signal here; the generator polls
`is_stop_requested(...)` between yields and tears the turn down as `stopped`.

Single-process only. This `set` lives in one Python process — exactly the same
caveat as `app.routes.conversations._TEMP_IDS` and the slowapi in-memory rate
limiter. Behind multiple uvicorn workers a stop requested on worker A will NOT
reach a stream running on worker B; the durable `stream.status="stopped"` row is
still written, but the live generator on the other worker keeps going until its
own disconnect check fires. Multi-worker prod needs a Redis pub/sub (or similar)
channel here. The `stream` table is the durable record; this is the best-effort
live cancel.
"""

from __future__ import annotations

from uuid import UUID

_STOP_REQUESTS: set[UUID] = set()


def request_stop(stream_id: UUID) -> None:
    """Signal the running generator for `stream_id` to stop at its next poll."""
    _STOP_REQUESTS.add(stream_id)


def is_stop_requested(stream_id: UUID) -> bool:
    """True if a stop has been requested for `stream_id` and not yet cleared."""
    return stream_id in _STOP_REQUESTS


def clear_stop(stream_id: UUID) -> None:
    """Drop the stop signal for `stream_id`. Idempotent."""
    _STOP_REQUESTS.discard(stream_id)
