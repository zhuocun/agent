"use client";

import * as React from "react";
import { AlertTriangle, Key } from "lucide-react";
import { Popover } from "@base-ui/react/popover";

import type { ModelAttribution } from "@/lib/types";
import { cn } from "@/lib/utils";
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
  const isEstimate = attribution.costConfidence === "estimate";
  const { substitution, isByok, servedModelLabel } = attribution;

  const costText = `${isEstimate ? "~" : ""}${formatCostSummary(attribution.costUsd)}`;

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      <Popover.Root>
        <Popover.Trigger
          aria-label="Cost details"
          className={cn(
            "inline-flex h-6 items-center gap-1.5 rounded-full bg-muted/60 px-2.5",
            "text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          )}
        >
          <span className="font-semibold">{servedModelLabel}</span>
          <span aria-hidden className="text-muted-foreground/60">
            ·
          </span>
          <span className="font-mono tabular-nums">{costText}</span>
          {isByok ? <Key aria-hidden className="size-3" /> : null}
        </Popover.Trigger>

        <Popover.Portal>
          <Popover.Positioner sideOffset={6} align="start" className="z-50 outline-none">
            <Popover.Popup
              className={cn(
                "glass-strong w-[min(22rem,calc(100vw-2rem))] origin-(--transform-origin) rounded-2xl text-popover-foreground outline-none",
                "duration-100 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95",
                "data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
              )}
            >
              <CostBreakdownDetails attribution={attribution} />
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>

      {substitution ? (
        <p
          role="note"
          className="inline-flex items-center gap-1 text-muted-foreground"
        >
          <AlertTriangle aria-hidden className="size-3" />
          <span>{substitution.reasonText}</span>
        </p>
      ) : null}
    </div>
  );
}
