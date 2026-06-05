"use client";

import { useEffect, useState, type JSX } from "react";
import { BarChart3, Download } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { fetchSpendAnalytics } from "@/lib/apiClient";
import type { SpendAnalytics } from "@/lib/types";
import { cn } from "@/lib/utils";

// Spend-analytics dashboard (PRD 05 §4.5 D27). Opened from Settings → Account.
// Renders the two HONEST cost bases, a lightweight CSS daily bar chart (no
// charting library), a by-model and top-conversations breakdown, and
// client-side CSV / JSON export. Reads already-captured data; never routes or
// switches models.

const RANGE_OPTIONS: ReadonlyArray<{ days: number; label: string }> = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
];

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(value);
}

// Compact "Jun 5" label for a "YYYY-MM-DD" UTC day key. Parsed as UTC so the
// rendered day matches the bucket the BE assigned (no local-tz drift).
function formatDayLabel(isoDate: string): string {
  const parsed = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return isoDate;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

// Quote a CSV field iff it contains a comma, quote, or newline (RFC 4180).
function csvField(value: string | number): string {
  const text = String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

// Flatten the analytics into one section-tagged CSV so totals, daily, by-model,
// and by-conversation all round-trip in a single machine-parseable file.
function toCsv(data: SpendAnalytics): string {
  const rows: string[] = ["section,label,costUsd,messageCount"];
  rows.push(
    `summary,${csvField("Cumulative meter")},${data.cumulativeMeterUsd},`,
  );
  rows.push(
    `summary,${csvField("Surviving messages")},${data.survivingMessagesUsd},`,
  );
  for (const day of data.daily) {
    rows.push(`daily,${csvField(day.date)},${day.costUsd},${day.messageCount}`);
  }
  for (const model of data.byModel) {
    rows.push(
      `model,${csvField(model.label)},${model.costUsd},${model.messageCount}`,
    );
  }
  for (const convo of data.byConversation) {
    rows.push(
      `conversation,${csvField(convo.title)},${convo.costUsd},${convo.messageCount}`,
    );
  }
  return rows.join("\n");
}

function downloadBlob(filename: string, contents: string, mime: string): void {
  const blob = new Blob([contents], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function SpendDialog(): JSX.Element {
  const [open, setOpen] = useState(false);
  const [days, setDays] = useState(30);
  const [data, setData] = useState<SpendAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch on open and whenever the range changes. State only moves forward from
  // inside the async callback (no synchronous setState in the effect body),
  // mirroring public-conversation-view.tsx — so a range switch keeps the prior
  // data on screen until the new range lands rather than flashing empty.
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const result = await fetchSpendAnalytics(days, controller.signal);
        if (controller.signal.aborted) return;
        setData(result);
        setError(null);
      } catch {
        if (controller.signal.aborted) return;
        setError("Spend data could not be loaded.");
      }
    })();
    return () => controller.abort();
  }, [open, days]);

  // The BE clamps `days` to the value it echoes back, so a mismatch means the
  // freshly-requested range hasn't arrived yet.
  const loading = !error && (data === null || data.rangeDays !== days);
  const maxDaily = data
    ? data.daily.reduce((acc, day) => Math.max(acc, day.costUsd), 0)
    : 0;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            type="button"
            variant="secondary"
            size="sm"
            data-testid="spend-dialog-trigger"
          >
            <BarChart3 aria-hidden className="size-3.5" />
            <span>View spend details</span>
          </Button>
        }
      />
      <DialogContent
        className="sm:max-w-xl"
        data-testid="spend-dialog"
      >
        <DialogHeader>
          <DialogTitle>Spend details</DialogTitle>
          <DialogDescription>
            Longitudinal model spend over the selected window.
          </DialogDescription>
        </DialogHeader>

        <div className="-mr-2 max-h-[60dvh] space-y-4 overflow-y-auto pr-2 sm:max-h-[70dvh]">
          {/* Range selector */}
          <div
            className="grid grid-cols-3 overflow-hidden rounded-full border border-border/70 bg-secondary/40 p-0.5"
            role="group"
            aria-label="Spend range"
          >
            {RANGE_OPTIONS.map((option) => {
              const selected = option.days === days;
              return (
                <button
                  key={option.days}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setDays(option.days)}
                  data-testid={`spend-range-${option.days}`}
                  className={cn(
                    "min-w-0 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                    selected
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                </button>
              );
            })}
          </div>

          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}

          {/* Two honest totals */}
          <div className="grid grid-cols-2 gap-2">
            <div className="glass-clear rounded-2xl px-3.5 py-3">
              <p className="text-xs text-muted-foreground">
                <span>Cumulative meter</span>
                <span className="ml-1 text-2xs opacity-70">(month-to-date)</span>
              </p>
              <p
                className="mt-0.5 font-mono text-base tabular-nums"
                data-testid="spend-total-cumulative"
              >
                {data ? formatUsd(data.cumulativeMeterUsd) : "—"}
              </p>
            </div>
            <div className="glass-clear rounded-2xl px-3.5 py-3">
              <p className="text-xs text-muted-foreground">
                Surviving messages
              </p>
              <p
                className="mt-0.5 font-mono text-base tabular-nums"
                data-testid="spend-total-surviving"
              >
                {data ? formatUsd(data.survivingMessagesUsd) : "—"}
              </p>
            </div>
          </div>
          <p className="text-xs leading-snug text-muted-foreground">
            The <span className="font-medium">cumulative meter</span> counts
            every generation you triggered this calendar month — including
            regenerated or deleted turns.{" "}
            <span className="font-medium">Surviving messages</span> sums only the
            replies still in your threads over the selected range, so it can be
            lower.
          </p>

          {/* Daily bar chart */}
          <section className="space-y-2">
            <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Daily spend
            </h4>
            {data && data.daily.length > 0 ? (
              <div
                className="flex h-28 items-end gap-0.5"
                data-testid="spend-daily-bars"
                aria-hidden
              >
                {data.daily.map((day) => {
                  const heightPct =
                    maxDaily > 0 ? (day.costUsd / maxDaily) * 100 : 0;
                  return (
                    <div
                      key={day.date}
                      className="group flex h-full min-w-0 flex-1 items-end"
                      title={`${formatDayLabel(day.date)}: ${formatUsd(day.costUsd)} (${day.messageCount} msg)`}
                    >
                      <div
                        className="w-full rounded-t bg-brand/70 transition-colors group-hover:bg-brand"
                        style={{ height: `${Math.max(heightPct, day.costUsd > 0 ? 4 : 0)}%` }}
                      />
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                {loading ? "Loading…" : "No spend in this window."}
              </p>
            )}
            {data && data.daily.length > 0 ? (
              <div className="flex justify-between text-[0.65rem] text-muted-foreground">
                <span>{formatDayLabel(data.daily[0]!.date)}</span>
                <span>
                  {formatDayLabel(data.daily[data.daily.length - 1]!.date)}
                </span>
              </div>
            ) : null}
          </section>

          {/* By model */}
          {data && data.byModel.length > 0 ? (
            <section className="space-y-1.5">
              <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                By model
              </h4>
              <ul className="space-y-1" data-testid="spend-by-model">
                {data.byModel.map((model) => (
                  <li
                    key={model.label}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="min-w-0 truncate">
                      {model.label}
                      <span className="ml-1.5 text-xs text-muted-foreground">
                        {model.messageCount} msg
                      </span>
                    </span>
                    <span className="shrink-0 font-mono tabular-nums">
                      {formatUsd(model.costUsd)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {/* Top conversations */}
          {data && data.byConversation.length > 0 ? (
            <section className="space-y-1.5">
              <h4 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                Top conversations
              </h4>
              <ul className="space-y-1" data-testid="spend-by-conversation">
                {data.byConversation.map((convo) => (
                  <li
                    key={convo.conversationId}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="min-w-0 truncate">
                      {convo.title || "Untitled"}
                      <span className="ml-1.5 text-xs text-muted-foreground">
                        {convo.messageCount} msg
                      </span>
                    </span>
                    <span className="shrink-0 font-mono tabular-nums">
                      {formatUsd(convo.costUsd)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {/* Export */}
          <div className="flex flex-wrap gap-2 border-t border-border/50 pt-3">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={!data}
              data-testid="spend-export-csv"
              onClick={() => {
                if (!data) return;
                downloadBlob(
                  `spend-${data.rangeDays}d.csv`,
                  toCsv(data),
                  "text/csv;charset=utf-8",
                );
              }}
            >
              <Download aria-hidden className="size-3.5" />
              <span>Export CSV</span>
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={!data}
              data-testid="spend-export-json"
              onClick={() => {
                if (!data) return;
                downloadBlob(
                  `spend-${data.rangeDays}d.json`,
                  JSON.stringify(data, null, 2),
                  "application/json",
                );
              }}
            >
              <Download aria-hidden className="size-3.5" />
              <span>Export JSON</span>
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
