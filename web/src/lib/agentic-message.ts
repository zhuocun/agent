// Shared derivation helpers for agentic (multi-agent) assistant turns. Both the
// private thread (`assistant-message.tsx`) and the public share view
// (`public-conversation-view.tsx`) reconstruct the same subagent-grouped layout
// from a persisted message's `subagent` marker parts + tagged reasoning/text,
// so the grouping logic lives here once rather than drifting between two copies.

import type { SubagentSection } from "@/components/chat/subagent-panel";
import type { MessagePart } from "@/lib/types";

// Subagents whose answer text is THE answer (rendered as the main markdown body
// rather than folded into the panel): `single` mode's primary and deep
// research's aggregator. Worker/orchestrator text stays panel-only.
export function getMainSubagentIds(parts: MessagePart[]): Set<string> {
  const ids = new Set<string>();
  for (const part of parts) {
    if (
      part.type === "subagent" &&
      (part.role === "primary" || part.role === "aggregator")
    ) {
      ids.add(part.subagentId);
    }
  }
  return ids;
}

// Rebuild the per-subagent sections from a persisted message: each `subagent`
// marker opens a section, its `subagentId`-tagged reasoning/text fill it, and
// the status settles to "done" (a reloaded transcript is never mid-stream).
//
// `includeCost` defaults to true; the share surface passes false so per-subagent
// spend never renders (PRD 07 §6.4 cost strip). Attribution is always carried —
// the panel reads only its model-identity / substitution fields, which the
// public contract keeps.
export function deriveSubagentSections(
  parts: MessagePart[],
  opts: { includeCost?: boolean } = {},
): SubagentSection[] {
  const includeCost = opts.includeCost ?? true;
  const sections: SubagentSection[] = [];
  const byId = new Map<string, SubagentSection>();
  for (const part of parts) {
    if (part.type === "subagent") {
      const section: SubagentSection = {
        subagentId: part.subagentId,
        label: part.label,
        role: part.role,
        status: "done",
        ...(includeCost && part.costUsd !== undefined
          ? { costUsd: part.costUsd }
          : {}),
        ...(part.attribution !== undefined
          ? { attribution: part.attribution }
          : {}),
        reasoning: "",
        answer: "",
      };
      byId.set(part.subagentId, section);
      sections.push(section);
      continue;
    }
    if ((part.type === "reasoning" || part.type === "text") && part.subagentId) {
      const section = byId.get(part.subagentId);
      if (!section) continue;
      if (part.type === "reasoning") section.reasoning += part.text;
      else section.answer += part.text;
    }
  }
  return sections;
}

// PRD 08 partial-synthesis marker. The agentic aggregator appends one (or more)
// `[Partial answer: …]` brackets to its synthesis on a graceful degrade (budget
// halt or per-worker failure — api/app/agentic/aggregate.py). The bracket never
// nests `]`, so a non-greedy character class matches each one (incl. any leading
// newlines the BE prepends) without over-eating real prose.
const PARTIAL_ANSWER_MARKER = /\n*\[Partial answer:[^\]]*\]/g;

export function hasPartialAnswerMarker(text: string): boolean {
  // Fresh, non-global test — the module-level regex carries `g`/`lastIndex`
  // state that would make a shared `.test()` alternate true/false across calls.
  return /\[Partial answer:/.test(text);
}

export function stripPartialAnswerMarker(text: string): string {
  return text.replace(PARTIAL_ANSWER_MARKER, "").trimEnd();
}
