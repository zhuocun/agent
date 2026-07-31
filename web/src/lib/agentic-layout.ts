// Shared agentic-turn layout derivation for the private thread and the public
// share view. Framework-free — mirrors assistant-message.tsx's panel wiring so
// both surfaces stay in sync.

import type { SubagentSection } from "@/components/chat/subagent-panel";
import {
  groupToolParts,
  partitionToolGroups,
  partitionWebSearchGroups,
  type GroupedToolPart,
  type ToolGroupLayout,
} from "@/lib/tool-groups";
import type { RunCostState } from "@/lib/stream-client";
import { stripToolMarkup } from "@/lib/strip-tool-markup";
import { readSubagentOutcome } from "@/lib/subagent-outcome";
import type { MessagePart } from "@/lib/types";

const PLAN_APPROVAL_TOOL_NAME = "agentic_plan_approval";

export function deriveRunCostFromParts(
  parts: readonly MessagePart[],
): RunCostState | null {
  const summary = parts.find(
    (p): p is Extract<MessagePart, { type: "agentic_run_summary" }> =>
      p.type === "agentic_run_summary",
  );

  // AR-012 / A-4: prefer the persisted terminal receipt when present.
  if (
    summary &&
    typeof summary.subtotalUsd === "number" &&
    typeof summary.capUsd === "number"
  ) {
    return {
      subtotalUsd: summary.subtotalUsd,
      capUsd: summary.capUsd,
      confidence: summary.costConfidence ?? "exact",
      phase: summary.costPhase ?? "final",
      ...(summary.outcome === "partial" ? { partial: true } : {}),
      ...(summary.budgetHalted ? { budgetHalted: true } : {}),
      ...(typeof summary.failedWorkers === "number"
        ? { failedWorkerCount: summary.failedWorkers }
        : {}),
    };
  }

  let subtotalUsd = 0;
  let hasCost = false;
  for (const part of parts) {
    if (part.type === "subagent" && part.costUsd !== undefined) {
      subtotalUsd += part.costUsd;
      hasCost = true;
    }
  }
  if (!hasCost) return null;

  let capUsd = 0;
  if (typeof summary?.capUsd === "number") {
    capUsd = summary.capUsd;
  } else {
    for (const part of parts) {
      if (
        part.type === "tool_call" &&
        part.name === PLAN_APPROVAL_TOOL_NAME &&
        part.input &&
        typeof part.input.capUsd === "number"
      ) {
        capUsd = part.input.capUsd;
        break;
      }
    }
  }
  // FE-3: this branch ASSEMBLED the number by summing per-subagent costs, so it
  // is not a receipt and must never claim to be one. Default to the honest
  // estimate labels (`Est.` prefix + the "estimated" aria clause) rather than
  // `exact` / `final`, which would contradict the plan card's own "(estimate)"
  // line on a paused run.
  return {
    subtotalUsd: typeof summary?.subtotalUsd === "number" ? summary.subtotalUsd : subtotalUsd,
    capUsd,
    confidence: summary?.costConfidence ?? "estimate",
    phase: summary?.costPhase ?? "plan",
    ...(summary?.outcome === "partial" ? { partial: true } : {}),
    ...(summary?.budgetHalted ? { budgetHalted: true } : {}),
    ...(typeof summary?.failedWorkers === "number"
      ? { failedWorkerCount: summary.failedWorkers }
      : {}),
  };
}

export function deriveAgenticRunSummary(
  parts: readonly MessagePart[],
  liveRunCost?: RunCostState | null,
): {
  partial: boolean;
  budgetHalted: boolean;
  failedWorkers: number;
} | null {
  if (liveRunCost?.partial || liveRunCost?.budgetHalted) {
    return {
      partial: true,
      budgetHalted: liveRunCost.budgetHalted === true,
      failedWorkers: liveRunCost.failedWorkerCount ?? 0,
    };
  }
  const summary = parts.find(
    (p): p is Extract<MessagePart, { type: "agentic_run_summary" }> =>
      p.type === "agentic_run_summary",
  );
  if (!summary || summary.outcome !== "partial") return null;
  return {
    partial: true,
    budgetHalted: summary.budgetHalted === true,
    failedWorkers: summary.failedWorkers ?? 0,
  };
}

export function buildSubagentSectionsFromParts(
  parts: readonly MessagePart[],
): SubagentSection[] {
  const sections: SubagentSection[] = [];
  const byId = new Map<string, SubagentSection>();
  for (const part of parts) {
    if (part.type === "subagent") {
      const section: SubagentSection = {
        subagentId: part.subagentId,
        label: part.label,
        role: part.role,
        status: "done",
        // FE-9: validate the persisted string before it lands in a closed
        // union — a legacy or future value must not launder into a green check.
        outcome: readSubagentOutcome(part.outcome) ?? "succeeded",
        ...(part.costUsd !== undefined ? { costUsd: part.costUsd } : {}),
        ...(part.attribution !== undefined ? { attribution: part.attribution } : {}),
        reasoning: "",
        answer: "",
      };
      byId.set(part.subagentId, section);
      sections.push(section);
      continue;
    }
    if (
      (part.type === "reasoning" || part.type === "text") &&
      part.subagentId
    ) {
      const section = byId.get(part.subagentId);
      if (!section) continue;
      if (part.type === "reasoning") section.reasoning += part.text;
      else section.answer += part.text;
    }
  }
  return sections;
}

export function isMainAnswerRole(role: string): boolean {
  return role === "primary" || role === "aggregator";
}

/** Main-bubble answer: role primary/aggregator, or canonical orchestrator ids. */
export function isMainAnswerSubagent(subagentId: string, role: string): boolean {
  return (
    subagentId === "primary" ||
    subagentId === "aggregator" ||
    isMainAnswerRole(role)
  );
}

export function buildMainSubagentIds(parts: readonly MessagePart[]): Set<string> {
  const ids = new Set<string>();
  for (const part of parts) {
    if (
      part.type === "subagent" &&
      isMainAnswerSubagent(part.subagentId, part.role)
    ) {
      ids.add(part.subagentId);
    }
  }
  return ids;
}

export function buildSubagentRoleById(
  parts: readonly MessagePart[],
): Map<string, string> {
  const roles = new Map<string, string>();
  for (const part of parts) {
    if (part.type === "subagent") roles.set(part.subagentId, part.role);
  }
  return roles;
}

/**
 * Merge all sources parts into one catalog keyed by global citation id (B12).
 *
 * After mid-stream remapping, ids are unique across workers; unioning every
 * sources part lets aggregator text resolve citations that span workers even
 * when a dedicated aggregator catalog is missing.
 */
export function collectGlobalSourceItems(
  parts: readonly MessagePart[],
): Extract<MessagePart, { type: "sources" }>["items"] {
  const byId = new Map<
    number,
    Extract<MessagePart, { type: "sources" }>["items"][number]
  >();
  for (const part of parts) {
    if (part.type !== "sources") continue;
    for (const item of part.items) {
      if (!byId.has(item.id)) byId.set(item.id, item);
    }
  }
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

/**
 * Resolve citation sources for a text part (B12).
 *
 * Prefer the sources part tagged with the same `subagentId` as the text
 * (worker or aggregator catalog). Fall back to an untagged sources part, then
 * to the full global merge across all source parts so multi-worker citations
 * still resolve when only per-worker catalogs exist.
 */
export function resolveSourcesForTextPart(
  parts: readonly MessagePart[],
  textPart: Extract<MessagePart, { type: "text" }>,
): Extract<MessagePart, { type: "sources" }>["items"] {
  const sid = textPart.subagentId;
  if (sid != null) {
    const matching = parts.find(
      (p): p is Extract<MessagePart, { type: "sources" }> =>
        p.type === "sources" && p.subagentId === sid,
    );
    if (matching && matching.items.length > 0) return matching.items;
  }
  const untagged = parts.find(
    (p): p is Extract<MessagePart, { type: "sources" }> =>
      p.type === "sources" && p.subagentId == null,
  );
  if (untagged && untagged.items.length > 0) return untagged.items;
  return collectGlobalSourceItems(parts);
}

/** Whether a sources part should render as the main SourcesPanel (B12). */
export function shouldShowSourcesInMainPanel(
  part: Extract<MessagePart, { type: "sources" }>,
  subagentRoleById: ReadonlyMap<string, string>,
): boolean {
  if (part.subagentId == null) return true;
  const role = subagentRoleById.get(part.subagentId) ?? "subagent";
  return isMainAnswerSubagent(part.subagentId, role);
}

/** Whether a text part belongs in the main bubble (not panel-only worker text). */
export function shouldRenderTextInMainBubble(
  part: Extract<MessagePart, { type: "text" }>,
  subagentRoleById: ReadonlyMap<string, string>,
): boolean {
  if (part.subagentId == null) return true;
  const role = subagentRoleById.get(part.subagentId) ?? "subagent";
  return isMainAnswerSubagent(part.subagentId, role);
}

export interface MainBubbleTextResolution {
  answerText: string;
  effectiveAnswerText: string;
}

/** Resolve copy/render text for the main assistant bubble from persisted parts. */
export function resolveMainBubbleText(
  parts: readonly MessagePart[],
): MainBubbleTextResolution {
  const subagentRoleById = buildSubagentRoleById(parts);
  const answerText = parts
    .filter((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
    .filter((p) => shouldRenderTextInMainBubble(p, subagentRoleById))
    .map((p) => stripToolMarkup(p.text))
    .join("\n\n");
  return { answerText, effectiveAnswerText: answerText };
}

export function hasToolOrSubagentActivity(
  parts: readonly MessagePart[],
): boolean {
  return parts.some(
    (p) =>
      p.type === "tool_call" ||
      p.type === "tool_result" ||
      p.type === "subagent",
  );
}

/** Answer text shown in the agent-activity panel (excludes the main reply). */
export function panelAnswerForSection(section: SubagentSection): string {
  return isMainAnswerSubagent(section.subagentId, section.role)
    ? ""
    : section.answer;
}

export interface AgenticPanelLayout {
  renderedParts: GroupedToolPart[];
  firstSubagentIdx: number;
  nestInPanel: boolean;
  subagentIds: Set<string>;
  webSearchLayout: ReturnType<typeof partitionWebSearchGroups>;
  toolLayout: ToolGroupLayout;
}

export function buildAgenticPanelLayout(
  parts: readonly MessagePart[],
): AgenticPanelLayout {
  const renderedParts = groupToolParts([...parts]);
  const firstSubagentIdx = renderedParts.findIndex((p) => p.type === "subagent");
  const nestInPanel = firstSubagentIdx >= 0;
  const subagentSections = buildSubagentSectionsFromParts(parts);
  const subagentIds = new Set(
    subagentSections.map((section) => section.subagentId),
  );
  const webSearchLayout = partitionWebSearchGroups(
    renderedParts,
    subagentIds,
    nestInPanel,
  );
  const toolLayout = partitionToolGroups(
    renderedParts,
    subagentIds,
    nestInPanel,
  );
  return {
    renderedParts,
    firstSubagentIdx,
    nestInPanel,
    subagentIds,
    webSearchLayout,
    toolLayout,
  };
}

export function isNestedWebSearchGroup(
  part: GroupedToolPart,
  nestInPanel: boolean,
): boolean {
  return part.type === "web_search_group" && nestInPanel;
}

export function isNestedToolGroup(
  part: GroupedToolPart,
  nestInPanel: boolean,
): boolean {
  return part.type === "tool_group" && nestInPanel;
}
