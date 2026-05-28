"use client";

import * as React from "react";
import { ArrowDownRight, ChevronDown, KeyRound } from "lucide-react";

import type { ModelAttribution } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { CostBreakdownDetails } from "@/components/chat/cost-breakdown";

export interface AttributionRowProps {
  attribution: ModelAttribution;
}

function formatCostSummary(n: number): string {
  if (n === 0) return "$0.00";
  const decimals = n < 0.01 ? 4 : n < 1 ? 3 : 2;
  return `$${n.toFixed(decimals)}`;
}

export function AttributionRow({
  attribution,
}: AttributionRowProps): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  const isEstimate = attribution.costConfidence === "estimate";
  const { substitution, isByok } = attribution;

  const costLabel = `${isByok ? "Cost billed to your key" : "Cost"}: ${
    isEstimate ? "estimated " : ""
  }${formatCostSummary(attribution.costUsd)}`;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span
          className="inline-flex h-5 items-center rounded-md bg-trust-badge px-2 font-medium text-trust-badge-foreground shadow-float"
          title={`Answered by ${attribution.servedModelLabel}`}
        >
          {attribution.servedModelLabel}
        </span>

        {isByok ? (
          <span className="inline-flex h-5 items-center gap-1 rounded-md bg-byok-indicator px-2 font-medium text-byok-indicator-foreground shadow-float">
            <KeyRound aria-hidden className="size-3" />
            Your API key
          </span>
        ) : null}

        <span aria-hidden className="text-muted-foreground/60">
          ·
        </span>

        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <span className="font-mono tabular-nums" aria-label={costLabel}>
            {formatCostSummary(attribution.costUsd)}
          </span>
          {isEstimate ? (
            <span
              className="inline-flex h-4 items-center rounded-md bg-warning/15 px-1 text-xs font-medium text-warning"
              title="Estimated cost — final charge may differ"
            >
              est.
            </span>
          ) : null}
          {isByok ? (
            <span className="text-muted-foreground/80">billed to your key</span>
          ) : null}
        </span>

        <CollapsibleTrigger
          aria-label={open ? "Hide cost details" : "Show cost details"}
          className={cn(
            "ml-auto inline-flex min-h-10 items-center gap-1 rounded-md px-2 py-1",
            "text-muted-foreground transition-colors hover:text-foreground",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          )}
        >
          <span>Details</span>
          <ChevronDown
            aria-hidden
            className={cn(
              "size-3.5 transition-transform",
              open && "rotate-180",
            )}
          />
        </CollapsibleTrigger>
      </div>

      {substitution ? (
        <div
          role="note"
          className={cn(
            "mt-1.5 flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs",
            "border-substitution-callout-border bg-substitution-callout text-substitution-callout-foreground",
          )}
        >
          <ArrowDownRight aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          <p>{substitution.reasonText}</p>
        </div>
      ) : null}

      <CollapsibleContent className="mt-2">
        <CostBreakdownDetails attribution={attribution} />
      </CollapsibleContent>
    </Collapsible>
  );
}
