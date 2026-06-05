"""Scheduled retention purge (D31).

Retention has historically been enforced OPPORTUNISTICALLY: an expired
conversation was only deleted the next time its owner hit a read path
(bootstrap, history read, export). That leaves a dormant account's expired data
on disk indefinitely. This module adds a real SCHEDULED sweep that deletes
expired conversations across ALL users on an interval, honoring the
per-conversation `retention_days` override else the owner's global
`preferences.retention_days` (see
`app.db.repositories.conversations.delete_expired_all_users`).

Modeled exactly on the orphan-stream reaper (`app.streaming.reaper`) — two
trigger seams, both wired from `app.main`'s lifespan:

- `purge_once`: a single best-effort sweep on a fresh session. Run once at
  startup and on each background tick.
- `run_purge_loop`: a lightweight detached `asyncio` task that calls
  `purge_once` on an interval. Cancelled cleanly on shutdown.

Single-process caveat (same as the reaper / `_TEMP_IDS` / the slowapi in-memory
store): this loop runs in-process. Behind multiple uvicorn workers each process
runs its own loop — harmless because the underlying deletes are idempotent (a
row already purged by another worker simply isn't a candidate), but a
production-grade purge belongs in a single coordinated job (cron / Redis-locked
worker), not every web process. See `app.config.Settings.retention_purge_*`.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import conversations as conversations_repo

_log = structlog.get_logger(__name__)


async def purge_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """Run a single retention-purge sweep on a fresh session. Best-effort.

    Owns its own session (never a request session). Swallows + logs any error so
    a transient DB hiccup neither blocks startup nor kills the loop. Returns the
    number of conversations purged (0 on failure).
    """
    try:
        async with session_factory() as session:
            purged = await conversations_repo.delete_expired_all_users(session)
            await session.commit()
        if purged:
            _log.info("retention.purge.swept", count=purged)
        return purged
    except Exception as exc:  # pragma: no cover - defensive
        _log.warning("retention.purge.failed", exc_info=exc)
        return 0


async def run_purge_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_seconds: float,
) -> None:
    """Periodic purge: sweep once immediately, then every `interval_seconds`.

    Runs until cancelled (lifespan shutdown). Each tick is best-effort via
    `purge_once`, so the loop never dies on a transient error. `CancelledError`
    propagates so the lifespan can await a clean shutdown.
    """
    await purge_once(session_factory)
    while True:
        await asyncio.sleep(interval_seconds)
        await purge_once(session_factory)
