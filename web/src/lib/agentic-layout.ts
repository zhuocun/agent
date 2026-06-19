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
import type { MessagePart } from "@/lib/types";

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
        ...(part.costUsd !== undefined ? { costUsd: part.costUsd } : {}),
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

export function buildMainSubagentIds(parts: readonly MessagePart[]): Set<string> {
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
