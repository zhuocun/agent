"use client";

import * as React from "react";
import { ChevronDown, Info, Key } from "lucide-react";
import { Popover } from "@base-ui/react/popover";

import type { ModelAttribution, ModelTierId } from "@/lib/types";
import { cn } from "@/lib/utils";
import { MODEL_TIERS_BY_ID } from "@/lib/model-tiers";
import { CostBreakdownDetails } from "@/components/chat/cost-breakdown";

export interface AttributionRowProps {
  attribution: ModelAttribution;
}

function formatCostSummary(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.0001) return "<$0.0001";
  const decimals = n < 0.01 ? 4 : n < 1 ? 3 : 2;
  return `$${n.toFixed(decimals)}`;
}

// `"auto"` is a request-time alias — the server must resolve it to a concrete
// tier before attribution's SERVED side lands here. Narrowing the served type
// makes that boundary explicit; if `"auto"` ever leaks through as served we
// want a loud failure, not a silent title-cased "Auto" chip. The REQUESTED
// side legitimately carries `"auto"` (the user picked Auto and the server
// resolved it), so its label lookup accepts the full union.
type ServedTierId = Exclude<ModelTierId, "auto">;

function servedTierLabelFor(id: ServedTierId): string {
  return MODEL_TIERS_BY_ID[id].label;
}

function requestedTierLabelFor(id: ModelTierId): string {
  return MODEL_TIERS_BY_ID[id].label;
}

function assertServedTier(id: ModelTierId): ServedTierId {
  if (id === "auto") {
    throw new Error(
      "attribution.servedTierId must be a concrete tier; 'auto' must be resolved upstream",
    );
  }
  return id;
}

// Bare interpunct used between byline segments. Local to the trigger so we
// don't ship a one-character component, but extracted so the markup reads as
// typography rather than a chain of repeated spans.
const Dot = (
  <span aria-hidden className="text-muted-foreground/60">
    ·
  </span>
);

export function AttributionRow({
  attribution,
}: AttributionRowProps): React.JSX.Element {
  const isEstimate = attribution.costConfidence === "estimate";
  const { substitution, isByok, servedModelLabel } = attribution;
  const servedTierId = assertServedTier(attribution.servedTierId);
  const providerLabel = attribution.providerLabel?.trim() || undefined;

  // The "<$0.0001" floor already reads as an upper bound, so don't stack a
  // "~" estimate marker on top of it ("~<$0.0001" parses as two operators).
  const costSummary = formatCostSummary(attribution.costUsd);
  const costText = `${isEstimate && !costSummary.startsWith("<") ? "~" : ""}${costSummary}`;
  const tierLabel = servedTierLabelFor(servedTierId);
  // When the served model label degenerates to the served tier's own label
  // (a data gap in the auto→fast path leaves served_model_label === tierLabel),
  // rendering both stutters ("Fast · Fast"). Drop the redundant tier segment;
  // the genuine-fallback case keeps a distinct model name and shows both.
  // Mirrors the model-mode-picker's showEffort dedupe.
  const showTier = tierLabel !== servedModelLabel;
  const showProvider =
    providerLabel !== undefined &&
    providerLabel !== servedModelLabel &&
    providerLabel !== tierLabel;
  const byokLabel = providerLabel
    ? `Your ${providerLabel} key`
    : "Your API key";

  // Brief: byline reads as typography, not a stack of chips. Substitution
  // collapses into a leading muted clause ("substituted from Pro: …"), and the
  // BYOK indicator is a muted inline glyph+label too — so there is zero filled
  // chrome at rest. Per Opp 4, filled pills next to a bare line were the
  // regression to avoid.
  const substitutionPrefix = substitution
    ? `substituted from ${requestedTierLabelFor(attribution.requestedTierId)}: `
    : null;

  const triggerLabel = [
    `served by ${servedModelLabel}`,
    providerLabel ? `provider ${providerLabel}` : null,
    `${tierLabel} tier`,
    costText,
    isByok ? `billed to ${byokLabel.toLowerCase()}` : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-sans text-xs text-muted-foreground">
      <Popover.Root>
        <Popover.Trigger
          aria-label={triggerLabel}
          className={cn(
            "group inline-flex items-center gap-1 rounded-sm bg-transparent p-0",
            "text-muted-foreground outline-none transition-colors hover:text-foreground",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          )}
        >
          {substitutionPrefix ? (
            <span className="inline-flex items-center gap-1 text-muted-foreground/80">
              <Info aria-hidden className="size-3" />
              <span>{substitutionPrefix}</span>
            </span>
          ) : null}
          <span className="underline-offset-4 group-hover:underline">
            {servedModelLabel}
          </span>
          <ChevronDown
            aria-hidden
            className="size-3.5 opacity-70 transition-transform data-[popup-open]:rotate-180"
          />
          {showProvider ? (
            <>
              {Dot}
              <span>{providerLabel}</span>
            </>
          ) : null}
          {showTier ? (
            <>
              {Dot}
              <span>{tierLabel}</span>
            </>
          ) : null}
          {Dot}
          <span className="font-mono tabular-nums">{costText}</span>
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

      {isByok ? (
        // Rendered INLINE (Key glyph + muted text, no filled background) so the
        // byline carries zero filled chrome at rest — matching the substitution
        // clause's treatment. A lone filled pill next to a bare typographic line
        // was the regression to avoid (Opp 4).
        <span className="inline-flex items-center gap-1 text-muted-foreground/80">
          <Key aria-hidden className="size-3" />
          <span>{byokLabel}</span>
        </span>
      ) : null}
    </div>
  );
}
