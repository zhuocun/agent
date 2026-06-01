"""Stream repository (PRD 04 §5.1).

Durable lifecycle of a streaming turn. One row per non-temporary streaming
turn: created `active` when the turn starts, transitioned to `done` /
`stopped` / `error` by the handler, and touched by the dedicated stop endpoint
without releasing the active guard.

The in-process stop *signal* lives in `app.streaming.stop_registry`; this
module is the durable record. Keep the two in sync at the call sites (the
handler / stop route), not here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Stream


class ActiveStreamExistsError(Exception):
    """Raised by `create_stream` when an active stream already exists.

    Surfaces the partial-unique-index violation
    (`ix_stream_conversation_active_unique`) as a typed domain signal the route
    maps to 409 CONFLICT. Catching the IntegrityError HERE (not at the route)
    keeps the durable concurrency guard self-contained: a concurrent
    double-submit that races past the route's fast precheck loses on INSERT and
    the loser gets this instead of a generic 500.
    """


async def create_stream(
    db: AsyncSession,
    *,
    conversation_id: UUID,
) -> Stream:
    """Insert an `active` stream row for the conversation. Flush + refresh.

    Raises `ActiveStreamExistsError` when the partial unique index
    (`ix_stream_conversation_active_unique`) rejects a second concurrent active
    stream for the same conversation. The caller (the route) rolls back and
    returns 409. The flush is wrapped in a SAVEPOINT (`db.begin_nested`) so the
    IntegrityError doesn't poison the outer transaction — only the nested insert
    is rolled back, leaving the session usable for the 409 response.
    """
    row = Stream(
        conversation_id=conversation_id,
        status="active",
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError as exc:
        raise ActiveStreamExistsError(str(conversation_id)) from exc
    await db.refresh(row)
    return row


async def mark_status(
    db: AsyncSession,
    *,
    stream_id: UUID,
    status: str,
    message_id: UUID | None = None,
    release_active_guard: bool = False,
) -> None:
    """Set `status` (and optionally `message_id`) + bump `updated_at`. Flush.

    Silent no-op if the row is gone. `message_id` is only written when a
    non-None value is passed so a later status transition doesn't clobber a
    pointer set by an earlier one.

    A stop request is not the same thing as producer termination. The stop
    route records intent by calling `mark_status(..., status="stopped")` before
    the provider task has flushed the partial assistant row. When that call has
    no `message_id`, keep the row `active` so the single-active-stream guard
    remains in force until the producer comes back through this repository with
    the persisted assistant id. Shutdown/cancel paths that really own producer
    termination can pass `release_active_guard=True`.
    """
    stmt = select(Stream).where(Stream.id == stream_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    if status != "stopped" or message_id is not None or release_active_guard:
        row.status = status
    if message_id is not None:
        row.message_id = message_id
    row.updated_at = datetime.now(UTC)
    await db.flush()


async def reap_stale_active(
    db: AsyncSession,
    *,
    older_than: timedelta,
) -> int:
    """Transition orphaned `active` stream rows to a terminal state. Flush.

    Closes the hard-crash gap (PRD 04 §5.1): a SIGKILL / OOM / power loss kills
    the worker mid-stream WITHOUT running any Python exception path (not even
    `asyncio.CancelledError`), so the handler's cleanup never fires and the
    row strands at `status="active"` forever. This sweeps every `active` row
    whose `updated_at` is older than `older_than` and marks it `"error"`.

    Why `"error"` and not `"stopped"`: `"stopped"` means the *user* (or a
    graceful disconnect/shutdown) ended the turn — an intentional, clean stop.
    An orphan is a turn that did NOT complete normally and was never explicitly
    stopped; the worker died under it. `"error"` is the honest terminal state
    for "this turn failed / never finished" and keeps the lifecycle observable
    (the `error` semantics already mean "did not persist a clean assistant
    row", which matches an orphan).

    Liveness guarantee: the cutoff is keyed on `updated_at`, which
    `mark_status` bumps on EVERY transition (see above). A genuinely in-flight
    turn keeps a fresh `updated_at`; only rows untouched for longer than
    `older_than` are reaped. The caller picks `older_than` (from
    `settings.stream_reap_after_seconds`) comfortably larger than the longest
    plausible live turn, so a live stream is never reaped. NOTE: for MVP turns
    last seconds, so a static TTL with no heartbeating is safe. If a turn could
    ever plausibly exceed the TTL, the handler should heartbeat `updated_at`
    mid-stream; we deliberately do NOT add heartbeating now.

    Single bulk `UPDATE` — dialect-safe (Postgres prod + SQLite tests): the
    cutoff is computed in Python and passed as a bound parameter, and
    `updated_at` is set to a Python `datetime` rather than a SQL `now()`, so no
    dialect-specific time function is involved. Returns the number of rows
    reaped.
    """
    cutoff = datetime.now(UTC) - older_than
    stmt = (
        update(Stream)
        .where(Stream.status == "active", Stream.updated_at < cutoff)
        .values(status="error", updated_at=datetime.now(UTC))
    )
    result = await db.execute(stmt)
    await db.flush()
    # `rowcount` is reliable for a bulk UPDATE on both asyncpg and aiosqlite.
    # `execute()` is typed as returning `Result`, but a DML statement yields a
    # `CursorResult` at runtime (the only kind that carries `rowcount`); cast so
    # the attribute is typed without laundering through `Any`.
    return cast("CursorResult[Any]", result).rowcount


async def get_by_id(
    db: AsyncSession,
    *,
    stream_id: UUID,
) -> Stream | None:
    """Return the `stream` row for `stream_id`, else None.

    Used by the resumable-stream reconnect endpoint to assert the stream
    belongs to the requested conversation (ownership is checked one hop up via
    the conversation). No status filter — a reconnect may land after the row is
    already `done` / `stopped` (replay the final buffered sequence within TTL).
    """
    stmt = select(Stream).where(Stream.id == stream_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_active_for_conversation(
    db: AsyncSession,
    *,
    conversation_id: UUID,
) -> Stream | None:
    """Return the newest stream still guarding the conversation, else None.

    The explicit-stop route calls `mark_status(status="stopped")` before the
    producer has actually stopped; that repository call intentionally leaves
    the row `active`, so the route can be wired safely without releasing the
    guard early.
    """
    stmt = (
        select(Stream)
        .where(
            Stream.conversation_id == conversation_id,
            Stream.status == "active",
        )
        .order_by(Stream.created_at.desc(), Stream.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
