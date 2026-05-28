import type { ReasoningEffort, ReasoningEffortId } from "@/lib/types";

// Reasoning-effort options shown in the composer toggle (PRD 01 §4.2 line 78).
// The dropdown surfaces costHint / latencyHint as visible chips so a "max
// reasoning" pick can't be made without seeing the trade-off.
export const REASONING_EFFORTS: ReasoningEffort[] = [
  {
    id: "auto",
    label: "Auto",
    description: "App picks based on the prompt",
    costHint: "auto",
    latencyHint: "auto",
  },
  {
    id: "minimal",
    label: "Minimal",
    description: "Fastest, no extended thinking",
    costHint: "lowest",
    latencyHint: "fastest",
  },
  {
    id: "standard",
    label: "Standard",
    description: "Balanced reasoning depth",
    costHint: "medium",
    latencyHint: "balanced",
  },
  {
    id: "extended",
    label: "Extended",
    description: "Deeper thinking, slower, higher cost",
    costHint: "high",
    latencyHint: "slow",
  },
];

export const REASONING_EFFORTS_BY_ID: Record<ReasoningEffortId, ReasoningEffort> =
  Object.fromEntries(REASONING_EFFORTS.map((e) => [e.id, e])) as Record<
    ReasoningEffortId,
    ReasoningEffort
  >;
