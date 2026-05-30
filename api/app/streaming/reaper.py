"""Orphan-stream reaper (PRD 04 §5.1).

Closes the hard-crash gap in the `stream` lifecycle. The handler transitions
rows on graceful completion, client disconnect, provider error, and on
`asyncio.CancelledError` (graceful shutdown). But a HARD crash — SIGKILL / OOM
/ power loss — runs NO Python exception path, so the handler's cleanup never
fires and the row strands at `status="active"` forever. This module sweeps
those orphans to a terminal `"error"` state (see
`app.db.repositories.streams.reap_stale_active` for the why-`error` rationale).

Two trigger seams, both wired from `app.main`'s lifespan:

- `reap_once`: a single best-effort sweep on a fresh session. Run at startup
  (a fresh process knows any `active` row it didn't create is orphaned from a
  prior crash) and on each background tick.
- `run_reaper_loop`: a lightweight detached `asyncio` task that calls
  `reap_once` on an interval. Cancelled cleanly on shutdown.

Single-process caveat (same as `_TEMP_IDS` / `stop_registry` / the slowapi
in-memory store): this loop runs in-process. Behind multiple uvicorn workers
each process runs its own loop — harmless because the underlying bulk UPDATE is
idempotent and keyed on a shared DB column, but a production-grade reaper
belongs in a single coordinated job (cron / Redis-locked worker), not every web
process. See `app.config.Settings.stream_reap_after_seconds`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import streams as streams_repo

_log = structlog.get_logger(__name__)


async def reap_once(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    older_than: timedelta,
) -> int:
    """Run a single reap sweep on a fresh session. Best-effort.

    Owns its own session (never a request session). Swallows + logs any error
    so a transient DB hiccup neither blocks startup nor kills the loop. Returns
    the number of rows reaped (0 on failure).
    """
    try:
        async with session_factory() as session:
            reaped = await streams_repo.reap_stale_active(
                session, older_than=older_than
            )
            await session.commit()
        if reaped:
            _log.warning("stream.reaper.reaped", count=reaped)
        return reaped
    except Exception as exc:  # pragma: no cover - defensive
        _log.warning("stream.reaper.failed", exc_info=exc)
        return 0


async def run_reaper_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    older_than: timedelta,
    interval_seconds: float,
) -> None:
    """Periodic reaper: sweep once immediately, then every `interval_seconds`.

    Runs until cancelled (lifespan shutdown). Each tick is best-effort via
    `reap_once`, so the loop never dies on a transient error. `CancelledError`
    propagates so the lifespan can await a clean shutdown.
    """
    await reap_once(session_factory, older_than=older_than)
    while True:
        await asyncio.sleep(interval_seconds)
        await reap_once(session_factory, older_than=older_than)
