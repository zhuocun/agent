// Pure grouping model for tool-call aggregation.
//
// Folds tool runs into panels so a long agentic transcript doesn't render as a
// wall of identical cards. Framework-free (no React imports).
//
// Group kinds:
//  - `web_search_group`: all `web_search` runs (settled or live) plus an
//    adjacent search status line fold into one section (threshold >=1).
//  - `tool_group`: contiguous spans of >=2 settled non-search tool runs.
//  - passthrough: lone settled non-search runs, plan-approval, and non-tool parts.

import type { MessagePart, ToolRunStatus } from "@/lib/types";

type ToolCallPart = Extract<MessagePart, { type: "tool_call" }>;
type ToolResultPart = Extract<MessagePart, { type: "tool_result" }>;
type StatusPart = Extract<MessagePart, { type: "status" }>;

export const WEB_SEARCH_TOOL_NAME = "web_search";

const PLAN_APPROVAL_TOOL_NAME = "agentic_plan_approval";

const TERMINAL_STATUSES: ReadonlySet<ToolRunStatus> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

export interface ToolRun {
  id: string;
  name: string;
  status: ToolRunStatus;
  call?: ToolCallPart;
  result?: ToolResultPart;
}

export interface ToolGroup {
  type: "tool_group";
  runs: ToolRun[];
  counts: Record<string, number>;
  failedCount: number;
  status: ToolRunStatus;
  subagentId?: string;
}

// Consolidated web-search activity: one or more `web_search` tool runs plus an
// optional absorbed status line ("Searching the web…" / "Searched the web").
export interface WebSearchGroup {
  type: "web_search_group";
  runs: ToolRun[];
  failedCount: number;
  status: ToolRunStatus;
  subagentId?: string;
  statusPart?: Pick<StatusPart, "label" | "state">;
}

export type GroupedToolPart = MessagePart | ToolGroup | WebSearchGroup;

function effectiveStatus(part: ToolCallPart | ToolResultPart): ToolRunStatus {
  return part.status ?? (part.type === "tool_result" ? "succeeded" : "pending");
}

function isSearchStatusPart(part: MessagePart): part is StatusPart {
  if (part.type !== "status") return false;
  // BE uses this label for web-search status lines (active → done).
  return part.label.startsWith("Searching the web");
}

function isGroupablePart(
  part: MessagePart,
): part is ToolCallPart | ToolResultPart {
  if (part.type !== "tool_call" && part.type !== "tool_result") return false;
  if (part.name === PLAN_APPROVAL_TOOL_NAME) return false;
  if (part.name === WEB_SEARCH_TOOL_NAME) return false;
  return TERMINAL_STATUSES.has(effectiveStatus(part));
}

function isLiveNestableToolPart(
  part: MessagePart,
): part is ToolCallPart | ToolResultPart {
  if (part.type !== "tool_call" && part.type !== "tool_result") return false;
  if (part.name === PLAN_APPROVAL_TOOL_NAME) return false;
  if (part.name === WEB_SEARCH_TOOL_NAME) return false;
  return !TERMINAL_STATUSES.has(effectiveStatus(part));
}

function runStatus(run: ToolRun): ToolRunStatus {
  if (run.result) return effectiveStatus(run.result);
  if (run.call) return effectiveStatus(run.call);
  return "succeeded";
}

function pairRuns(span: (ToolCallPart | ToolResultPart)[]): ToolRun[] {
  const runs: ToolRun[] = [];
  const byId = new Map<string, ToolRun>();

  for (const part of span) {
    if (part.type === "tool_call") {
      const existing = byId.get(part.id);
      if (existing && !existing.call) {
        existing.call = part;
        continue;
      }
      const run: ToolRun = {
        id: part.id,
        name: part.name,
        status: "succeeded",
        call: part,
      };
      runs.push(run);
      byId.set(part.id, run);
    } else {
      const existing = byId.get(part.toolCallId);
      if (existing && !existing.result) {
        existing.result = part;
        continue;
      }
      const run: ToolRun = {
        id: part.toolCallId,
        name: part.name,
        status: "succeeded",
        result: part,
      };
      runs.push(run);
      byId.set(part.toolCallId, run);
    }
  }

  for (const run of runs) {
    run.status = runStatus(run);
    run.name = run.call?.name ?? run.result?.name ?? run.name;
  }
  return runs;
}

function aggregateRunStatus(runs: ToolRun[]): ToolRunStatus {
  if (runs.some((run) => run.status === "failed")) return "failed";
  if (runs.some((run) => run.status === "cancelled")) return "cancelled";
  if (runs.some((run) => run.status === "running")) return "running";
  if (runs.some((run) => run.status === "awaiting_approval")) {
    return "awaiting_approval";
  }
  if (runs.some((run) => run.status === "pending")) return "pending";
  return "succeeded";
}

function buildGroup(
  runs: ToolRun[],
  subagentId: string | undefined,
): ToolGroup {
  const counts: Record<string, number> = {};
  let failedCount = 0;
  let hasCancelled = false;
  for (const run of runs) {
    counts[run.name] = (counts[run.name] ?? 0) + 1;
    if (run.status === "failed") failedCount += 1;
    if (run.status === "cancelled") hasCancelled = true;
  }
  const status: ToolRunStatus =
    failedCount > 0 ? "failed" : hasCancelled ? "cancelled" : "succeeded";
  return {
    type: "tool_group",
    runs,
    counts,
    failedCount,
    status,
    ...(subagentId !== undefined ? { subagentId } : {}),
  };
}

function buildWebSearchGroup(
  runs: ToolRun[],
  subagentId: string | undefined,
  statusPart: Pick<StatusPart, "label" | "state"> | undefined,
): WebSearchGroup {
  const failedCount = runs.filter((run) => run.status === "failed").length;
  return {
    type: "web_search_group",
    runs,
    failedCount,
    status: aggregateRunStatus(runs),
    ...(subagentId !== undefined ? { subagentId } : {}),
    ...(statusPart !== undefined ? { statusPart } : {}),
  };
}

function pushRunParts(out: GroupedToolPart[], run: ToolRun): void {
  if (run.call) out.push(run.call);
  if (run.result) out.push(run.result);
}

function flushGenericSpan(
  out: GroupedToolPart[],
  span: (ToolCallPart | ToolResultPart)[],
  spanSubagentId: string | undefined,
): void {
  if (span.length === 0) return;
  const runs = pairRuns(span);
  if (runs.length >= 2) {
    out.push(buildGroup(runs, spanSubagentId));
    return;
  }
  for (const run of runs) pushRunParts(out, run);
}

function flushWebSearchSpan(
  out: GroupedToolPart[],
  span: (ToolCallPart | ToolResultPart)[],
  spanSubagentId: string | undefined,
  statusPart: Pick<StatusPart, "label" | "state"> | undefined,
): void {
  if (span.length === 0) return;
  const runs = pairRuns(span);
  if (runs.length === 0) return;
  out.push(buildWebSearchGroup(runs, spanSubagentId, statusPart));
}

export function groupToolParts(parts: MessagePart[]): GroupedToolPart[] {
  const out: GroupedToolPart[] = [];
  let genericSpan: (ToolCallPart | ToolResultPart)[] = [];
  let genericSubagentId: string | undefined;
  let webSearchSpan: (ToolCallPart | ToolResultPart)[] = [];
  let webSearchSubagentId: string | undefined;
  let pendingSearchStatus: Pick<StatusPart, "label" | "state"> | undefined;

  const flushGeneric = () => {
    flushGenericSpan(out, genericSpan, genericSubagentId);
    genericSpan = [];
    genericSubagentId = undefined;
  };

  const flushWebSearch = () => {
    flushWebSearchSpan(out, webSearchSpan, webSearchSubagentId, pendingSearchStatus);
    webSearchSpan = [];
    webSearchSubagentId = undefined;
    pendingSearchStatus = undefined;
  };

  const flushAll = () => {
    flushGeneric();
    flushWebSearch();
  };

  for (const part of parts) {
    if (part.type === "tool_call" || part.type === "tool_result") {
      if (part.name === WEB_SEARCH_TOOL_NAME) {
        flushGeneric();
        if (
          webSearchSpan.length > 0 &&
          part.subagentId !== webSearchSubagentId
        ) {
          flushWebSearch();
        }
        if (webSearchSpan.length === 0) webSearchSubagentId = part.subagentId;
        webSearchSpan.push(part);
        continue;
      }

      if (isGroupablePart(part)) {
        flushWebSearch();
        if (genericSpan.length > 0 && part.subagentId !== genericSubagentId) {
          flushGeneric();
        }
        if (genericSpan.length === 0) genericSubagentId = part.subagentId;
        genericSpan.push(part);
        continue;
      }

      flushAll();
      out.push(part);
      continue;
    }

    if (isSearchStatusPart(part) && webSearchSpan.length > 0) {
      flushGeneric();
      pendingSearchStatus = { label: part.label, state: part.state };
      continue;
    }

    flushAll();
    out.push(part);
  }

  flushAll();
  return out;
}

/** Split web-search groups for agent-activity nesting vs standalone render. */
export function partitionWebSearchGroups(
  parts: GroupedToolPart[],
  subagentIds: ReadonlySet<string>,
  nestInPanel: boolean,
): {
  standalone: WebSearchGroup[];
  panelLevel: WebSearchGroup[];
  bySubagentId: Map<string, WebSearchGroup[]>;
} {
  const standalone: WebSearchGroup[] = [];
  const panelLevel: WebSearchGroup[] = [];
  const bySubagentId = new Map<string, WebSearchGroup[]>();

  for (const part of parts) {
    if (part.type !== "web_search_group") continue;
    if (!nestInPanel) {
      standalone.push(part);
      continue;
    }
    const ownerId = part.subagentId;
    if (ownerId !== undefined && subagentIds.has(ownerId)) {
      const owned = bySubagentId.get(ownerId) ?? [];
      owned.push(part);
      bySubagentId.set(ownerId, owned);
      continue;
    }
    panelLevel.push(part);
  }

  return { standalone, panelLevel, bySubagentId };
}

export interface ToolGroupLayout {
  // Real `tool_group` items when NOT nesting — render flat as before.
  standalone: ToolGroup[];
  // Nested groups not owned by a known subagent (untagged origin or an unknown
  // tag) — render inside the agent-activity card's panel-level slot.
  panelLevel: ToolGroup[];
  // Nested groups keyed by their owning subagent id — render inside that
  // worker's row, mirroring `webSearchBySubagentId`.
  bySubagentId: Map<string, ToolGroup[]>;
  // Live / awaiting generic tool parts owned by a subagent row — rendered as raw
  // `ToolPartView` rows (not folded into a collapsed ToolGroupPanel).
  liveToolPartsBySubagentId: Map<string, (ToolCallPart | ToolResultPart)[]>;
  // Untagged (or unknown-tag) live generic tool parts at panel level.
  panelLevelLiveToolParts: (ToolCallPart | ToolResultPart)[];
  // Passthrough + live tool parts nested in the panel — skip flat render.
  nestedParts: Set<MessagePart>;
}

/**
 * Split generic tool activity for agent-activity nesting vs standalone render —
 * the `tool_group` analogue of `partitionWebSearchGroups`.
 *
 * Two inputs feed the nest:
 *  - Real `tool_group` items (>=2 settled runs already folded by
 *    `groupToolParts`) route by `subagentId` exactly like web-search groups.
 *  - Lone settled tool runs that `groupToolParts` left as passthrough
 *    `tool_call` / `tool_result` parts. When such a run is subagent-TAGGED it's
 *    wrapped into a single-run `ToolGroup` so it nests too; its source parts are
 *    recorded in `nestedParts` for the render loop to skip. UNTAGGED lone runs
 *    are left untouched (they stay standalone, rendering flat in place).
 *
 * Live / awaiting-approval generic runs nest into the agent-activity panel as
 * raw `ToolPartView` rows when subagent-tagged (mirroring live web search).
 * `agentic_plan_approval` stays standalone. When `nestInPanel` is false nothing
 * nests — every real group is `standalone`.
 */
export function partitionToolGroups(
  parts: GroupedToolPart[],
  subagentIds: ReadonlySet<string>,
  nestInPanel: boolean,
): ToolGroupLayout {
  const standalone: ToolGroup[] = [];
  const panelLevel: ToolGroup[] = [];
  const bySubagentId = new Map<string, ToolGroup[]>();
  const liveToolPartsBySubagentId = new Map<
    string,
    (ToolCallPart | ToolResultPart)[]
  >();
  const panelLevelLiveToolParts: (ToolCallPart | ToolResultPart)[] = [];
  const nestedParts = new Set<MessagePart>();

  const route = (group: ToolGroup, ownerId: string | undefined): void => {
    if (ownerId !== undefined && subagentIds.has(ownerId)) {
      const owned = bySubagentId.get(ownerId) ?? [];
      owned.push(group);
      bySubagentId.set(ownerId, owned);
      return;
    }
    panelLevel.push(group);
  };

  // Lone settled tool parts left as passthrough by `groupToolParts`. Paired here
  // (call + result of one run) so a single tagged run folds into ONE group.
  const loneToolParts: (ToolCallPart | ToolResultPart)[] = [];

  for (const part of parts) {
    if (part.type === "tool_group") {
      if (!nestInPanel) {
        standalone.push(part);
        continue;
      }
      route(part, part.subagentId);
      continue;
    }
    if (
      nestInPanel &&
      (part.type === "tool_call" || part.type === "tool_result") &&
      isGroupablePart(part)
    ) {
      loneToolParts.push(part);
    }
  }

  for (const run of pairRuns(loneToolParts)) {
    const ownerId = run.call?.subagentId ?? run.result?.subagentId;
    // Untagged lone runs stay standalone — leave their parts to render flat.
    if (ownerId === undefined) continue;
    route(buildGroup([run], ownerId), ownerId);
    if (run.call) nestedParts.add(run.call);
    if (run.result) nestedParts.add(run.result);
  }

  if (nestInPanel) {
    for (const part of parts) {
      if (part.type !== "tool_call" && part.type !== "tool_result") continue;
      if (!isLiveNestableToolPart(part)) continue;
      nestedParts.add(part);
      const ownerId = part.subagentId;
      if (ownerId !== undefined && subagentIds.has(ownerId)) {
        const owned = liveToolPartsBySubagentId.get(ownerId) ?? [];
        owned.push(part);
        liveToolPartsBySubagentId.set(ownerId, owned);
        continue;
      }
      panelLevelLiveToolParts.push(part);
    }
  }

  return {
    standalone,
    panelLevel,
    bySubagentId,
    liveToolPartsBySubagentId,
    panelLevelLiveToolParts,
    nestedParts,
  };
}
