import * as React from "react";
import { Info, Key } from "lucide-react";

import type { ModelTierId, PublicAttribution } from "@/lib/types";
import { cn } from "@/lib/utils";
import { MODEL_TIERS_BY_ID } from "@/lib/model-tiers";

export interface PublicAttributionRowProps {
  attribution: PublicAttribution;
}

// The private `AttributionRow` (components/chat/attribution-row.tsx) hard-wires
// cost: it formats `costUsd`, renders a `costConfidence` "~" marker, and opens a
// `CostBreakdownDetails` popover. The public share contract structurally has NO
// cost (web/src/lib/types.ts `PublicAttribution`), so reusing that component
// would force fabricated cost props. Instead this is a trimmed, static byline
// that keeps the SAME typography and the SAME model-identity semantics — served
// model label, substitution callout, optional BYOK chip — minus the interactive
// cost popover. The callout is NOT optional here: PRD 07 §6.4 ships
// `substitution` on the public payload precisely so a stranger sees when the
// served model differed from the one asked for, and UI-TRUST-5 makes rendering
// it a must. Only cost is stripped on this surface.

type ServedTierId = Exclude<ModelTierId, "auto">;

function assertServedTier(id: ModelTierId): ServedTierId {
  if (id === "auto") {
    throw new Error(
      "attribution.servedTierId must be a concrete tier; 'auto' must be resolved upstream",
    );
  }
  return id;
}

export function PublicAttributionRow({
  attribution,
}: PublicAttributionRowProps): React.JSX.Element {
  const { isByok, servedModelLabel, substitution } = attribution;
  const servedTierId = assertServedTier(attribution.servedTierId);
  const tierLabel = MODEL_TIERS_BY_ID[servedTierId].label;
  const providerLabel = attribution.providerLabel?.trim() || undefined;
  const byokLabel = providerLabel
    ? `Your ${providerLabel} key`
    : "Your API key";
  // Prefer the friendly served-model label; fall back to the tier display name.
  const answerLabel = servedModelLabel.trim() || tierLabel;
  const answerLine = `Answered with ${answerLabel}`;
  const ariaLabel = [
    substitution ? `Rerouted: ${substitution.reasonText}` : null,
    answerLine,
    providerLabel ? `provider ${providerLabel}` : null,
    isByok ? byokLabel : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className="flex flex-wrap items-center gap-x-2 gap-y-1 font-sans ui-caption text-muted-foreground"
      data-testid="public-attribution"
      aria-label={ariaLabel}
    >
      {substitution ? (
        <span
          className={cn(
            "inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 ui-caption font-medium",
            "bg-substitution-callout text-substitution-callout-foreground",
            "ring-1 ring-substitution-callout-border",
          )}
          data-testid="public-attribution-substitution"
        >
          <Info aria-hidden className="size-3 shrink-0" />
          <span className="min-w-0 text-pretty">{substitution.reasonText}</span>
        </span>
      ) : null}
      <span>{answerLine}</span>

      {isByok ? (
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 ui-caption",
            "bg-byok-indicator text-byok-indicator-foreground",
          )}
        >
          <Key aria-hidden className="size-3" />
          <span>{byokLabel}</span>
        </span>
      ) : null}
    </div>
  );
}
