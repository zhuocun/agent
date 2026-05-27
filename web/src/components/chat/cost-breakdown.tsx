"use client";

import * as React from "react";
import { Check, Info, Layers, TrendingUp } from "lucide-react";

import type { CostBreakdown, ModelAttribution } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";

// The detailed token/cost panel revealed when the user expands the attribution row.
// Implements the PRD 07 §4.1 `cost_breakdown` contract: structured (not scalar)
// pricing, all three long-context models, and the reasoning-token cache exemption
// (PRD 07 §7.7). Numerals are monospace for scannable alignment (PRD 06 §3.2).
export interface CostBreakdownDetailsProps {
  attribution: ModelAttribution;
}

// Token counts read best as grouped integers; prices and totals carry more precision.
const intFmt = new Intl.NumberFormat("en-US");

function formatTokens(n: number): string {
  return intFmt.format(n);
}

// List prices are quoted per million tokens; keep them human-readable.
function formatPricePerM(n: number): string {
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })}/M`;
}

// Money: show enough significant digits that sub-cent turns aren't all "$0.00",
// without dumping noise on larger amounts.
function formatUsd(n: number): string {
  if (n === 0) return "$0.00";
  const decimals = n < 0.01 ? 6 : n < 1 ? 4 : 2;
  return `$${n.toFixed(decimals)}`;
}

/** A single key/value line. The value is monospace + right-aligned for column scanning. */
function Row({
  label,
  value,
  hint,
  emphasis,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-0.5">
      <dt
        className={cn(
          "text-muted-foreground",
          emphasis && "font-medium text-foreground",
        )}
      >
        {label}
        {hint ? (
          <span className="ml-1 text-[0.95em] text-muted-foreground/80">
            {hint}
          </span>
        ) : null}
      </dt>
      <dd
        className={cn(
          "font-mono tabular-nums whitespace-nowrap text-foreground/90",
          emphasis && "font-medium text-foreground",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

/**
 * Long-context pricing summary. The three 2026 models (PRD 07 §4.1) are mutually
 * exclusive and each gets a distinct, non-alarming treatment:
 *  - flat:true            -> positive "no surcharge" selling point (success tone)
 *  - sessionMultiplier    -> whole-session reprice with separate in/out factors
 *  - appliedTier          -> stepped band; only tokens above the threshold reprice
 */
function LongContextSummary({ breakdown }: { breakdown: CostBreakdown }) {
  const lc = breakdown.longContext;

  if (lc.flat) {
    return (
      <div
        className="flex items-start gap-2 rounded-md bg-success/10 px-2.5 py-2 text-success"
        // Tone is reinforced by the icon + text, never color alone (PRD 01 §5.7).
      >
        <Check aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        <div className="space-y-0.5">
          <p className="font-medium">No long-context surcharge</p>
          <p className="text-[0.95em] text-success/90">
            This model prices long context at its standard rate.
          </p>
        </div>
      </div>
    );
  }

  if (lc.sessionMultiplier) {
    const { input, output } = lc.sessionMultiplier;
    return (
      <div className="flex items-start gap-2 rounded-md bg-muted px-2.5 py-2 text-muted-foreground">
        <TrendingUp aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        <div className="space-y-0.5">
          <p className="font-medium text-foreground">
            Long-context session reprice
          </p>
          <p className="text-[0.95em]">
            <span className="font-mono tabular-nums">×{input}</span> in
            {" · "}
            <span className="font-mono tabular-nums">×{output}</span> out
            {" — the whole request reprices once the threshold is crossed."}
          </p>
        </div>
      </div>
    );
  }

  if (lc.appliedTier) {
    const tier = lc.appliedTier;
    return (
      <div className="space-y-1.5 rounded-md bg-muted px-2.5 py-2 text-muted-foreground">
        <div className="flex items-start gap-2">
          <Layers aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          <div className="space-y-0.5">
            <p className="font-medium text-foreground">
              Long-context band: {tier.label}
            </p>
            <p className="text-[0.95em]">
              Only tokens above{" "}
              <span className="font-mono tabular-nums">
                {formatTokens(tier.thresholdTokens)}
              </span>{" "}
              reprice at this band; the rest stay at list price.
            </p>
          </div>
        </div>
        <dl className="space-y-0.5 pl-5.5">
          <Row label="Band input" value={formatPricePerM(tier.priceInPerM)} />
          <Row label="Band output" value={formatPricePerM(tier.priceOutPerM)} />
        </dl>
      </div>
    );
  }

  // Not flat, but no specific repricing applied to this turn (e.g. below threshold).
  return null;
}

export function CostBreakdownDetails({
  attribution,
}: CostBreakdownDetailsProps): React.JSX.Element {
  const b = attribution.breakdown;
  const isEstimate = attribution.costConfidence === "estimate";
  const hasReasoning = b.reasoningTokens > 0;
  const hasSurcharge = b.sessionSurchargeUsd > 0;

  return (
    <div className="space-y-2.5 rounded-md border border-border bg-card/50 p-3 text-xs">
      {/* Tokens */}
      <dl>
        <Row label="Input tokens" value={formatTokens(b.inputTokens)} />
        <Row label="Output tokens" value={formatTokens(b.outputTokens)} />
        {hasReasoning ? (
          <Row
            label="Reasoning tokens"
            hint="billed at output rate"
            value={formatTokens(b.reasoningTokens)}
          />
        ) : null}
        {b.cachedInputTokens > 0 ? (
          <Row
            label="Cached input"
            hint="discounted"
            value={formatTokens(b.cachedInputTokens)}
          />
        ) : null}
      </dl>

      <Separator />

      {/* List prices ($/M) */}
      <dl>
        <Row label="List price, input" value={formatPricePerM(b.listPriceInPerM)} />
        <Row
          label="List price, output"
          value={formatPricePerM(b.listPriceOutPerM)}
        />
      </dl>

      {/* Reasoning-token billing note — PRD 07 §7.7: never cache-discounted. */}
      {hasReasoning ? (
        <p className="flex items-start gap-1.5 text-muted-foreground">
          <Info aria-hidden className="mt-0.5 size-3 shrink-0" />
          <span>
            Reasoning tokens are billed at the output rate every turn and are
            never cache-discounted.
          </span>
        </p>
      ) : null}

      {/* Long-context treatment (the differentiated transparency moment). */}
      <LongContextSummary breakdown={b} />

      <Separator />

      {/* Totals */}
      <dl>
        <Row label="Subtotal" value={formatUsd(b.subtotalUsd)} />
        {hasSurcharge ? (
          <Row
            label="Session surcharge"
            hint="this turn"
            value={formatUsd(b.sessionSurchargeUsd)}
          />
        ) : null}
        <Row
          label={isEstimate ? "Estimated total" : "Total"}
          value={formatUsd(attribution.costUsd)}
          emphasis
        />
      </dl>

      {isEstimate ? (
        <p className="flex items-start gap-1.5 text-warning">
          <Info aria-hidden className="mt-0.5 size-3 shrink-0" />
          <span>
            Estimated — some pricing data was unavailable, so this total may
            differ from the final charge.
          </span>
        </p>
      ) : null}
    </div>
  );
}
