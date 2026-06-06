"use client";

import * as React from "react";
import { Braces, ChevronDown, Info, Key, TriangleAlert } from "lucide-react";
import { Popover } from "@base-ui/react/popover";

import type { ModelAttribution, ModelTierId } from "@/lib/types";
import { cn } from "@/lib/utils";
import { MODEL_TIERS_BY_ID } from "@/lib/model-tiers";
import {
  CostBreakdownDetails,
  costAnomaly,
} from "@/components/chat/cost-breakdown";

export interface AttributionRowProps {
  attribution: ModelAttribution;
  onOpen?: () => void;
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
  onOpen,
}: AttributionRowProps): React.JSX.Element {
  const isEstimate = attribution.costConfidence === "estimate";
  const { substitution, isByok, servedModelLabel, outputFormat } = attribution;
  // JSON-mode affordance. `outputFormat` is present only when structured output
  // was requested this turn; `outputValid === false` means the model's output
  // failed to parse/validate as JSON. The label carries the valid/invalid state
  // in TEXT (not color alone) so it reads for AT and in monochrome.
  const showJsonChip = outputFormat !== undefined;
  const jsonInvalid = attribution.outputValid === false;
  const servedTierId = assertServedTier(attribution.servedTierId);
  const providerLabel = attribution.providerLabel?.trim() || undefined;

  // The "<$0.0001" floor already reads as an upper bound, so don't stack a
  // "~" estimate marker on top of it ("~<$0.0001" parses as two operators).
  const costSummary = formatCostSummary(attribution.costUsd);
  const costText = `${isEstimate && !costSummary.startsWith("<") ? "~" : ""}${costSummary}`;
  const tierLabel = servedTierLabelFor(servedTierId);
  const byokLabel = providerLabel
    ? `Your ${providerLabel} key`
    : "Your API key";

  // Brief: byline reads as typography, not a stack of chips. Substitution
  // collapses into a leading muted clause ("substituted from Pro: …"). The
  // visible identity stays intentionally compact: one served model label plus
  // cost. Provider/tier details remain in the accessible label and full
  // attribution payload without repeating model-ish names in every message.
  const substitutionPrefix = substitution
    ? `substituted from ${requestedTierLabelFor(attribution.requestedTierId)}: `
    : null;

  // Cost-anomaly "why" clause (Feature 5). Only shown when there's NO
  // substitution — the substitution clause already explains this turn's cost
  // story, and stacking two muted prefixes clutters the byline. Reuses the same
  // Info-glyph treatment as the substitution clause.
  const anomalyReason = substitution ? null : costAnomaly(attribution.breakdown);

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
      <Popover.Root
        onOpenChange={(open) => {
          if (open) onOpen?.();
        }}
      >
        <Popover.Trigger
          aria-label={triggerLabel}
          data-testid="message-attribution"
          className={cn(
            "group inline-flex items-center gap-1 rounded-sm bg-transparent p-0",
            "text-muted-foreground outline-none transition-colors hover:text-foreground",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
        >
          {substitutionPrefix ? (
            <span className="inline-flex items-center gap-1 text-muted-foreground/80">
              <Info aria-hidden className="size-3" />
              <span>{substitutionPrefix}</span>
            </span>
          ) : anomalyReason ? (
            <span
              className="inline-flex items-center gap-1 text-muted-foreground/80"
              data-testid="attribution-anomaly"
            >
              <Info aria-hidden className="size-3" />
              <span>{anomalyReason}: </span>
            </span>
          ) : null}
          <span className="underline-offset-4 group-hover:underline">
            {servedModelLabel}
          </span>
          {/* The chevron is secondary ornament — it advertises that the row
              expands, but the model label + cost (the transparency summary)
              carry the meaning at rest. So it follows the sanctioned
              hover/focus disclosure idiom: hidden on desktop until the message
              is hovered or anything inside it is focused, always-on on touch.
              The whole trigger stays clickable regardless; only the chevron
              stops painting at rest. The popup-open rotate is preserved for
              when the row is expanded. */}
          <ChevronDown
            aria-hidden
            className={cn(
              "size-3.5 opacity-70 transition-[transform,opacity] data-[popup-open]:rotate-180",
              "md:opacity-0 md:group-hover/msg:opacity-70 group-focus-visible:opacity-70 [@media(hover:none)]:opacity-70",
              "data-[popup-open]:opacity-70",
            )}
          />
          {Dot}
          <span className="font-mono tabular-nums">{costText}</span>
        </Popover.Trigger>

        <Popover.Portal>
          <Popover.Positioner sideOffset={6} align="start" className="z-[60] outline-none">
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

      {showJsonChip ? (
        // Rendered INLINE (glyph + muted text, no filled background) to match the
        // BYOK/substitution treatment so the byline keeps zero filled chrome at
        // rest. The invalid variant swaps to the warning glyph + tint and states
        // "(invalid)" in text, so the failure reads without relying on color.
        <span
          className={cn(
            "inline-flex items-center gap-1",
            jsonInvalid ? "text-warning" : "text-muted-foreground/80",
          )}
          data-testid="json-output-chip"
        >
          {jsonInvalid ? (
            <TriangleAlert aria-hidden className="size-3" />
          ) : (
            <Braces aria-hidden className="size-3" />
          )}
          <span>{jsonInvalid ? "JSON (invalid)" : "JSON"}</span>
        </span>
      ) : null}
    </div>
  );
}
