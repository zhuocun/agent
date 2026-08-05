"""Worker fan-out plumbing for the deep-research orchestrator.

The orchestrator's fan-out is a bounded producer/consumer: N worker tasks relay
their tagged events onto one shared queue while a single consumer drains it in
completion order. That machinery — the concurrency semaphore, the bounded queue
and its drop-oldest teardown policy, the per-worker sentinel that tells the
consumer when a worker has finished putting, and the task lifecycle — is
mechanical and has nothing to say about the run.

It lives here so `_run_deep_research` is left with the decisions only: which
workers to spawn, what a pause means, when the cap or a bound trip kills the
fan-out, and what to synthesize. Nothing in this module reads a budget, a plan or
a ledger.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.agentic.worker import WorkerPaused
from app.providers.protocol import ProviderEvent, SubagentDone


@dataclass(frozen=True)
class _WorkerSentinel:
    """Internal queue marker: a worker has put its last event and finished.

    NOT a `ProviderEvent` — it never escapes the orchestrator; it only lets the
    fan-out merge loop know when every worker has drained so it can stop reading
    the shared queue.
    """

    subagent_id: str


# Everything the fan-out queue can carry: a worker's own provider events, its
# HITL pause, and the per-worker completion sentinel.
FanoutItem = ProviderEvent | _WorkerSentinel | WorkerPaused

# Bound the worker fan-out → consumer queue so a slow drain cannot buffer an
# unbounded number of worker events in process memory (B23). ``await put``
# applies backpressure; teardown uses non-blocking put with drop-oldest.
_FANOUT_QUEUE_MAXSIZE = 256


def _queue_item_is_protected(item: object) -> bool:
    """Teardown must not drop completion control messages (B23)."""
    return isinstance(item, (_WorkerSentinel, SubagentDone, WorkerPaused))


def _queue_put_nowait_drop_oldest(
    queue: asyncio.Queue[Any], item: object
) -> None:
    """Enqueue ``item`` without awaiting; drop oldest *unprotected* if full (B23).

    Used on cancellation / sentinel paths so teardown cannot block forever on a
    full fan-out queue when the consumer has already stopped draining.

    Never drops ``_WorkerSentinel`` / ``SubagentDone`` / ``WorkerPaused`` already
    queued — losing a sentinel can hang the fan-out consumer forever.
    """
    while True:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            held_protected: list[object] = []
            dropped = False
            while True:
                try:
                    old = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not dropped and not _queue_item_is_protected(old):
                    dropped = True
                    continue
                held_protected.append(old)
            for old in held_protected:
                try:
                    queue.put_nowait(old)
                except asyncio.QueueFull:
                    # Only protected items remain and the queue is saturated.
                    # maxsize (>=256) exceeds max workers, so this is unreachable
                    # in production; keep protected items and retry put.
                    break
            if not dropped:
                # Queue holds only protected control messages. If we are
                # inserting another sentinel that is already present, skip;
                # otherwise force one unprotected-style slot by refusing to
                # discard sentinels and relying on maxsize >> worker count.
                if isinstance(item, _WorkerSentinel):
                    # Deduplicate: if an identical sentinel is already queued, done.
                    # (We cannot peek easily after re-queue; treat as success if
                    # put still fails after a no-drop cycle — consumer will drain.)
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(item)
                    return
                # Non-sentinel teardown item with a protected-only full queue:
                # drop nothing further; best-effort put and return.
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(item)
                return


class WorkerFanout:
    """The bounded queue, the concurrency gate and the task set of one fan-out.

    One instance per fan-out. `drain` is the consumer side and it ends when every
    tracked worker has reported its sentinel — which is why `finish` runs in the
    worker's `finally` and why a sentinel is never droppable.

    The producer side is `semaphore` plus `put`, and it deliberately stays a
    borrowed slot rather than a method here: a worker holds its concurrency slot
    across its own terminal decisions (pause / fail / succeed) and puts the
    terminal while still holding it, so wrapping the relay in a method would
    release the slot earlier and change how the fan-out interleaves.
    """

    def __init__(self, *, max_concurrency: int) -> None:
        self.semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self.queue: asyncio.Queue[FanoutItem] = asyncio.Queue(
            maxsize=_FANOUT_QUEUE_MAXSIZE
        )
        self.tasks: list[asyncio.Task[None]] = []

    def track(self, tasks: list[asyncio.Task[None]]) -> None:
        """Adopt the spawned worker tasks, so the drain knows how many sentinels
        to wait for and teardown has one place to cancel and join them."""
        self.tasks = tasks

    async def put(self, item: FanoutItem) -> None:
        """Enqueue with backpressure — the bound is what makes it backpressure."""
        await self.queue.put(item)

    def put_nowait_drop_oldest(self, item: FanoutItem) -> None:
        """Enqueue from a teardown path that must never block (B23)."""
        _queue_put_nowait_drop_oldest(self.queue, item)

    def finish(self, subagent_id: str) -> None:
        """Report one worker drained. B23: must not block on a full queue."""
        self.put_nowait_drop_oldest(_WorkerSentinel(subagent_id))

    async def drain(self) -> AsyncIterator[ProviderEvent | WorkerPaused]:
        """Yield every worker event in completion order until all are drained.

        Sentinels are the fan-out's own control messages and are counted here
        rather than surfaced: one per tracked worker, so the consumer stops
        exactly when the last worker has put its last item.
        """
        remaining = len(self.tasks)
        while remaining > 0:
            item = await self.queue.get()
            if isinstance(item, _WorkerSentinel):
                remaining -= 1
                continue
            yield item

    def cancel_pending(self) -> None:
        """Cancel every worker that has not finished. Idempotent."""
        for task in self.tasks:
            if not task.done():
                task.cancel()

    async def join(self) -> list[None | BaseException]:
        """Await every worker task, surfacing outcomes instead of raising.

        `return_exceptions=True` because a cancelled worker is the normal shape
        of a budget kill; the caller decides which outcomes are worth logging.
        """
        return await asyncio.gather(*self.tasks, return_exceptions=True)
