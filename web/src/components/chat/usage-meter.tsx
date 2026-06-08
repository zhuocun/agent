"use client";

import { Key } from "lucide-react";

import { useT } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
import type { UsageBudget } from "@/lib/types";

const WARN_THRESHOLD = 0.8;
const CRIT_THRESHOLD = 0.95;
// Spend soft-cap thresholds (PRD 05 §4.5 D27). Layered OVER the shipped hard
// gate (which still blocks at the effective cap): warn as spend approaches the
// cap, escalate to critical once it's reached.
const SPEND_WARN_THRESHOLD = 0.8;
const SPEND_CRIT_THRESHOLD = 1.0;

export interface UsageMeterProps {
  usage: UsageBudget;
}

type UsageTone = "normal" | "warning" | "critical" | "exhausted";

const TONE_SEVERITY: Record<UsageTone, number> = {
  normal: 0,
  warning: 1,
  critical: 2,
  exhausted: 3,
};

function maxTone(a: UsageTone, b: UsageTone): UsageTone {
  return TONE_SEVERITY[a] >= TONE_SEVERITY[b] ? a : b;
}

function formatUsd(amount: number): string {
  return `$${amount.toFixed(amount < 1 ? 4 : 2)}`;
}

interface UsagePresentation {
  limit: number;
  used: number;
  remaining: number;
  pct: number;
  tone: UsageTone;
  remainingText: string;
  accessibleLabel: string;
  detailText: string;
  // Spend soft-cap fields. `hasSpendCap` is true for platform-key users with a
  // positive effective cap; the remaining-USD text is then legible regardless
  // of the integer meter.
  hasSpendCap: boolean;
  spendRemainingUsd: number;
  spendPct: number;
}

export function getUsagePresentation(usage: UsageBudget): UsagePresentation {
  const limit = Math.max(0, usage.limit);
  const used = Math.max(0, usage.used);
  const remaining = limit > 0 ? Math.max(0, limit - used) : 0;
  const ratio = limit > 0 ? Math.min(used / limit, 1) : 0;
  const pct = Math.round(ratio * 100);
  const integerTone: UsageTone =
    limit > 0 && remaining === 0
      ? "exhausted"
      : ratio >= CRIT_THRESHOLD
        ? "critical"
        : ratio >= WARN_THRESHOLD
          ? "warning"
          : "normal";

  // Cost-based soft cap: the actually-enforced figure is `effectiveQuotaUsd`
  // (the tighter of the operator quota and the user's own cap). Only platform
  // -key users are gated on spend; BYOK pays their own provider.
  const quota = usage.effectiveQuotaUsd ?? 0;
  const spend = Math.max(0, usage.monthlySpendUsd ?? 0);
  const hasSpendCap = !usage.isByok && quota > 0;
  const spendRatio = hasSpendCap ? spend / quota : 0;
  const spendRemainingUsd = hasSpendCap ? Math.max(0, quota - spend) : 0;
  const spendPct = hasSpendCap ? Math.min(Math.round(spendRatio * 100), 100) : 0;
  const spendTone: UsageTone = !hasSpendCap
    ? "normal"
    : spendRatio >= SPEND_CRIT_THRESHOLD
      ? spendRemainingUsd <= 0
        ? "exhausted"
        : "critical"
      : spendRatio >= SPEND_WARN_THRESHOLD
        ? "warning"
        : "normal";

  const tone = maxTone(integerTone, spendTone);

  const valueText = `${used.toLocaleString()} / ${limit.toLocaleString()}`;
  // When a spend cap is active it's the binding limit, so the remaining text
  // speaks in USD (legible, actionable). Otherwise fall back to the integer
  // meter's count.
  const remainingText = hasSpendCap
    ? spendRemainingUsd <= 0
      ? "Budget reached"
      : `${formatUsd(spendRemainingUsd)} left`
    : limit > 0
      ? remaining === 0
        ? "No usage left"
        : `${remaining.toLocaleString()} left`
      : "Usage metering active";
  const detailText = hasSpendCap
    ? `${formatUsd(spend)} of ${formatUsd(quota)} spent ${usage.periodLabel}, ${formatUsd(spendRemainingUsd)} remaining`
    : limit > 0
      ? `${valueText} used, ${remaining.toLocaleString()} remaining ${usage.periodLabel}`
      : `Usage tracked ${usage.periodLabel}`;
  const approachingSuffix =
    tone === "exhausted"
      ? " — limit reached"
      : tone === "critical" || tone === "warning"
        ? " — approaching limit"
        : "";
  const accessibleLabel = hasSpendCap
    ? `Spend ${formatUsd(spend)} of ${formatUsd(quota)} ${usage.periodLabel}, ${formatUsd(spendRemainingUsd)} remaining${approachingSuffix}`
    : limit > 0
      ? `Usage ${valueText} used ${usage.periodLabel}, ${remaining.toLocaleString()} remaining${approachingSuffix}`
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
    hasSpendCap,
    spendRemainingUsd,
    spendPct,
  };
}

export function UsageMeter({ usage }: UsageMeterProps) {
  const t = useT();
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
        {t("usage.billedToKey")}
      </span>
    );
  }

  const presentation = getUsagePresentation(usage);
  const isWarning = presentation.tone === "warning";
  const isCritical =
    presentation.tone === "critical" || presentation.tone === "exhausted";
  // When a spend cap binds, the bar tracks the cost ratio (the enforced limit);
  // otherwise it keeps the integer used/limit fill.
  const showBar = presentation.hasSpendCap || presentation.limit > 0;
  const barPct = presentation.hasSpendCap
    ? presentation.spendPct
    : presentation.pct;

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
      {showBar ? (
        <div
          role="progressbar"
          aria-label={presentation.accessibleLabel}
          aria-valuenow={barPct}
          aria-valuemin={0}
          aria-valuemax={100}
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
            style={{ width: `${barPct}%` }}
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
