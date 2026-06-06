"use client";

import { useEffect, useState, type JSX } from "react";
import { Globe, ShieldCheck } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { fetchActivity, fetchDataProcessing } from "@/lib/apiClient";
import type { ActivityEvent, DataProcessingRollup } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface ActivityDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  // Open the model picker so the user can switch their route. Wired by the
  // parent to the existing composer picker; when absent the affordance hides.
  onSwitchRoute?: () => void;
}

const PAGE_SIZE = 25;

// Human-readable labels for each audit `eventType`. The backend keeps the wire
// codes stable; this is the only place that turns them into calm sentences.
const EVENT_LABELS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.upgrade": "Created your account",
  "auth.signout": "Signed out",
  "byok.upsert": "Saved a provider API key",
  "byok.revoke": "Removed a provider API key",
  "account.export": "Exported your data",
  "account.delete": "Deleted an account",
  "share.mint": "Created a public share link",
  "share.revoke": "Removed a public share link",
  "retention.purge": "Old chats removed by your retention setting",
  "moderation.blocked": "A message was blocked by a safety rule",
  "moderation.appeal": "Requested a review of a blocked message",
};

function eventLabel(eventType: string): string {
  return (
    EVENT_LABELS[eventType] ??
    eventType
      .split(/[._]/)
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

const TIME_FMT = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return TIME_FMT.format(parsed);
}

// "N messages processed in <jurisdiction> (<provider>)" — first-class honest
// facts. A provider with no published policy renders as "policy unavailable".
function jurisdictionPhrase(jurisdiction: string | null): string {
  return jurisdiction ?? "an undisclosed region (policy unavailable)";
}

function SectionHeading({ children }: { children: string }): JSX.Element {
  return (
    <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
      {children}
    </h3>
  );
}

// Activity & data-access surface (PRD 07 §6.5 / PRD 05 §7.4 / PRD 08 §5.6).
// Read-only: the data-access log + the "where your messages were processed"
// rollup. Both endpoints accept anonymous callers and only ever return the
// caller's own data.
export function ActivityDialog({
  open,
  onOpenChange,
  onSwitchRoute,
}: ActivityDialogProps): JSX.Element {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [rollup, setRollup] = useState<DataProcessingRollup | null>(null);
  // `loaded` flips true after the first fetch settles (success OR error); the
  // loading state is derived from it so we never setState synchronously in the
  // effect body (repo lints react-hooks/set-state-in-effect).
  const [loaded, setLoaded] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the first page + rollup whenever the dialog opens. Every setState here
  // runs only AFTER an await, mirroring the bootstrap effect — nothing fires
  // synchronously during the effect body.
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    let cancelled = false;
    void (async () => {
      try {
        const [firstPage, processing] = await Promise.all([
          fetchActivity(undefined, PAGE_SIZE, controller.signal),
          fetchDataProcessing(controller.signal),
        ]);
        if (cancelled) return;
        setEvents(firstPage);
        setRollup(processing);
        setHasMore(firstPage.length === PAGE_SIZE);
        setLoaded(true);
      } catch {
        if (cancelled) return;
        setError("Couldn't load your activity. Please try again.");
        setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [open]);

  const loading = open && !loaded && error === null;

  // Reset transient state on close so a re-open refetches from a clean slate.
  // Driven from the close path (an event handler, not an effect).
  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setEvents([]);
      setRollup(null);
      setLoaded(false);
      setHasMore(false);
      setError(null);
      setLoadingMore(false);
    }
    onOpenChange(next);
  };

  const handleLoadMore = async (): Promise<void> => {
    const oldest = events[events.length - 1];
    if (!oldest || loadingMore) return;
    setLoadingMore(true);
    try {
      // Composite keyset cursor `<createdAt>|<id>` — required so a group of
      // events sharing a createdAt (same-request emits / second-resolution
      // timestamps) can't be skipped across the page boundary.
      const next = await fetchActivity(
        `${oldest.createdAt}|${oldest.id}`,
        PAGE_SIZE,
      );
      setEvents((prev) => [...prev, ...next]);
      setHasMore(next.length === PAGE_SIZE);
    } catch {
      setError("Couldn't load more activity. Please try again.");
    } finally {
      setLoadingMore(false);
    }
  };

  const showEmptyActivity = !loading && !error && events.length === 0;
  const buckets = rollup?.byProvider ?? [];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[80dvh] sm:max-h-none"
        data-testid="activity-dialog"
      >
        <DialogHeader>
          <DialogTitle>Activity &amp; data access</DialogTitle>
          <DialogDescription>
            A record of sensitive actions on your account, and where your
            messages were processed. Only you can see this.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 max-h-[60dvh] space-y-6 overflow-y-auto pr-2 sm:max-h-[70dvh]">
          {/* Where your messages were processed */}
          <section className="space-y-3">
            <SectionHeading>Where your messages were processed</SectionHeading>
            {rollup && rollup.totalAttributed > 0 ? (
              <ul className="space-y-2" data-testid="data-processing-list">
                {buckets.map((bucket) => (
                  <li
                    key={bucket.providerId}
                    className="glass-clear space-y-1 rounded-2xl px-3.5 py-3"
                    data-testid="data-processing-bucket"
                  >
                    <div className="flex items-start gap-3">
                      <Globe
                        aria-hidden
                        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      />
                      <div className="min-w-0 flex-1 space-y-1">
                        <p className="text-sm">
                          <span className="font-medium tabular-nums">
                            {bucket.messageCount}
                          </span>{" "}
                          {bucket.messageCount === 1 ? "message" : "messages"}{" "}
                          processed in{" "}
                          <span className="font-medium">
                            {jurisdictionPhrase(bucket.jurisdiction)}
                          </span>{" "}
                          <span className="text-muted-foreground">
                            ({bucket.providerLabel})
                          </span>
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {bucket.platformCount} on platform key
                          {bucket.isByokCount > 0
                            ? `, ${bucket.isByokCount} on your own key`
                            : ""}
                          {bucket.substitutionCount > 0
                            ? ` · ${bucket.substitutionCount} re-routed`
                            : ""}
                        </p>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No processed messages yet. Once you chat, the providers that
                handled your turns appear here.
              </p>
            )}
            {onSwitchRoute ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onSwitchRoute}
                data-testid="activity-switch-route"
              >
                <ShieldCheck aria-hidden className="size-3.5" />
                <span>Change your model route</span>
              </Button>
            ) : null}
          </section>

          {/* Data-access activity log */}
          <section className="space-y-3">
            <SectionHeading>Recent account activity</SectionHeading>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : showEmptyActivity ? (
              <p className="text-sm text-muted-foreground">
                No account activity recorded yet.
              </p>
            ) : (
              <>
                <ul className="space-y-1.5" data-testid="activity-list">
                  {events.map((event) => (
                    <li
                      key={event.id}
                      className="flex items-baseline justify-between gap-3 rounded-xl px-1 py-1.5"
                      data-testid="activity-event"
                    >
                      <span className="min-w-0 text-sm">
                        {eventLabel(event.eventType)}
                      </span>
                      <time
                        dateTime={event.createdAt}
                        className="shrink-0 font-mono text-2xs tabular-nums text-muted-foreground"
                      >
                        {formatTimestamp(event.createdAt)}
                      </time>
                    </li>
                  ))}
                </ul>
                {hasMore ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => void handleLoadMore()}
                    disabled={loadingMore}
                    className={cn("rounded-full")}
                    data-testid="activity-load-more"
                  >
                    {loadingMore ? "Loading…" : "Load more"}
                  </Button>
                ) : null}
              </>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
