"use client";

import { Key } from "lucide-react";

import { cn } from "@/lib/utils";
import type { UsageBudget } from "@/lib/types";

// Usage / budget meter (PRD 06 §5.5).
// Compact transparency surface for the composer footer / thread header.
// - Platform-key users: a thin progress bar + "{used} / {limit} {periodLabel}".
//   At >= 80% of the cap it switches to a warning treatment; the numerals
//   carry the signal too, so we never rely on color alone (PRD 06 §5.5 / a11y).
// - BYOK sessions: no platform token markup — just "Billed to your key"
//   (PRD 06 §5.5 / §5.8).
const WARN_THRESHOLD = 0.8;

export interface UsageMeterProps {
  usage: UsageBudget;
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
      >
        <Key aria-hidden="true" className="size-3 shrink-0" />
        Billed to your key
      </span>
    );
  }

  // Clamp so a malformed/over-cap value can't draw past 100% or divide by zero.
  const limit = Math.max(0, usage.limit);
  const used = Math.max(0, usage.used);
  const ratio = limit > 0 ? Math.min(used / limit, 1) : 0;
  const pct = Math.round(ratio * 100);
  const isWarning = ratio >= WARN_THRESHOLD;

  const valueText = `${used.toLocaleString()} / ${limit.toLocaleString()}`;
  const accessibleLabel = `Usage ${valueText} ${usage.periodLabel}${
    isWarning ? " — approaching limit" : ""
  }`;

  return (
    <div
      className={cn(
        "inline-flex min-w-0 items-center gap-2 text-xs",
        isWarning ? "text-warning" : "text-muted-foreground",
      )}
      title={accessibleLabel}
    >
      {limit > 0 ? (
        <div
          role="progressbar"
          aria-label={accessibleLabel}
          aria-valuenow={used}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-valuetext={`${valueText} ${usage.periodLabel}`}
          className={cn(
            "h-1.5 w-16 shrink-0 overflow-hidden rounded-full",
            isWarning ? "bg-warning/20" : "bg-muted",
          )}
        >
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-300 ease-out",
              isWarning ? "bg-warning" : "bg-brand",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : null}

      <span className="min-w-0 truncate">
        <span className="font-mono tabular-nums">{valueText}</span>{" "}
        <span className={cn(!isWarning && "text-muted-foreground")}>
          {usage.periodLabel}
        </span>
      </span>
    </div>
  );
}
