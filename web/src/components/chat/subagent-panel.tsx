"use client";

import type { ReactNode } from "react";
import {
  CheckCircle2,
  ChevronDown,
  Info,
  Loader2,
  Telescope,
} from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { MODEL_TIERS_BY_ID } from "@/lib/model-tiers";
import type { RunCostState } from "@/lib/stream-client";
import type { ModelAttribution } from "@/lib/types";

// One orchestrator subagent's section, shape-compatible with the live
// `SubagentActivity` from stream-client AND derivable from a persisted
// message's `subagent` marker + tagged parts (assistant-message.tsx owns that
// derivation), so the streaming bubble and a reloaded transcript render
// identically through this one component.
export interface SubagentSection {
  subagentId: string;
  label: string;
  role: string;
  status: "running" | "done";
  costUsd?: number;
  // Per-subagent model attribution (FR-26e: no silent downgrade inside a
  // fan-out). Present only when the BE persisted/streamed it for this subagent;
  // its `substitution` clause drives the row's served-model/rerouted callout.
  attribution?: ModelAttribution;
  reasoning: string;
  answer: string;
}

interface SubagentPanelProps {
  sections: SubagentSection[];
  // Live run-cost subtotal vs the per-run cap (the `run_cost` SSE event).
  // Null/absent on a reloaded transcript — the BE doesn't persist the cap —
  // so the meter then falls back to the summed per-subagent costs.
  runCost?: RunCostState | null;
}

// Mirrors attribution-row's cost summary so per-worker and run totals read in
// the same grammar as the message byline.
function formatUsd(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.0001) return "<$0.0001";
  const decimals = n < 0.01 ? 4 : n < 1 ? 3 : 2;
  return `$${n.toFixed(decimals)}`;
}

// Orchestration-role wording for the row pill. Roles come from the BE
// orchestrator (`primary` / `worker` / `aggregator` / `orchestrator`); unknown
// future roles fall through verbatim rather than erroring.
function roleLabel(role: string): string {
  switch (role) {
    case "primary":
      return "Primary";
    case "worker":
      return "Worker";
    case "aggregator":
      return "Aggregator";
    case "orchestrator":
      return "Orchestrator";
    default:
      return role;
  }
}

// Per-worker activity + run-cost meter for an agentic (multi-agent) turn.
// Modeled on the tool-part grammar: a quiet bordered card whose rows collapse
// their detail behind a one-line summary (progressive disclosure). Running
// rows stay expanded — they carry live streaming text.
export function SubagentPanel({ sections, runCost }: SubagentPanelProps) {
  if (sections.length === 0) return null;

  const runningCount = sections.filter((s) => s.status === "running").length;
  // Deep-research runs carry worker/aggregator roles; a `single`-mode turn is
  // one primary subagent. Title accordingly so a single-agent panel doesn't
  // overclaim "Deep research".
  const isDeepResearch = sections.some(
    (s) => s.role === "worker" || s.role === "aggregator",
  );
  const title = isDeepResearch ? "Deep research" : "Agent activity";
  const summary =
    runningCount > 0
      ? `${runningCount} of ${sections.length} running`
      : sections.length === 1
        ? "1 agent"
        : `${sections.length} agents`;

  // Run-cost meter: prefer the live `run_cost` frame (subtotal vs cap); on a
  // reloaded transcript fall back to the summed per-subagent costs (no cap).
  const summedCost = sections.reduce((acc, s) => acc + (s.costUsd ?? 0), 0);
  const subtotalUsd = runCost ? runCost.subtotalUsd : summedCost;
  const capUsd = runCost && runCost.capUsd > 0 ? runCost.capUsd : null;
  // Header meter earns its place when a live cap exists, or when the summed
  // cost is above the sub-cent noise floor — otherwise it duplicates row costs.
  const showMeter =
    (runCost != null && runCost.capUsd > 0) || summedCost >= 0.0001;

  return (
    <div
      data-testid="subagent-panel"
      className="max-w-full rounded-xl border border-foreground/[0.06] bg-foreground/[0.02] px-3 py-2.5 text-sm text-muted-foreground"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Telescope aria-hidden className="size-4 shrink-0" />
        <span className="font-medium text-foreground">{title}</span>
        <span className="text-xs text-muted-foreground">{summary}</span>
        {showMeter ? (
          <RunCostMeter subtotalUsd={subtotalUsd} capUsd={capUsd} />
        ) : null}
      </div>
      <ul className="mt-2 flex flex-col gap-1.5">
        {sections.map((section) => (
          <li key={section.subagentId} className="list-none">
            <SubagentRow section={section} />
          </li>
        ))}
      </ul>
    </div>
  );
}

// Subtotal-vs-cap meter, kept in the usage-meter grammar (hairline capacity
// bar + mono figure). Without a cap (reloaded transcript) only the figure
// renders — an uncapped bar would be a made-up ratio.
function RunCostMeter({
  subtotalUsd,
  capUsd,
}: {
  subtotalUsd: number;
  capUsd: number | null;
}) {
  const pct =
    capUsd !== null ? Math.min(Math.round((subtotalUsd / capUsd) * 100), 100) : 0;
  const label =
    capUsd !== null
      ? `Run cost ${formatUsd(subtotalUsd)} of ${formatUsd(capUsd)} cap`
      : `Run cost ${formatUsd(subtotalUsd)}`;
  return (
    <span
      className="ml-auto inline-flex shrink-0 items-center gap-2 text-2xs"
      data-testid="run-cost-meter"
      title={label}
    >
      {capUsd !== null ? (
        <span
          role="progressbar"
          aria-label={label}
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuetext={label}
          className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-foreground/8"
        >
          <span
            className="block h-full rounded-full bg-brand/80 transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </span>
      ) : null}
      <span className="font-mono tabular-nums">
        {formatUsd(subtotalUsd)}
        {capUsd !== null ? ` / ${formatUsd(capUsd)}` : ""}
      </span>
    </span>
  );
}

function SubagentRow({ section }: { section: SubagentSection }) {
  const isRunning = section.status === "running";
  const substitution = section.attribution?.substitution;
  const servedModelLabel = section.attribution?.servedModelLabel;
  const hasDetail =
    section.reasoning.length > 0 ||
    section.answer.length > 0 ||
    substitution !== undefined;

  const costBadge =
    section.costUsd !== undefined ? (
      <span className="shrink-0 font-mono text-2xs tabular-nums text-muted-foreground">
        {formatUsd(section.costUsd)}
      </span>
    ) : null;

  // Rerouted callout (FR-26e): a per-subagent substitution is a user-facing
  // alert, not metadata, so it stays in the summary line even when the row is
  // collapsed — mirroring the byline's substitution chip (attribution-row.tsx).
  // The full "answered by X because Y" reason rides the title + detail body.
  const substitutionBadge = substitution ? (
    <span
      data-testid="subagent-substitution"
      title={substitution.reasonText}
      className="inline-flex shrink-0 items-center gap-1 rounded-full bg-substitution-callout px-1.5 py-0.5 text-2xs font-medium text-substitution-callout-foreground ring-1 ring-substitution-callout-border"
    >
      <Info aria-hidden className="size-3 shrink-0" />
      <span>Rerouted</span>
    </span>
  ) : null;

  const summaryRow = (trailing?: ReactNode) => (
    <div className="flex min-w-0 flex-1 items-center gap-1.5">
      <span className="min-w-0 truncate font-medium text-foreground">
        {section.label}
      </span>
      <span className="inline-flex h-5 shrink-0 items-center rounded-full bg-foreground/[0.06] px-2 text-2xs text-muted-foreground">
        {roleLabel(section.role)}
      </span>
      <span className="ml-auto flex shrink-0 items-center gap-1.5">
        {substitutionBadge}
        {costBadge}
        {trailing}
      </span>
    </div>
  );

  // Served-model / substitution callout for the detail body: names the model
  // that actually answered this subagent and, on a reroute, why it differs from
  // the requested tier (silent-downgrade prevention, FR-26e). Rendered only
  // when there's something to say (a substitution clause or a served label).
  const attributionNote =
    substitution && section.attribution ? (
      <p
        className="break-words text-xs leading-snug text-muted-foreground"
        data-testid="subagent-attribution"
      >
        <span className="font-medium text-foreground">
          Rerouted from{" "}
          {MODEL_TIERS_BY_ID[section.attribution.requestedTierId].label} tier
        </span>
        {" — "}
        {substitution.reasonText}
      </p>
    ) : servedModelLabel ? (
      <p
        className="break-words text-xs leading-snug text-muted-foreground"
        data-testid="subagent-attribution"
      >
        Served by {servedModelLabel}
      </p>
    ) : null;

  const detailBody = hasDetail ? (
    <div className="mt-1 space-y-1">
      {attributionNote}
      {section.reasoning ? (
        <p className="line-clamp-3 break-words text-xs italic leading-snug text-muted-foreground">
          {section.reasoning}
        </p>
      ) : null}
      {section.answer ? (
        <p className="whitespace-pre-wrap break-words text-xs leading-snug text-muted-foreground">
          {section.answer}
        </p>
      ) : null}
    </div>
  ) : null;

  const statusIcon = isRunning ? (
    <Loader2
      aria-hidden
      className="mt-0.5 size-4 shrink-0 motion-safe:animate-spin"
    />
  ) : (
    <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-success" />
  );

  // Running rows render fully expanded — their text is streaming in live and
  // collapsing it would hide the very activity the panel exists to show.
  if (isRunning || !hasDetail) {
    return (
      <div
        data-testid="subagent-row"
        data-subagent-id={section.subagentId}
        className="flex items-start gap-2 rounded-lg bg-foreground/[0.02] px-2.5 py-2"
      >
        {statusIcon}
        <div className="min-w-0 flex-1">
          {summaryRow()}
          {detailBody}
        </div>
      </div>
    );
  }

  // Settled rows collapse their detail behind the summary line, mirroring the
  // tool-part disclosure (chevron + height/opacity tween; reduced-motion users
  // get the instant collapse via the globals.css collapsible override).
  return (
    <Collapsible
      data-testid="subagent-row"
      data-subagent-id={section.subagentId}
      className="flex items-start gap-2 rounded-lg bg-foreground/[0.02] px-2.5 py-2"
    >
      {statusIcon}
      <div className="min-w-0 flex-1">
        <CollapsibleTrigger
          className={cn(
            "group/subagent-trigger flex w-full min-w-0 items-center text-left",
            "min-h-11 bg-transparent py-2 -my-2 outline-none md:min-h-0 md:py-0 md:my-0",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
          aria-label={`${section.label}, ${roleLabel(section.role)} — toggle details`}
        >
          {summaryRow(
            <ChevronDown
              aria-hidden
              className="size-3.5 shrink-0 transition-transform duration-300 ease-[var(--ease-ios-spring)] motion-reduce:transition-none group-data-[panel-open]/subagent-trigger:rotate-180"
            />,
          )}
        </CollapsibleTrigger>
        <CollapsibleContent
          keepMounted
          className={cn(
            "overflow-hidden",
            "transition-[height,opacity] duration-200 ease-[var(--ease-ios-smooth)]",
            "h-[var(--collapsible-panel-height)] opacity-100",
            "data-[starting-style]:h-0 data-[starting-style]:opacity-0",
            "data-[ending-style]:h-0 data-[ending-style]:opacity-0",
          )}
        >
          {detailBody}
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
