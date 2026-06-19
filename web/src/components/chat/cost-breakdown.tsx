"use client";

import * as React from "react";
import { Check, Info, Layers, TrendingUp } from "lucide-react";

import type { CostBreakdown, ModelAttribution } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  formatPricePerM,
  formatUsdPrecise,
} from "@/lib/money";
import { Separator } from "@/components/ui/separator";

export interface CostBreakdownDetailsProps {
  attribution: ModelAttribution;
}

const intFmt = new Intl.NumberFormat("en-US");

function formatTokens(n: number): string {
  return intFmt.format(n);
}

// Conservative thresholds for the long-context "no cache hit" / "high reasoning"
// callouts. Tuned high so the clause only fires when the signal is genuinely
// notable — a quiet "why this cost more" nudge, not noise on every turn.
const LONG_CONTEXT_TOKENS = 200_000;
const NO_CACHE_INPUT_TOKENS = 50_000;

// Pure cost-anomaly classifier (Feature 5). Returns a short human reason when
// the breakdown shows a notable cost driver, else null. Derived entirely from
// existing breakdown fields — no wire change. Order matters: the first matching
// (most cost-relevant) reason wins so the clause stays one line.
export function costAnomaly(breakdown: CostBreakdown): string | null {
  // Reasoning dominated output: extended-thinking turns where the (output-rate,
  // un-cached) reasoning tokens exceed the visible answer tokens.
  if (breakdown.reasoningTokens > breakdown.outputTokens) {
    return "High reasoning cost";
  }
  // Very large input window — long context is the dominant input driver.
  if (breakdown.inputTokens + breakdown.cachedInputTokens > LONG_CONTEXT_TOKENS) {
    return "Long context";
  }
  // A big prompt that got zero cache discount (every input token billed full).
  if (breakdown.cachedInputTokens === 0 && breakdown.inputTokens > NO_CACHE_INPUT_TOKENS) {
    return "No cache hit";
  }
  return null;
}

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

function LongContextSummary({ breakdown }: { breakdown: CostBreakdown }) {
  const lc = breakdown.longContext;

  if (lc.flat) {
    return (
      <div className="flex items-start gap-2 rounded-xl bg-success/10 px-2.5 py-2 text-success">
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
      <div className="flex items-start gap-2 rounded-xl bg-muted px-2.5 py-2 text-muted-foreground">
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
      <div className="space-y-1.5 rounded-xl bg-muted px-2.5 py-2 text-muted-foreground">
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

  return null;
}

export function CostBreakdownDetails({
  attribution,
}: CostBreakdownDetailsProps): React.JSX.Element {
  const b = attribution.breakdown;
  const isEstimate = attribution.costConfidence === "estimate";
  const hasReasoning = b.reasoningTokens > 0;
  const hasSurcharge = b.sessionSurchargeUsd > 0;
  const anomaly = costAnomaly(b);

  return (
    <div className="bg-muted/50 space-y-2.5 rounded-2xl p-4 text-xs">
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

      <dl>
        <Row label="List price, input" value={formatPricePerM(b.listPriceInPerM)} />
        <Row
          label="List price, output"
          value={formatPricePerM(b.listPriceOutPerM)}
        />
      </dl>

      {hasReasoning ? (
        <p className="flex items-start gap-1.5 text-muted-foreground">
          <Info aria-hidden className="mt-0.5 size-3 shrink-0" />
          <span>
            Reasoning tokens bill at the output rate and aren&apos;t
            cache-discounted.
          </span>
        </p>
      ) : null}

      <LongContextSummary breakdown={b} />

      <Separator />

      <dl>
        <Row label="Subtotal" value={formatUsdPrecise(b.subtotalUsd)} />
        {hasSurcharge ? (
          <Row
            label="Session surcharge"
            hint="this turn"
            value={formatUsdPrecise(b.sessionSurchargeUsd)}
          />
        ) : null}
        <Row
          label={isEstimate ? "Estimated total" : "Total"}
          value={formatUsdPrecise(attribution.costUsd)}
          emphasis
        />
      </dl>

      {anomaly ? (
        <p
          className="flex items-start gap-1.5 text-warning"
          data-testid="cost-anomaly"
        >
          <Info aria-hidden className="mt-0.5 size-3 shrink-0" />
          <span>{anomaly}</span>
        </p>
      ) : null}

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
