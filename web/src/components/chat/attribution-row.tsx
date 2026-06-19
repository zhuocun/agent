"use client";

import * as React from "react";
import { Braces, Info, Key, TriangleAlert } from "lucide-react";

import type { ModelAttribution, ModelTierId } from "@/lib/types";
import { cn } from "@/lib/utils";
import { MODEL_TIERS_BY_ID } from "@/lib/model-tiers";

export interface AttributionRowProps {
  attribution: ModelAttribution;
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

// Bare interpunct used between byline segments.
const Dot = (
  <span aria-hidden className="text-muted-foreground/60">
    ·
  </span>
);

export function AttributionRow({
  attribution,
}: AttributionRowProps): React.JSX.Element {
  const { substitution, isByok, servedModelLabel, outputFormat } = attribution;
  const showJsonChip = outputFormat !== undefined;
  const jsonInvalid = attribution.outputValid === false;
  const servedTierId = assertServedTier(attribution.servedTierId);
  const providerLabel = attribution.providerLabel?.trim() || undefined;
  const tierLabel = servedTierLabelFor(servedTierId);
  const byokLabel = providerLabel
    ? `Your ${providerLabel} key`
    : "Your API key";
  const showTier = tierLabel !== servedModelLabel;
  const showProvider =
    providerLabel !== undefined &&
    providerLabel !== servedModelLabel &&
    providerLabel !== tierLabel;

  const triggerLabel = [
    substitution
      ? `Rerouted from ${requestedTierLabelFor(attribution.requestedTierId)} tier`
      : null,
    `served by ${servedModelLabel}`,
    providerLabel ? `provider ${providerLabel}` : null,
    `${tierLabel} tier`,
    isByok ? `billed to ${byokLabel.toLowerCase()}` : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 font-sans text-xs text-muted-foreground"
      data-testid="message-attribution"
      aria-label={triggerLabel}
    >
      {substitution ? (
        <span
          className="inline-flex items-center gap-1 rounded-full bg-substitution-callout px-1.5 py-0.5 text-2xs font-medium text-substitution-callout-foreground ring-1 ring-substitution-callout-border"
          data-testid="attribution-substitution"
        >
          <Info aria-hidden className="size-3 shrink-0" />
          <span>Rerouted</span>
        </span>
      ) : null}
      <span className="inline-flex flex-wrap items-center gap-1">
        <span>{servedModelLabel}</span>
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
      </span>
      {isByok ? (
        <span className="inline-flex items-center gap-1 text-muted-foreground/80">
          <Key aria-hidden className="size-3" />
          <span>{byokLabel}</span>
        </span>
      ) : null}
      {showJsonChip ? (
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
