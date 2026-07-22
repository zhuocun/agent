"use client";

import type { ReactNode } from "react";
import {
  CheckCircle2,
  ChevronDown,
  CircleMinus,
  Loader2,
  Telescope,
  XCircle,
} from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { formatUsdMeter } from "@/lib/money";
import { cn } from "@/lib/utils";
import type { ToolGroup, WebSearchGroup } from "@/lib/tool-groups";
import type { RunCostState } from "@/lib/stream-client";
import type { ModelAttribution, SubagentOutcome } from "@/lib/types";
import { WebSearchPanel } from "@/components/chat/web-search-panel";
import { ToolGroupPanel } from "@/components/chat/tool-group-panel";
import { ToolPartView } from "@/components/chat/tool-part";
import { panelAnswerForSection } from "@/lib/agentic-layout";
import { stripToolMarkup } from "@/lib/strip-tool-markup";
import type { MessagePart } from "@/lib/types";

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
  outcome?: SubagentOutcome;
  costUsd?: number;
  attribution?: Pick<
    ModelAttribution,
    | "servedModelLabel"
    | "providerLabel"
    | "requestedTierId"
    | "servedTierId"
    | "substitution"
  > &
    Partial<ModelAttribution>;
  reasoning: string;
  answer: string;
}

interface SubagentPanelProps {
  sections: SubagentSection[];
  runCost?: RunCostState | null;
  // Web-search activity owned by a subagent (or untagged but co-occurring with
  // this panel) renders inside the agent-activity card instead of as a sibling.
  panelWebSearchGroups?: WebSearchGroup[];
  webSearchBySubagentId?: ReadonlyMap<string, WebSearchGroup[]>;
  // Generic tool-group activity owned by a subagent (or untagged but
  // co-occurring with this panel) nests inside the card, mirroring the
  // web-search nesting above.
  panelToolGroups?: ToolGroup[];
  toolGroupsBySubagentId?: ReadonlyMap<string, ToolGroup[]>;
  panelLiveToolParts?: LiveToolPart[];
  liveToolPartsBySubagentId?: ReadonlyMap<string, LiveToolPart[]>;
  onToolDecision?: (d: { toolCallId: string; decision: "approve" | "deny"; editedInput?: Record<string, unknown> }) => void;
}

type LiveToolPart = Extract<MessagePart, { type: "tool_call" | "tool_result" }>;

// Per-worker activity for an agentic (multi-agent) turn.
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

// Per-worker activity for an agentic (multi-agent) turn. Modeled on the
// tool-part grammar: a quiet bordered card whose rows collapse
// their detail behind a one-line summary (progressive disclosure). Running
// rows stay expanded — they carry live streaming text.
export function SubagentPanel({
  sections: rawSections,
  runCost = null,
  panelWebSearchGroups = [],
  webSearchBySubagentId,
  panelToolGroups = [],
  toolGroupsBySubagentId,
  panelLiveToolParts = [],
  liveToolPartsBySubagentId,
  onToolDecision,
}: SubagentPanelProps) {
  // Display-side net: scrub any leaked tool-call markup out of task labels and
  // panel text (mirrors the BE sanitizer) so a pre-leaked section never shows
  // raw. Streaming/persistence are untouched.
  const sections = rawSections.map((s) => ({
    ...s,
    label: stripToolMarkup(s.label),
    reasoning: stripToolMarkup(s.reasoning),
    answer: stripToolMarkup(s.answer),
  }));
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

  const singleAgentFlat = sections.length === 1 && !isDeepResearch;

  return (
    <div
      data-testid="subagent-panel"
      className="max-w-full rounded-xl border border-foreground/[0.06] bg-foreground/[0.02] px-3 py-2.5 ui-body text-muted-foreground"
    >
      <Collapsible defaultOpen>
        <CollapsibleTrigger
          data-testid="subagent-panel-trigger"
          className={cn(
            "group/subagent-panel-trigger flex w-full min-w-0 items-center gap-x-2 gap-y-1 text-left",
            "min-h-11 bg-transparent py-2 -my-2 outline-none md:min-h-0 md:py-0 md:my-0",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
          aria-label={`${title} — toggle details`}
        >
          <Telescope aria-hidden className="size-4 shrink-0" />
          <span className="font-medium text-foreground">{title}</span>
          {runCost ? <RunCostMeter runCost={runCost} /> : null}
          {!singleAgentFlat ? (
            <span className="ui-caption text-muted-foreground">{summary}</span>
          ) : null}
          <ChevronDown
            aria-hidden
            className="ml-auto size-3.5 shrink-0 transition-transform duration-300 ease-[var(--ease-ios-spring)] motion-reduce:transition-none group-data-[panel-open]/subagent-panel-trigger:rotate-180"
          />
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
          {panelWebSearchGroups.length > 0 ? (
            <div className="mt-2 space-y-1" data-testid="subagent-panel-web-search">
              {panelWebSearchGroups.map((group, idx) => (
                <WebSearchPanel
                  key={`panel-web-search-${idx}`}
                  group={group}
                  onDecision={onToolDecision}
                  embedded
                />
              ))}
            </div>
          ) : null}
          {panelToolGroups.length > 0 ? (
            <div className="mt-2 space-y-1" data-testid="subagent-panel-tools">
              {panelToolGroups.map((group, idx) => (
                <ToolGroupPanel
                  key={`panel-tools-${idx}`}
                  group={group}
                  onDecision={onToolDecision}
                  embedded
                />
              ))}
            </div>
          ) : null}
          {panelLiveToolParts.length > 0 ? (
            <LiveToolPartsBlock
              parts={panelLiveToolParts}
              onToolDecision={onToolDecision}
              testId="subagent-panel-live-tools"
            />
          ) : null}
          {singleAgentFlat ? (
            <SingleAgentContent
              section={sections[0]!}
              webSearchGroups={webSearchBySubagentId?.get(sections[0]!.subagentId)}
              toolGroups={toolGroupsBySubagentId?.get(sections[0]!.subagentId)}
              liveToolParts={liveToolPartsBySubagentId?.get(sections[0]!.subagentId)}
              onToolDecision={onToolDecision}
            />
          ) : (
            <ul className="mt-2 flex flex-col gap-1.5">
              {sections.map((section) => (
                <li key={section.subagentId} className="list-none">
                  <SubagentRow
                    section={section}
                    webSearchGroups={webSearchBySubagentId?.get(section.subagentId)}
                    toolGroups={toolGroupsBySubagentId?.get(section.subagentId)}
                    liveToolParts={liveToolPartsBySubagentId?.get(section.subagentId)}
                    onToolDecision={onToolDecision}
                  />
                </li>
              ))}
            </ul>
          )}
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

function RunCostMeter({ runCost }: { runCost: RunCostState }) {
  const isEstimate =
    runCost.confidence === "estimate" || runCost.phase === "plan";
  const prefix = isEstimate ? "Est. " : "";
  const ariaExtra = isEstimate ? " estimated" : "";
  return (
    <span
      data-testid="run-cost-meter"
      data-confidence={runCost.confidence ?? "exact"}
      data-phase={runCost.phase ?? "final"}
      className="inline-flex h-5 items-center rounded-full bg-foreground/[0.06] px-2 ui-caption text-muted-foreground"
      aria-label={`Run cost${ariaExtra} ${formatUsdMeter(runCost.subtotalUsd)}${
        runCost.capUsd > 0 ? ` of ${formatUsdMeter(runCost.capUsd)} cap` : ""
      }`}
    >
      {prefix}
      {formatUsdMeter(runCost.subtotalUsd)}
      {runCost.capUsd > 0 ? (
        <span className="text-muted-foreground/70">
          {" "}
          / {formatUsdMeter(runCost.capUsd)}
        </span>
      ) : null}
    </span>
  );
}

function OutcomeIcon({
  status,
  outcome,
}: {
  status: "running" | "done";
  outcome?: SubagentOutcome;
}) {
  if (status === "running") {
    return (
      <Loader2
        aria-hidden
        className="mt-0.5 size-4 shrink-0 motion-safe:animate-spin"
      />
    );
  }
  const resolved: SubagentOutcome = outcome ?? "succeeded";
  switch (resolved) {
    case "failed":
      return (
        <XCircle
          aria-hidden
          data-testid="subagent-outcome-failed"
          className="mt-0.5 size-4 shrink-0 text-destructive"
        />
      );
    case "cancelled":
    case "budget_cancelled":
    case "stopped":
      return (
        <CircleMinus
          aria-hidden
          data-testid="subagent-outcome-cancelled"
          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
        />
      );
    case "succeeded":
      return (
        <CheckCircle2
          aria-hidden
          data-testid="subagent-outcome-succeeded"
          className="mt-0.5 size-4 shrink-0 text-success"
        />
      );
    default: {
      const _exhaustive: never = resolved;
      return _exhaustive;
    }
  }
}

function LiveToolPartsBlock({
  parts,
  onToolDecision,
  testId,
}: {
  parts: LiveToolPart[];
  onToolDecision?: (d: { toolCallId: string; decision: "approve" | "deny"; editedInput?: Record<string, unknown> }) => void;
  testId: string;
}) {
  if (parts.length === 0) return null;
  return (
    <div className="mt-2 space-y-0.5" data-testid={testId}>
      {parts.map((part, idx) => (
        <ToolPartView
          key={
            part.type === "tool_call"
              ? `call-${part.id}`
              : `result-${part.toolCallId}-${idx}`
          }
          part={part}
          onDecision={onToolDecision}
          embedded
        />
      ))}
    </div>
  );
}

function SingleAgentContent({
  section,
  webSearchGroups,
  toolGroups,
  liveToolParts,
  onToolDecision,
}: {
  section: SubagentSection;
  webSearchGroups?: WebSearchGroup[];
  toolGroups?: ToolGroup[];
  liveToolParts?: LiveToolPart[];
  onToolDecision?: (d: { toolCallId: string; decision: "approve" | "deny"; editedInput?: Record<string, unknown> }) => void;
}) {
  const isRunning = section.status === "running";
  const panelAnswer = panelAnswerForSection(section);
  const hasText = section.reasoning.length > 0 || panelAnswer.length > 0;

  const webSearchBlock =
    webSearchGroups && webSearchGroups.length > 0 ? (
      <div className="mt-2 space-y-1" data-testid="subagent-row-web-search">
        {webSearchGroups.map((group, idx) => (
          <WebSearchPanel
            key={`${section.subagentId}-web-search-${idx}`}
            group={group}
            onDecision={onToolDecision}
            embedded
          />
        ))}
      </div>
    ) : null;

  const toolGroupsBlock =
    toolGroups && toolGroups.length > 0 ? (
      <div className="mt-2 space-y-1" data-testid="subagent-row-tools">
        {toolGroups.map((group, idx) => (
          <ToolGroupPanel
            key={`${section.subagentId}-tools-${idx}`}
            group={group}
            onDecision={onToolDecision}
            embedded
          />
        ))}
      </div>
    ) : null;

  return (
    <div
      data-testid="subagent-row"
      data-subagent-id={section.subagentId}
      className="mt-2"
    >
      {isRunning ? (
        <div className="mb-1 flex items-center gap-1.5 ui-caption text-muted-foreground">
          <Loader2
            aria-hidden
            className="size-3.5 shrink-0 motion-safe:animate-spin"
          />
          <span>Working…</span>
        </div>
      ) : null}
      {hasText ? (
        <div className="space-y-1">
          {section.reasoning ? (
            <p className="line-clamp-3 break-words ui-caption italic leading-snug text-muted-foreground">
              {section.reasoning}
            </p>
          ) : null}
          {panelAnswer ? (
            <p className="whitespace-pre-wrap break-words ui-caption leading-snug text-muted-foreground">
              {panelAnswer}
            </p>
          ) : null}
        </div>
      ) : null}
      {webSearchBlock}
      {toolGroupsBlock}
      {liveToolParts && liveToolParts.length > 0 ? (
        <LiveToolPartsBlock
          parts={liveToolParts}
          onToolDecision={onToolDecision}
          testId="subagent-row-live-tools"
        />
      ) : null}
    </div>
  );
}

function SubagentRow({
  section,
  webSearchGroups,
  toolGroups,
  liveToolParts,
  onToolDecision,
}: {
  section: SubagentSection;
  webSearchGroups?: WebSearchGroup[];
  toolGroups?: ToolGroup[];
  liveToolParts?: LiveToolPart[];
  onToolDecision?: (d: { toolCallId: string; decision: "approve" | "deny"; editedInput?: Record<string, unknown> }) => void;
}) {
  const isRunning = section.status === "running";
  const panelAnswer = panelAnswerForSection(section);
  const hasTextDetail =
    section.reasoning.length > 0 || panelAnswer.length > 0;

  const summaryRow = (trailing?: ReactNode) => (
    <div className="flex min-w-0 flex-1 items-center gap-1.5">
      <span className="min-w-0 truncate font-medium text-foreground">
        {section.label}
      </span>
      <span className="inline-flex h-5 shrink-0 items-center rounded-full bg-foreground/[0.06] px-2 ui-caption text-muted-foreground">
        {roleLabel(section.role)}
      </span>
      {section.status === "done" && section.attribution?.servedModelLabel ? (
        <span
          className="max-w-[10rem] truncate ui-caption text-muted-foreground"
          data-testid="subagent-served-model"
          title={
            section.attribution.providerLabel
              ? `${section.attribution.servedModelLabel} · ${section.attribution.providerLabel}`
              : section.attribution.servedModelLabel
          }
        >
          {section.attribution.servedModelLabel}
        </span>
      ) : null}
      {section.attribution?.substitution ? (
        <span
          className="max-w-full truncate ui-caption text-substitution-callout-foreground"
          data-testid="subagent-substitution-callout"
          title={section.attribution.substitution.reasonText}
        >
          Rerouted → {section.attribution.servedModelLabel}
        </span>
      ) : null}
      <span className="ml-auto flex shrink-0 items-center gap-1.5">
        {trailing}
      </span>
    </div>
  );

  const webSearchBlock =
    webSearchGroups && webSearchGroups.length > 0 ? (
      <div className="mt-2 space-y-2" data-testid="subagent-row-web-search">
        {webSearchGroups.map((group, idx) => (
          <WebSearchPanel
            key={`${section.subagentId}-web-search-${idx}`}
            group={group}
            onDecision={onToolDecision}
            embedded
          />
        ))}
      </div>
    ) : null;

  const toolGroupsBlock =
    toolGroups && toolGroups.length > 0 ? (
      <div className="mt-2 space-y-2" data-testid="subagent-row-tools">
        {toolGroups.map((group, idx) => (
          <ToolGroupPanel
            key={`${section.subagentId}-tools-${idx}`}
            group={group}
            onDecision={onToolDecision}
            embedded
          />
        ))}
      </div>
    ) : null;

  const liveToolsBlock =
    liveToolParts && liveToolParts.length > 0 ? (
      <LiveToolPartsBlock
        parts={liveToolParts}
        onToolDecision={onToolDecision}
        testId="subagent-row-live-tools"
      />
    ) : null;

  const textDetailBody = hasTextDetail ? (
    <div className="mt-1 space-y-1">
      {section.reasoning ? (
        <p className="line-clamp-3 break-words ui-caption italic leading-snug text-muted-foreground">
          {section.reasoning}
        </p>
      ) : null}
      {panelAnswer ? (
        <p className="whitespace-pre-wrap break-words ui-caption leading-snug text-muted-foreground">
          {panelAnswer}
        </p>
      ) : null}
    </div>
  ) : null;

  const detailBody = (
    <>
      {textDetailBody}
      {webSearchBlock}
      {toolGroupsBlock}
      {liveToolsBlock}
    </>
  );

  const statusIcon = (
    <OutcomeIcon status={section.status} outcome={section.outcome} />
  );

  // Running rows render fully expanded — their text is streaming in live and
  // collapsing it would hide the very activity the panel exists to show.
  if (isRunning || !hasTextDetail) {
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
          {textDetailBody}
        </CollapsibleContent>
        {webSearchBlock}
        {toolGroupsBlock}
        {liveToolsBlock}
      </div>
    </Collapsible>
  );
}
