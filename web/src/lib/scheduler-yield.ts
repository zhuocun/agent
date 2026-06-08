"use client";

// Cooperative scheduling helper. Long synchronous tasks (e.g. an optimistic
// send that mutates a big message list, kicks off a fetch, and resets the
// composer all in one click handler) block the main thread and inflate INP.
// `yieldToMain()` breaks such a task into smaller chunks: it returns a promise
// that resolves AFTER the browser has had a chance to handle pending input and
// paint, so `await yieldToMain()` mid-handler hands control back to the event
// loop.
//
// Prefer the standardized `scheduler.yield()` (Prioritized Task Scheduling) when
// the browser exposes it — it re-queues the continuation at user-visible
// priority so it resumes promptly without starving input. Fall back to a
// `MessageChannel`-backed macrotask (more reliable than `setTimeout(0)`, which
// browsers clamp/throttle), and finally to `setTimeout(0)` where neither
// exists. SSR (no `window`) resolves immediately.

interface SchedulerWithYield {
  yield?: () => Promise<void>;
}

function getScheduler(): SchedulerWithYield | null {
  if (typeof globalThis === "undefined") return null;
  const scheduler = (globalThis as { scheduler?: SchedulerWithYield }).scheduler;
  return scheduler ?? null;
}

export function yieldToMain(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();

  const scheduler = getScheduler();
  if (scheduler && typeof scheduler.yield === "function") {
    // `scheduler.yield()` can reject if the document is detached mid-yield;
    // never let that surface as an unhandled rejection in a UI handler.
    return scheduler.yield().catch(() => undefined);
  }

  if (typeof MessageChannel !== "undefined") {
    return new Promise<void>((resolve) => {
      const channel = new MessageChannel();
      channel.port1.onmessage = () => {
        channel.port1.close();
        resolve();
      };
      channel.port2.postMessage(undefined);
    });
  }

  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, 0);
  });
}
