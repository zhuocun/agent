import { formatUsdMeter } from "@/lib/money";
import type { UsageBudget } from "@/lib/types";

const WARN_THRESHOLD = 0.8;
const CRIT_THRESHOLD = 0.95;
// Spend soft-cap thresholds (PRD 05 §4.5 D27). Layered OVER the shipped hard
// gate (which still blocks at the effective cap): warn as spend approaches the
// cap, escalate to critical once it's reached.
const SPEND_WARN_THRESHOLD = 0.8;
const SPEND_CRIT_THRESHOLD = 1.0;

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

export interface UsagePresentation {
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

/**
 * Remaining platform allowance. `platformRemainingUsd` is the enforced figure
 * (quota remainder plus credits, minus reservations). Quota minus spend is only
 * the fallback when that field is absent.
 */
function spendRemainingUsd(
  usage: UsageBudget,
  quota: number,
  spend: number,
): number {
  const reported = usage.platformRemainingUsd;
  if (typeof reported === "number" && Number.isFinite(reported)) {
    return Math.max(0, reported);
  }
  return Math.max(0, quota - spend);
}

/**
 * 0–100 fill of the allowance already consumed. Never the raw dollar remainder.
 * With a finite credit balance, the pool is max(spend, quota) plus those
 * credits, so spend past the quota stays in the numerator. Without that field,
 * reservations shrink the quota fill and a larger remainder widens the pool.
 */
function allowanceUsedPct(
  quota: number,
  spend: number,
  remainingUsd: number,
  creditBalanceUsd: number | null | undefined,
): number {
  if (typeof creditBalanceUsd === "number" && Number.isFinite(creditBalanceUsd)) {
    const credits = Math.max(0, creditBalanceUsd);
    const pool = Math.max(spend, quota) + credits;
    if (pool <= 0) return 0;
    const consumed = Math.min(
      pool,
      Math.max(0, spend + Math.max(0, quota - spend) + credits - remainingUsd),
    );
    return Math.min(100, Math.max(0, Math.round((consumed / pool) * 100)));
  }
  const quotaRemainder = Math.max(0, quota - spend);
  if (remainingUsd < quotaRemainder) {
    if (quota <= 0) return 0;
    return Math.min(
      100,
      Math.max(0, Math.round(((quota - remainingUsd) / quota) * 100)),
    );
  }
  const pool = spend + remainingUsd;
  if (pool <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((spend / pool) * 100)));
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
  const remainingUsd = hasSpendCap ? spendRemainingUsd(usage, quota, spend) : 0;
  const spendPct = hasSpendCap
    ? allowanceUsedPct(quota, spend, remainingUsd, usage.creditBalanceUsd)
    : 0;
  const spendTone: UsageTone = !hasSpendCap
    ? "normal"
    : spendRatio >= SPEND_CRIT_THRESHOLD
      ? remainingUsd <= 0
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
    ? remainingUsd <= 0
      ? "Budget reached"
      : `${formatUsdMeter(remainingUsd)} left`
    : limit > 0
      ? remaining === 0
        ? "No usage left"
        : `${remaining.toLocaleString()} left`
      : "Usage metering active";
  const detailText = hasSpendCap
    ? `${formatUsdMeter(spend)} of ${formatUsdMeter(quota)} spent ${usage.periodLabel}, ${formatUsdMeter(remainingUsd)} remaining`
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
    ? `Spend ${formatUsdMeter(spend)} of ${formatUsdMeter(quota)} ${usage.periodLabel}, ${formatUsdMeter(remainingUsd)} remaining${approachingSuffix}`
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
    spendRemainingUsd: remainingUsd,
    spendPct,
  };
}
