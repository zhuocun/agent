// Pure grouping model for the tool-call aggregation redesign.
//
// Folds contiguous spans of *settled* tool runs into a single `ToolGroup` so a
// long agentic transcript doesn't render as a wall of identical tool cards.
// Framework-free by design (no React imports): the presentational panel
// (`tool-group-panel.tsx`) and any future consumer derive their layout from the
// shape returned here, and the rules below are unit-testable in isolation.
//
// Rules (see W1 brief):
//  1. Only aggregate SETTLED runs (`succeeded` / `failed` / `cancelled`). Live
//     runs (`running` / `awaiting_approval` / `pending`) and the
//     `agentic_plan_approval` pseudo-tool render standalone (passthrough).
//  2. Threshold of >=2 runs: a lone settled run renders flat (unchanged); a
//     panel only forms at 2+.
//  3. Group boundary = adjacency: a maximal contiguous span of groupable tool
//     parts. Any non-tool part or live/plan-approval tool breaks the run, and a
//     `subagentId` change also breaks it.
//  4. Pair `tool_call` <-> `tool_result` by id / `toolCallId`.

import type { MessagePart, ToolRunStatus } from "@/lib/types";

type ToolCallPart = Extract<MessagePart, { type: "tool_call" }>;
type ToolResultPart = Extract<MessagePart, { type: "tool_result" }>;

// The agentic orchestrator's plan-approval pause rides a PSEUDO tool call with
// this name (api/app/agentic/orchestrator.py PLAN_APPROVAL_TOOL_NAME). It is a
// user-facing gate, never a generic settled tool — keep it out of any group so
// it always renders standalone (mirrors tool-part.tsx's special-casing).
const PLAN_APPROVAL_TOOL_NAME = "agentic_plan_approval";

// Terminal (settled) tool-run statuses. Everything else is "live".
const TERMINAL_STATUSES: ReadonlySet<ToolRunStatus> = new Set([
  "succeeded",
  "failed",
  "cancelled",
]);

// A single tool invocation: a `tool_call` paired with its `tool_result` by id.
// Either side may be absent (a settled call with no separate result part, or a
// stray result), but at least one is always present.
export interface ToolRun {
  // The call id / result `toolCallId` the pair shares.
  id: string;
  // Human/source tool name (e.g. "web_search"); used for the per-name counts.
  name: string;
  // The run's terminal status: the result's status when present, else the
  // call's. Always one of the TERMINAL_STATUSES for a run inside a group.
  status: ToolRunStatus;
  call?: ToolCallPart;
  result?: ToolResultPart;
}

// A folded run of >=2 contiguous settled tool invocations. Carries the member
// runs plus a few derived summaries the panel renders without re-walking:
//  - `counts`: per-name run counts (e.g. `{ web_search: 2, fetch_url: 1 }`)
//  - `failedCount`: how many runs failed
//  - `status`: the group's terminal verdict (failed > cancelled > succeeded)
// `type: "tool_group"` is the discriminant that distinguishes a group from a
// passthrough `MessagePart` in the returned array.
export interface ToolGroup {
  type: "tool_group";
  runs: ToolRun[];
  counts: Record<string, number>;
  failedCount: number;
  status: ToolRunStatus;
  // Inherited from the span's parts (all share one value — a change breaks the
  // span). Absent for non-agentic turns.
  subagentId?: string;
}

// Default status for a bare part, mirroring tool-part.tsx: a `tool_result` with
// no explicit status is treated as succeeded; a `tool_call` defaults to pending
// (so an un-statused call reads as live and stays standalone).
function effectiveStatus(part: ToolCallPart | ToolResultPart): ToolRunStatus {
  return part.status ?? (part.type === "tool_result" ? "succeeded" : "pending");
}

// A part is groupable iff it is a settled tool part that is not the
// plan-approval pseudo-tool.
function isGroupablePart(
  part: MessagePart,
): part is ToolCallPart | ToolResultPart {
  if (part.type !== "tool_call" && part.type !== "tool_result") return false;
  if (part.name === PLAN_APPROVAL_TOOL_NAME) return false;
  return TERMINAL_STATUSES.has(effectiveStatus(part));
}

function runStatus(run: ToolRun): ToolRunStatus {
  if (run.result) return effectiveStatus(run.result);
  if (run.call) return effectiveStatus(run.call);
  return "succeeded";
}

// Pair the parts of one contiguous span into runs, matching `tool_call.id` to
// `tool_result.toolCallId`. Preserves first-seen order: a run takes the
// position of whichever of its parts appeared first.
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
    // Prefer the call's declared name (the result echoes the same name); fall
    // back to the result when the run has no call part.
    run.name = run.call?.name ?? run.result?.name ?? run.name;
  }
  return runs;
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
  // Terminal verdict precedence: any failure dominates, then any cancellation,
  // else the whole group succeeded.
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

// Walk the parts list, folding each maximal contiguous span of groupable tool
// parts into a `ToolGroup` when it holds >=2 runs, and passing everything else
// (non-tool parts, live tools, plan-approval, and lone settled runs) through
// flat and in order.
export function groupToolParts(
  parts: MessagePart[],
): (MessagePart | ToolGroup)[] {
  const out: (MessagePart | ToolGroup)[] = [];
  let span: (ToolCallPart | ToolResultPart)[] = [];
  let spanSubagentId: string | undefined;

  const flush = () => {
    if (span.length === 0) return;
    const runs = pairRuns(span);
    if (runs.length >= 2) {
      out.push(buildGroup(runs, spanSubagentId));
    } else {
      for (const part of span) out.push(part);
    }
    span = [];
    spanSubagentId = undefined;
  };

  for (const part of parts) {
    if (isGroupablePart(part)) {
      // A subagent change breaks the current span before extending it.
      if (span.length > 0 && part.subagentId !== spanSubagentId) flush();
      if (span.length === 0) spanSubagentId = part.subagentId;
      span.push(part);
    } else {
      flush();
      out.push(part);
    }
  }
  flush();
  return out;
}
