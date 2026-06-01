"use client";

import { Key } from "lucide-react";

import { cn } from "@/lib/utils";
import type { UsageBudget } from "@/lib/types";

const WARN_THRESHOLD = 0.8;
const CRIT_THRESHOLD = 0.95;

export interface UsageMeterProps {
  usage: UsageBudget;
}

type UsageTone = "normal" | "warning" | "critical" | "exhausted";

interface UsagePresentation {
  limit: number;
  used: number;
  remaining: number;
  pct: number;
  tone: UsageTone;
  remainingText: string;
  accessibleLabel: string;
  detailText: string;
}

export function getUsagePresentation(usage: UsageBudget): UsagePresentation {
  const limit = Math.max(0, usage.limit);
  const used = Math.max(0, usage.used);
  const remaining = limit > 0 ? Math.max(0, limit - used) : 0;
  const ratio = limit > 0 ? Math.min(used / limit, 1) : 0;
  const pct = Math.round(ratio * 100);
  const tone: UsageTone =
    limit > 0 && remaining === 0
      ? "exhausted"
      : ratio >= CRIT_THRESHOLD
        ? "critical"
        : ratio >= WARN_THRESHOLD
          ? "warning"
          : "normal";

  const valueText = `${used.toLocaleString()} / ${limit.toLocaleString()}`;
  const remainingText =
    limit > 0
      ? remaining === 0
        ? "No usage left"
        : `${remaining.toLocaleString()} left`
      : "Usage metering active";
  const detailText =
    limit > 0
      ? `${valueText} used, ${remaining.toLocaleString()} remaining ${usage.periodLabel}`
      : `Usage tracked ${usage.periodLabel}`;
  const accessibleLabel =
    limit > 0
      ? `Usage ${valueText} used ${usage.periodLabel}, ${remaining.toLocaleString()} remaining${
          tone === "exhausted"
            ? " — limit reached"
            : tone === "critical" || tone === "warning"
              ? " — approaching limit"
              : ""
        }`
      : `Usage tracked ${usage.periodLabel}`;

  return {
    limit,
    used,
    remaining,
    pct,
    tone,
    remainingText,
    accessibleLabel,
    detailText,
  };
}

export function UsageMeter({ usage }: UsageMeterProps) {
  if (usage.isByok) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5",
          "bg-byok-indicator text-byok-indicator-foreground",
          "text-xs font-medium",
        )}
        title="Your own provider key is active. Platform credits are not used for model token charges."
      >
        <Key aria-hidden="true" className="size-3 shrink-0" />
        Billed to your key
      </span>
    );
  }

  const presentation = getUsagePresentation(usage);
  const isWarning = presentation.tone === "warning";
  const isCritical =
    presentation.tone === "critical" || presentation.tone === "exhausted";

  return (
    <div
      className={cn(
        "inline-flex min-w-0 items-center gap-2 text-xs",
        isCritical
          ? "text-destructive"
          : isWarning
            ? "text-warning"
            : "text-muted-foreground",
      )}
      title={presentation.accessibleLabel}
    >
      {presentation.limit > 0 ? (
        <div
          role="progressbar"
          aria-label={presentation.accessibleLabel}
          aria-valuenow={presentation.used}
          aria-valuemin={0}
          aria-valuemax={presentation.limit}
          aria-valuetext={presentation.detailText}
          className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-foreground/8"
        >
          <div
            className={cn(
              "relative h-full rounded-full transition-[width] duration-300 ease-out",
              // Nominal fill uses the brand tint — iOS capacity bars colour
              // normal fill with the tint, not gray (gray reads inert/
              // disabled). `/80` keeps it calm rather than fully saturated.
              // The warning/critical threshold branches are unchanged.
              isCritical
                ? "bg-destructive"
                : isWarning
                  ? "bg-warning"
                  : "bg-brand/80",
            )}
            style={{ width: `${presentation.pct}%` }}
          />
        </div>
      ) : null}

      <span className="min-w-0 truncate">
        <span className="font-mono tabular-nums">
          {presentation.remainingText}
        </span>{" "}
        <span
          className={cn(
            !isWarning && !isCritical && "text-muted-foreground",
          )}
        >
          {usage.periodLabel}
        </span>
      </span>
    </div>
  );
}
