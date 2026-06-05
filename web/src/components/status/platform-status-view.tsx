"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Loader2, RotateCw, TriangleAlert } from "lucide-react";

import { ThemeToggle } from "@/components/chat/theme-toggle";
import { Button } from "@/components/ui/button";
import { fetchPlatformStatus } from "@/lib/apiClient";
import type { PlatformStatus } from "@/lib/types";

// Public status page (PRD 08 §10). A calm operational/degraded summary fetched
// client-side from the PUBLIC `/api/status` route (no auth). Mirrors the
// structure of the public share view: a server-component shell owns metadata,
// this client component owns the live fetch + states.

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; status: PlatformStatus }
  | { kind: "error" };

const TIME_FMT = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return TIME_FMT.format(parsed);
}

export function PlatformStatusView() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (attempt > 0) setState({ kind: "loading" });
    void (async () => {
      try {
        const status = await fetchPlatformStatus(controller.signal);
        if (controller.signal.aborted) return;
        setState({ kind: "ready", status });
      } catch {
        if (controller.signal.aborted) return;
        setState({ kind: "error" });
      }
    })();
    return () => controller.abort();
  }, [attempt]);

  return (
    <div className="relative flex min-h-dvh flex-col bg-background text-foreground">
      <StatusHeader />
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 pt-[calc(env(safe-area-inset-top)+4rem)] pb-16 md:pt-[calc(env(safe-area-inset-top)+5.5rem)]">
        {state.kind === "loading" ? <LoadingState /> : null}
        {state.kind === "error" ? (
          <ErrorState onRetry={() => setAttempt((n) => n + 1)} />
        ) : null}
        {state.kind === "ready" ? <StatusBody status={state.status} /> : null}
      </main>
    </div>
  );
}

function StatusHeader() {
  return (
    <header className="fixed inset-x-0 top-0 z-40 flex h-[46px] items-center gap-2 bg-gradient-to-b from-background/70 via-background/30 to-background/0 px-[max(env(safe-area-inset-left),1.25rem)] pr-[max(env(safe-area-inset-right),1.25rem)] pt-[env(safe-area-inset-top)] md:h-16">
      <div
        aria-hidden
        className="chrome-frost pointer-events-none absolute inset-0 -z-10"
        style={{
          maskImage: "linear-gradient(to bottom, black, transparent)",
          WebkitMaskImage: "linear-gradient(to bottom, black, transparent)",
        }}
      />
      <Link
        href="/"
        className="flex items-center gap-2 rounded-sm font-medium text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
        aria-label="Olune home"
      >
        <span className="text-base font-semibold tracking-tight">Olune</span>
        <span className="hidden text-sm text-muted-foreground sm:inline">
          · status
        </span>
      </Link>
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        <Button
          nativeButton={false}
          render={<Link href="/" />}
          variant="secondary"
          className="h-11 rounded-full px-3.5 text-sm sm:h-9"
        >
          Back to chat
        </Button>
      </div>
    </header>
  );
}

function StatusBody({ status }: { status: PlatformStatus }) {
  const degraded = status.status === "degraded";
  const windowMinutes = Math.round(status.windowSeconds / 60);
  return (
    <div className="flex flex-1 flex-col" data-testid="platform-status">
      <div
        className="glass-clear flex items-start gap-4 rounded-3xl px-5 py-6"
        data-status={status.status}
      >
        {degraded ? (
          <TriangleAlert
            aria-hidden
            className="mt-0.5 size-8 shrink-0 text-warning"
          />
        ) : (
          <CheckCircle2
            aria-hidden
            className="mt-0.5 size-8 shrink-0 text-emerald-500 dark:text-emerald-400"
          />
        )}
        <div className="min-w-0 space-y-1">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">
            {degraded
              ? "Some requests are failing"
              : "All systems operational"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {degraded
              ? "We're seeing an elevated error rate on recent requests. You may hit failures or retries — we're on it."
              : "Recent requests are completing normally. There are no known platform issues right now."}
          </p>
        </div>
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Sample window</dt>
          <dd className="mt-0.5 font-medium tabular-nums">
            last {windowMinutes} min
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Recent requests</dt>
          <dd className="mt-0.5 font-medium tabular-nums">
            {status.sampleSize.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Errors</dt>
          <dd className="mt-0.5 font-medium tabular-nums">
            {status.errorCount.toLocaleString()}
          </dd>
        </div>
      </dl>

      <p className="mt-6 text-xs text-muted-foreground">
        Updated {formatTimestamp(status.updatedAt)}. This page reflects
        platform-wide health derived from recent traffic, not your individual
        account.
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div
      className="flex flex-1 items-center justify-center py-24 text-muted-foreground"
      role="status"
    >
      <Loader2 className="size-5 motion-safe:animate-spin" aria-hidden />
      <span className="sr-only">Loading platform status…</span>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 py-24 text-center">
      <div className="space-y-1.5">
        <h1 className="text-lg font-semibold tracking-tight">
          Couldn&apos;t load platform status
        </h1>
        <p className="mx-auto max-w-sm text-sm text-muted-foreground">
          Something went wrong reaching the server. Check your connection and
          try again.
        </p>
      </div>
      <Button
        type="button"
        variant="secondary"
        onClick={onRetry}
        className="h-10 rounded-full px-4 text-sm"
      >
        <RotateCw aria-hidden className="size-4" />
        <span>Try again</span>
      </Button>
    </div>
  );
}
