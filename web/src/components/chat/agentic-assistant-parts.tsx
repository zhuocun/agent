"use client";

import { useMemo, useRef, type RefObject } from "react";

import { MarkdownRenderer } from "@/components/chat/markdown-renderer";
import { ReasoningPanel } from "@/components/chat/reasoning-panel";
import {
  SourcesPanel,
  type SourcesPanelHandle,
} from "@/components/chat/sources-panel";
import { SubagentPanel } from "@/components/chat/subagent-panel";
import { ToolGroupPanel } from "@/components/chat/tool-group-panel";
import { WebSearchPanel } from "@/components/chat/web-search-panel";
import { ToolPartView } from "@/components/chat/tool-part";
import {
  buildAgenticPanelLayout,
  buildSubagentRoleById,
  buildSubagentSectionsFromParts,
  hasToolOrSubagentActivity,
  isNestedToolGroup,
  isNestedWebSearchGroup,
  resolveMainBubbleText,
  shouldRenderTextInMainBubble,
} from "@/lib/agentic-layout";
import type { MessagePart } from "@/lib/types";

export function AgenticAssistantParts({
  parts,
  sourcesPanelRef,
  sourceItems,
  answerTestId = "assistant-answer",
  showEmptyFallback = false,
}: {
  parts: readonly MessagePart[];
  sourcesPanelRef: RefObject<SourcesPanelHandle | null>;
  sourceItems: Extract<MessagePart, { type: "sources" }>["items"];
  answerTestId?: string;
  /** When true, show the calm empty-reply note on tool/subagent turns with no main answer. */
  showEmptyFallback?: boolean;
}) {
  const layout = buildAgenticPanelLayout(parts);
  const {
    renderedParts,
    firstSubagentIdx,
    nestInPanel,
    webSearchLayout,
    toolLayout,
  } = layout;
  const subagentSections = buildSubagentSectionsFromParts(parts);
  const subagentRoleById = useMemo(() => buildSubagentRoleById(parts), [parts]);
  const { effectiveAnswerText } = useMemo(
    () => resolveMainBubbleText(parts),
    [parts],
  );
  const showEmptyReplyFallback =
    showEmptyFallback &&
    hasToolOrSubagentActivity(parts) &&
    !effectiveAnswerText.trim();

  return (
    <>
      {renderedParts.map((part, idx) => {
        if (part.type === "web_search_group") {
          if (isNestedWebSearchGroup(part, nestInPanel)) return null;
          return <WebSearchPanel key={idx} group={part} />;
        }
        if (part.type === "tool_group") {
          if (isNestedToolGroup(part, nestInPanel)) return null;
          return <ToolGroupPanel key={idx} group={part} />;
        }
        if (part.type === "subagent") {
          return idx === firstSubagentIdx ? (
            <SubagentPanel
              key={idx}
              sections={subagentSections}
              panelWebSearchGroups={webSearchLayout.panelLevel}
              webSearchBySubagentId={webSearchLayout.bySubagentId}
              panelToolGroups={toolLayout.panelLevel}
              toolGroupsBySubagentId={toolLayout.bySubagentId}
              panelLiveToolParts={toolLayout.panelLevelLiveToolParts}
              liveToolPartsBySubagentId={toolLayout.liveToolPartsBySubagentId}
            />
          ) : null;
        }
        if (part.type === "reasoning") {
          if (part.subagentId) return null;
          return (
            <ReasoningPanel
              key={idx}
              text={part.text}
              durationSec={part.durationSec}
              isStreaming={false}
            />
          );
        }
        if (part.type === "text") {
          if (
            part.subagentId != null &&
            !shouldRenderTextInMainBubble(part, subagentRoleById)
          ) {
            return null;
          }
          return part.text ? (
            <div key={idx} data-testid={answerTestId}>
              <MarkdownRenderer
                sources={sourceItems}
                onCitationClick={(id) =>
                  sourcesPanelRef.current?.revealSource(id)
                }
              >
                {part.text}
              </MarkdownRenderer>
            </div>
          ) : null;
        }
        if (part.type === "sources") {
          if (part.items.length === 0) return null;
          return (
            <SourcesPanel key={idx} ref={sourcesPanelRef} items={part.items} />
          );
        }
        if (part.type === "tool_call" || part.type === "tool_result") {
          if (toolLayout.nestedParts.has(part)) return null;
          return <ToolPartView key={idx} part={part} />;
        }
        return null;
      })}
      {showEmptyReplyFallback ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="assistant-empty-fallback"
        >
          Finished without a written reply.
        </p>
      ) : null}
    </>
  );
}

export function useSourcesFromParts(parts: readonly MessagePart[]) {
  const sourcesPanelRef = useRef<SourcesPanelHandle>(null);
  const sourceItems =
    parts.find((p): p is Extract<MessagePart, { type: "sources" }> =>
      p.type === "sources",
    )?.items ?? [];
  return { sourcesPanelRef, sourceItems };
}
