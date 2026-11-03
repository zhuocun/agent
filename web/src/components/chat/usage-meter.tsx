"use client";

import { Key } from "lucide-react";

import { getUsagePresentation } from "@/components/chat/usage-presentation";
import { Progress } from "@/components/ui/progress";
import { useT } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
import type { UsageBudget } from "@/lib/types";

export { getUsagePresentation };

export interface UsageMeterProps {
  usage: UsageBudget;
}

export function UsageMeter({ usage }: UsageMeterProps) {
  const t = useT();
  if (usage.isByok) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5",
          "bg-byok-indicator text-byok-indicator-foreground",
          "ui-caption font-medium",
        )}
        title="Your own provider key is active. Platform credits are not used for model token charges."
      >
        <Key aria-hidden="true" className="size-3 shrink-0" />
        {t("usage.billedToKey")}
      </span>
    );
  }

  const presentation = getUsagePresentation(usage);
  const isWarning = presentation.tone === "warning";
  const isCritical =
    presentation.tone === "critical" || presentation.tone === "exhausted";
  // When a spend cap binds, the bar is the 0–100 allowance fill; otherwise it
  // keeps the integer used/limit fill.
  const showBar = presentation.hasSpendCap || presentation.limit > 0;
  const barPct = presentation.hasSpendCap
    ? presentation.spendPct
    : presentation.pct;

  return (
    <div
      className={cn(
        "inline-flex min-w-0 items-center gap-2 ui-caption",
        isCritical
          ? "text-destructive-text"
          : isWarning
            ? "text-warning-text"
            : "text-muted-foreground",
      )}
      title={presentation.accessibleLabel}
    >
      {showBar ? (
        <Progress
          value={barPct}
          min={0}
          max={100}
          aria-label={presentation.accessibleLabel}
          aria-valuetext={presentation.detailText}
          className={cn(
            "h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-muted",
            "shadow-[inset_0_0_0_1px_var(--border)] forced-colors:border forced-colors:border-[CanvasText]",
            "[&_[data-slot=progress-track]]:h-full [&_[data-slot=progress-track]]:bg-transparent",
            "[&_[data-slot=progress-indicator]]:relative [&_[data-slot=progress-indicator]]:rounded-full",
            "[&_[data-slot=progress-indicator]]:transition-[width] [&_[data-slot=progress-indicator]]:duration-300 [&_[data-slot=progress-indicator]]:ease-out",
            "[&_[data-slot=progress-indicator]]:motion-reduce:transition-none [&_[data-slot=progress-indicator]]:forced-colors:bg-[Highlight]",
            // Nominal fill uses the brand tint — iOS capacity bars colour
            // normal fill with the tint, not gray (gray reads inert/
            // disabled). `/80` keeps it calm rather than fully saturated.
            // The warning/critical threshold branches are unchanged.
            isCritical
              ? "[&_[data-slot=progress-indicator]]:bg-destructive"
              : isWarning
                ? "[&_[data-slot=progress-indicator]]:bg-warning"
                : "[&_[data-slot=progress-indicator]]:bg-brand/80",
          )}
        />
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
