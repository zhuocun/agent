"use client";

import { useEffect, useState, type JSX } from "react";
import Link from "next/link";
import { TriangleAlert, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { fetchPlatformStatus } from "@/lib/apiClient";
import { cn } from "@/lib/utils";

export interface DegradedStatusBannerProps {
  className?: string;
}

// Light poll interval. Calm, never spammy: one fetch on mount, then once a
// minute. The banner only ever renders when the platform reports `degraded`.
const POLL_INTERVAL_MS = 60_000;

// Calm, dismissible degraded-platform banner (PRD 08 §10). Self-contained: it
// polls the PUBLIC `/api/status` route on mount + a light interval and renders
// nothing unless the platform is `degraded` (and the user hasn't dismissed it).
// Links to the full `/status` page. Dismissal is per-mount — a fresh load
// re-checks — so a user is never permanently blind to an ongoing incident.
export function DegradedStatusBanner({
  className,
}: DegradedStatusBannerProps): JSX.Element | null {
  const [degraded, setDegraded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const poll = async (): Promise<void> => {
      try {
        const status = await fetchPlatformStatus(controller.signal);
        if (cancelled) return;
        setDegraded(status.status === "degraded");
      } catch {
        // A failed status check is not itself an incident signal — leave the
        // banner state untouched so a transient blip never flashes the banner.
      }
    };

    void poll();
    const id = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(id);
    };
  }, []);

  if (!degraded || dismissed) return null;

  return (
    <div className={cn("flex justify-center px-3 pt-1", className)}>
      <div
        role="status"
        data-testid="degraded-status-banner"
        className="inline-flex h-11 max-w-full items-center gap-1.5 rounded-full bg-warning pl-3 pr-1 text-xs text-warning-foreground ring-1 ring-warning-foreground/20"
      >
        <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
        <span className="min-w-0">
          <span className="font-medium">Service degraded</span>
          <span className="hidden sm:inline">
            {" "}
            — some requests may fail.
          </span>
        </span>
        <Button
          nativeButton={false}
          render={<Link href="/status" />}
          variant="ghost"
          size="xs"
          className="ml-0.5 h-11 px-3 text-xs underline-offset-4 hover:underline"
        >
          View status
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          aria-label="Dismiss"
          onClick={() => setDismissed(true)}
          className="-mr-1 size-11 shrink-0 rounded-full px-0"
        >
          <X aria-hidden className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
