"""One durable envelope shared by a turn's generator and its sink (AC-11).

`stream_and_persist` used to guard its own lifecycle with a `finally` the sink
could not see. That left two escapes. Fallible setup after the `submitted`
frame — approval settlement, the prior-row load, source resolution, pump
creation, seeded execution — ran BEFORE that guard, so a failure there returned
without releasing the budget reservation or closing the durable `stream` row.
And `run_detached_producer`, whose `buffer.append()` is the real sink, caught its
own append failure and left the generator suspended at a `yield`, so the
generator's `finally` never ran at all: the pump kept pulling from the provider
and the reservation stayed held.

So the generator and the wrapper hold ONE of these. The generator registers the
work it starts and reports the durable commits it makes; the wrapper reports sink
failure. This object is the only thing that selects an outcome — the wrapper
never infers a second one and never writes the database itself.

Every method is idempotent, because the generator's `finally`, the wrapper's
exception handling and `aclose()` can all reach the same instance for the same
turn. The pre/post-commit distinction is what makes that safe: before the durable
commit a failure cancels the registered work, marks the stream `error`, releases
the reservation and clears the stop signal; after it, the committed result stands
and a delivery failure rewrites neither status nor spend.

Not a settlement planner. It owns no event reduction, no persistence policy and
no cost arithmetic (deferred STREAM-Q004 stays deferred).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Literal
from uuid import UUID

from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.runtime.context import RuntimeContext
from app.streaming.stop_registry import clear_stop_async

log = logging.getLogger(__name__)

# A durably committed turn outcome. `error` is not here: an errored turn commits
# no assistant row, so it is a failure the latch selects, not a result reported.
CommittedOutcome = Literal["done", "paused", "stopped"]
TurnOutcome = Literal["done", "paused", "stopped", "error"]
FailureStage = Literal["source", "delivery"]


class TurnLifecycle:
    """The outcome latch and cleanup owner for one streaming turn."""

    def __init__(
        self,
        *,
        runtime: RuntimeContext,
        stream_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        self._runtime = runtime
        self._stream_id = stream_id
        self._user_id = user_id
        self._registered: list[asyncio.Task[Any]] = []
        self._outcome: TurnOutcome | None = None
        self._committed = False
        self._failure: BaseException | None = None
        self._failure_stage: FailureStage | None = None
        self._closed = False

    # --- observation ---------------------------------------------------------

    @property
    def outcome(self) -> TurnOutcome | None:
        """The single selected outcome, or None while the turn is still open."""
        return self._outcome

    @property
    def committed(self) -> bool:
        return self._committed

    @property
    def failure(self) -> BaseException | None:
        return self._failure

    @property
    def failure_stage(self) -> FailureStage | None:
        return self._failure_stage

    @property
    def closed(self) -> bool:
        return self._closed

    # --- registration --------------------------------------------------------

    def register_producer(self, task: asyncio.Task[Any]) -> None:
        """Register work that must not outlive the turn (the provider pump).

        A fallback retry starts a second pump; both are registered and cancelling
        an already-finished task is a no-op, so re-registration is safe.
        """
        if task not in self._registered:
            self._registered.append(task)

    async def cancel_registered(self) -> None:
        """Cancel and join every registered task. Safe to call repeatedly."""
        pending = [task for task in self._registered if not task.done()]
        for task in pending:
            task.cancel()
        for task in pending:
            # The pump forwards real provider exceptions through its queue and
            # never re-raises on await, so nothing genuine is hidden here.
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # --- outcome selection ---------------------------------------------------

    def record_commit(self, outcome: CommittedOutcome) -> None:
        """Latch the turn's durable result. The first commit wins.

        Called once the assistant row (or the deliberate decision not to persist
        one, on a temporary turn) is settled, and always BEFORE the terminal
        frame is delivered — that ordering is what makes a terminal-frame sink
        failure a post-commit event rather than a reason to unwind the turn.
        """
        if self._committed:
            return
        self._committed = True
        self._outcome = outcome

    async def source_failed(self, exc: BaseException) -> None:
        """Report a producer-side failure: setup, or the source itself."""
        await self._failed("source", exc)

    async def delivery_failed(self, exc: BaseException) -> None:
        """Report a sink-side failure — `buffer.append()`, or the inline yield.

        The caller closes the generator afterwards; that runs the generator's own
        `finally`, which reaches `close()` on this same instance.
        """
        await self._failed("delivery", exc)

    async def _failed(self, stage: FailureStage, exc: BaseException) -> None:
        if self._failure is None:
            self._failure = exc
            self._failure_stage = stage
        if self._committed:
            # The durable result stands: no re-charge, no status rewrite. Only
            # the delivery of an already-committed turn is known to have failed.
            log.warning(
                "turn.%s_failed_after_commit",
                stage,
                exc_info=exc,
                extra={"outcome": self._outcome},
            )
            return
        self._outcome = "error"
        await self._mark_stream_error()
        await self.close()

    # --- cleanup -------------------------------------------------------------

    async def close(self) -> None:
        """Release everything the turn held. Runs its body exactly once.

        Cancels registered work, drops the live stop signal and releases the
        platform-budget hold. Reached from the generator's `finally` on every
        path, and directly from a pre-commit failure so a setup crash that never
        entered that `finally` still lands here.
        """
        if self._closed:
            return
        self._closed = True
        await self.cancel_registered()
        await self._clear_stop()
        await self._release_reservation()

    async def hard_cancelled(self) -> None:
        """Close durable stream bookkeeping for a hard cancel (worker shutdown).

        A `CancelledError` mid-turn is an interruption, not a provider failure,
        so an uncommitted turn terminalizes as `stopped` with the single-active
        guard released — otherwise the row strands at `active` until the orphan
        reaper sweeps it.

        Commit-aware, and that is the point: the terminal frame is delivered
        AFTER the durable commit, so a cancel landing on that yield used to
        rewrite a `done` row (message id and all) to `stopped`. A committed
        outcome stands; only its last frame was lost.
        """
        if self._committed or self._stream_id is None:
            return
        self._outcome = "stopped"
        try:
            async with self._runtime.session_factory() as db:
                await streams_repo.mark_status(
                    db,
                    stream_id=self._stream_id,
                    status="stopped",
                    release_active_guard=True,
                )
                await db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("stream.mark_cancelled.failed", exc_info=exc)

    async def _mark_stream_error(self) -> None:
        """Terminalize the durable `stream` row for a pre-commit failure.

        Best-effort on a fresh session: the request session may be poisoned by
        the same failure, and bookkeeping must never become the error the caller
        sees instead of the real one.
        """
        if self._stream_id is None:
            return
        try:
            async with self._runtime.session_factory() as db:
                await streams_repo.mark_status(db, stream_id=self._stream_id, status="error")
                await db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("stream.mark_error.failed", exc_info=exc)

    async def _release_reservation(self) -> None:
        """B9: drop the platform headroom hold for this stream (idempotent)."""
        if self._stream_id is None or self._user_id is None:
            return
        try:
            async with self._runtime.session_factory() as db:
                await usage_repo.release_platform_budget(db, stream_id=self._stream_id)
                await db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("budget.reservation_release.failed", exc_info=exc)

    async def _clear_stop(self) -> None:
        """Drop the live stop signal so a later turn cannot inherit it."""
        if self._stream_id is None:
            return
        with contextlib.suppress(Exception):
            await clear_stop_async(self._stream_id)
