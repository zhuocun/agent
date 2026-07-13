"use client";

import * as React from "react";
import { Info, Key } from "lucide-react";

import type { ModelAttribution, ModelTierId } from "@/lib/types";
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

export function AttributionRow({
  attribution,
}: AttributionRowProps): React.JSX.Element {
  const { substitution, isByok, servedModelLabel, outputFormat } = attribution;
  const jsonInvalid = attribution.outputValid === false;
  const servedTierId = assertServedTier(attribution.servedTierId);
  const providerLabel = attribution.providerLabel?.trim() || undefined;
  const tierLabel = servedTierLabelFor(servedTierId);
  const byokLabel = providerLabel
    ? `Your ${providerLabel} key`
    : "Your API key";

  const triggerLabel = [
    substitution
      ? `Rerouted from ${requestedTierLabelFor(attribution.requestedTierId)} tier`
      : null,
    `served by ${servedModelLabel}`,
    providerLabel ? `provider ${providerLabel}` : null,
    `${tierLabel} tier`,
    isByok ? `billed to ${byokLabel.toLowerCase()}` : null,
    outputFormat !== undefined
      ? jsonInvalid
        ? "structured JSON output (invalid)"
        : "structured JSON output"
      : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 font-sans ui-caption text-muted-foreground"
      data-testid="message-attribution"
      aria-label={triggerLabel}
    >
      {substitution ? (
        <span
          className="inline-flex max-w-full flex-col items-start gap-0.5 rounded-md bg-substitution-callout px-2 py-1.5 ui-caption font-medium text-substitution-callout-foreground ring-1 ring-substitution-callout-border sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-1.5 sm:rounded-full sm:px-1.5 sm:py-0.5"
          data-testid="attribution-substitution"
        >
          <span className="inline-flex min-w-0 items-center gap-1">
            <Info aria-hidden className="size-3 shrink-0" />
            <span className="min-w-0 text-pretty">
              Rerouted from {requestedTierLabelFor(attribution.requestedTierId)}{" "}
              → {servedModelLabel}
            </span>
          </span>
          <span className="ps-4 font-normal text-substitution-callout-foreground/85 sm:ps-0">
            <span className="hidden sm:inline" aria-hidden>
              ·{" "}
            </span>
            {substitution.reasonText}
          </span>
        </span>
      ) : null}
      <span>{tierLabel}</span>
      {isByok ? (
        <span className="inline-flex items-center gap-1 text-muted-foreground/80">
          <Key aria-hidden className="size-3" />
          <span>{byokLabel}</span>
        </span>
      ) : null}
    </div>
  );
}
