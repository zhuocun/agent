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
// model label, optional tier, substitution clause, BYOK chip — minus the
// interactive cost popover. Lowest-churn correct approach: a small sibling, not
// a refactor of the cost-bearing private row.

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
  const { substitution, isByok, servedModelLabel } = attribution;
  const servedTierId = assertServedTier(attribution.servedTierId);
  const tierLabel = MODEL_TIERS_BY_ID[servedTierId].label;
  const providerLabel = attribution.providerLabel?.trim() || undefined;
  const byokLabel = providerLabel
    ? `Your ${providerLabel} key`
    : "Your API key";
  const substitutionPrefix = substitution
    ? `Rerouted from ${MODEL_TIERS_BY_ID[attribution.requestedTierId].label} tier — `
    : null;
  const ariaLabel = [
    substitutionPrefix,
    `served by ${servedModelLabel}`,
    providerLabel ? `provider ${providerLabel}` : null,
    `${tierLabel} tier`,
    isByok ? byokLabel : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className="flex flex-wrap items-center gap-x-2 gap-y-1 font-sans text-sm text-muted-foreground"
      data-testid="public-attribution"
      aria-label={ariaLabel}
    >
      {substitutionPrefix ? (
        <span className="inline-flex items-center gap-1 text-muted-foreground/80">
          <Info aria-hidden className="size-3" />
          <span>{substitutionPrefix}</span>
        </span>
      ) : null}
      <span>{tierLabel}</span>

      {isByok ? (
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs",
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
