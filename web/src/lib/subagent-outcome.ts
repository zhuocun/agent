// One validator for `SubagentOutcome` on both the live wire and the persisted
// parts. Framework-free so `agentic-layout.ts` (share view) and
// `stream-client.ts` (streaming thread) can share it.
//
// FE-9: the closed union matches api/app/schemas/common.py today, but an
// unrecognized value must not be laundered into `succeeded` — a green check for
// a state we cannot read is the one wrong answer. Degrade to the neutral
// `stopped` instead, and keep an ABSENT value absent so callers can still tell
// "no terminal reported" from "terminal we could not read".

import type { SubagentOutcome } from "@/lib/types";

export function readSubagentOutcome(
  value: unknown,
): SubagentOutcome | undefined {
  if (value === undefined || value === null) return undefined;
  if (
    value === "succeeded" ||
    value === "failed" ||
    value === "cancelled" ||
    value === "budget_cancelled" ||
    value === "stopped"
  ) {
    return value;
  }
  return "stopped";
}
