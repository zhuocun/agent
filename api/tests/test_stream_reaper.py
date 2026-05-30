"""Orphan-stream reaper tests (PRD 04 §5.1).

Covers the hard-crash gap: a SIGKILL / OOM / power loss leaves a `stream` row
stranded at `status="active"` forever because no Python cleanup runs. The
reaper sweeps `active` rows whose `updated_at` is older than the TTL to
`"error"` (not `"stopped"` — the user never stopped them; the turn did not
complete normally).

Three layers:
- `reap_stale_active` repo function: reaps stale, spares fresh, ignores
  already-terminal rows, returns the right count.
- `reap_once` / `run_reaper_loop`: the best-effort wrappers used by the
  lifespan seams.
- the `app.main` lifespan: a smoke test that the startup sweep + background
  task wire up and tear down without error. No real timers — the interval is
  cranked huge so the loop parks on the first sleep and is cancelled on exit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Stream, User
from app.db.repositories import streams as streams_repo
from app.streaming.reaper import reap_once, run_reaper_loop

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
) -> UUID:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        convo = Conversation(
            user_id=user.id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return convo.id


async def _seed_stream(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conversation_id: UUID,
    status: str,
    updated_age: timedelta,
) -> UUID:
    """Insert a stream row with an artificially-aged `updated_at`."""
    async with session_factory() as session:
        row = Stream(conversation_id=conversation_id, status=status)
        row.updated_at = datetime.now(UTC) - updated_age
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def _status_of(
    session_factory: async_sessionmaker[AsyncSession], stream_id: UUID
) -> str:
    async with session_factory() as session:
        row = (
            await session.execute(select(Stream).where(Stream.id == stream_id))
        ).scalar_one()
        return row.status


# Repo function ----------------------------------------------------------------


async def test_reap_marks_stale_active_as_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An `active` row older than the TTL is reaped to `error`; count is 1."""
    conv_id = await _seed_conversation(session_factory)
    stale_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(hours=1),
    )

    async with session_factory() as session:
        reaped = await streams_repo.reap_stale_active(
            session, older_than=timedelta(minutes=15)
        )
        await session.commit()

    assert reaped == 1
    assert await _status_of(session_factory, stale_id) == "error"


async def test_reap_spares_fresh_active(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A recently-updated `active` row (a live turn) is NOT reaped."""
    conv_id = await _seed_conversation(session_factory)
    fresh_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(seconds=2),
    )

    async with session_factory() as session:
        reaped = await streams_repo.reap_stale_active(
            session, older_than=timedelta(minutes=15)
        )
        await session.commit()

    assert reaped == 0
    assert await _status_of(session_factory, fresh_id) == "active"


async def test_reap_ignores_terminal_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Already-terminal `done` / `stopped` / `error` rows are never touched,
    even when old."""
    conv_id = await _seed_conversation(session_factory)
    done_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="done",
        updated_age=timedelta(hours=2),
    )
    stopped_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="stopped",
        updated_age=timedelta(hours=2),
    )
    error_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="error",
        updated_age=timedelta(hours=2),
    )

    async with session_factory() as session:
        reaped = await streams_repo.reap_stale_active(
            session, older_than=timedelta(minutes=15)
        )
        await session.commit()

    assert reaped == 0
    assert await _status_of(session_factory, done_id) == "done"
    assert await _status_of(session_factory, stopped_id) == "stopped"
    assert await _status_of(session_factory, error_id) == "error"


async def test_reap_counts_only_stale_active_among_mixed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """With a mix of stale-active, fresh-active, and terminal rows, only the
    stale-active ones are reaped and the count reflects exactly those."""
    conv_id = await _seed_conversation(session_factory)
    stale_a = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(hours=1),
    )
    stale_b = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(hours=3),
    )
    fresh = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(seconds=1),
    )
    done = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="done",
        updated_age=timedelta(hours=5),
    )

    async with session_factory() as session:
        reaped = await streams_repo.reap_stale_active(
            session, older_than=timedelta(minutes=15)
        )
        await session.commit()

    assert reaped == 2
    assert await _status_of(session_factory, stale_a) == "error"
    assert await _status_of(session_factory, stale_b) == "error"
    assert await _status_of(session_factory, fresh) == "active"
    assert await _status_of(session_factory, done) == "done"


# reap_once / loop wrappers ----------------------------------------------------


async def test_reap_once_commits_and_returns_count(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`reap_once` owns its own session, commits, and returns the reaped count."""
    conv_id = await _seed_conversation(session_factory)
    stale_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(hours=1),
    )

    reaped = await reap_once(session_factory, older_than=timedelta(minutes=15))

    assert reaped == 1
    # The commit is durable: a fresh session sees the reaped status.
    assert await _status_of(session_factory, stale_id) == "error"


async def test_run_reaper_loop_sweeps_then_cancels_cleanly(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The loop sweeps once immediately, then parks on the interval sleep.

    Cancelling it (lifespan shutdown) propagates `CancelledError` cleanly.
    The interval is huge so the test never waits on a real timer — we only
    assert the immediate first sweep happened, then cancel.
    """
    import asyncio

    conv_id = await _seed_conversation(session_factory)
    stale_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(hours=1),
    )

    task = asyncio.create_task(
        run_reaper_loop(
            session_factory,
            older_than=timedelta(minutes=15),
            interval_seconds=3600.0,  # parks here after the first sweep
        )
    )
    # Yield until the first immediate sweep has committed.
    for _ in range(50):
        if await _status_of(session_factory, stale_id) == "error":
            break
        await asyncio.sleep(0.01)

    assert await _status_of(session_factory, stale_id) == "error"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# Lifespan smoke ---------------------------------------------------------------


async def test_lifespan_runs_reaper_seams_without_error(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `app.main` lifespan runs the startup sweep + background task and
    tears them down without error.

    We point the reaper's session factory at the per-test SQLite factory (the
    real `get_session_factory()` is bound to the env DATABASE_URL, wrong in
    tests) and crank the interval huge so no real timer fires. Asserts the
    startup sweep actually reaped the seeded orphan.
    """
    import app.main as main_mod

    conv_id = await _seed_conversation(session_factory)
    stale_id = await _seed_stream(
        session_factory,
        conversation_id=conv_id,
        status="active",
        updated_age=timedelta(hours=1),
    )

    # Redirect the reaper at the per-test factory and disable the real timer.
    monkeypatch.setattr(main_mod, "get_session_factory", lambda: session_factory)

    from app.config import Settings

    settings = Settings(
        stream_reap_after_seconds=900,
        stream_reap_interval_seconds=3600,
    )
    lifespan = main_mod._build_lifespan(settings)

    from fastapi import FastAPI

    app = FastAPI()
    async with lifespan(app):
        # Startup sweep reaped the orphan.
        assert await _status_of(session_factory, stale_id) == "error"
    # Exiting the context cancels the background task cleanly (no raise here).
