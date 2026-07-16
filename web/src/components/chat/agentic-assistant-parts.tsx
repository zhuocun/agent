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
  collectGlobalSourceItems,
  deriveAgenticRunSummary,
  deriveRunCostFromParts,
  hasToolOrSubagentActivity,
  isNestedToolGroup,
  isNestedWebSearchGroup,
  resolveMainBubbleText,
  resolveSourcesForTextPart,
  shouldRenderTextInMainBubble,
  shouldShowSourcesInMainPanel,
} from "@/lib/agentic-layout";
import type { MessagePart } from "@/lib/types";
import { AlertTriangle } from "lucide-react";

export function AgenticAssistantParts({
  parts,
  sourcesPanelRef,
  answerTestId = "assistant-answer",
  showEmptyFallback = false,
}: {
  parts: readonly MessagePart[];
  sourcesPanelRef: RefObject<SourcesPanelHandle | null>;
  /** @deprecated Unused — citations resolve via resolveSourcesForTextPart. */
  sourceItems?: Extract<MessagePart, { type: "sources" }>["items"];
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
  const runCost = deriveRunCostFromParts(parts);
  const partialSummary = deriveAgenticRunSummary(parts);
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
      {partialSummary ? (
        <p
          role="status"
          data-testid="partial-synthesis-warning"
          className="mb-2 inline-flex max-w-full items-center gap-1.5 rounded-full border border-warning-foreground/20 bg-warning px-2.5 py-1 ui-caption text-warning-foreground"
        >
          <AlertTriangle aria-hidden className="size-3.5 shrink-0" />
          {partialSummary.budgetHalted
            ? "Partial answer — stopped early to stay within the run budget."
            : partialSummary.failedWorkers > 0
              ? `Partial answer — ${partialSummary.failedWorkers} worker${
                  partialSummary.failedWorkers === 1 ? "" : "s"
                } failed.`
              : "Partial answer — some research steps did not finish."}
        </p>
      ) : null}
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
              runCost={runCost}
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
          const textSources = resolveSourcesForTextPart(parts, part);
          return part.text ? (
            <div key={idx} data-testid={answerTestId}>
              <MarkdownRenderer
                sources={textSources}
                onCitationClick={(id) =>
                  sourcesPanelRef.current?.revealSource(id)
                }
              >
                {part.text}
              </MarkdownRenderer>
            </div>
          ) : null;
        }
        if (part.type === "status") {
          if (part.subagentId) return null;
          return null;
        }
        if (part.type === "sources") {
          // B12: show untagged OR main-answer (primary/aggregator) sources —
          // not the first worker's sources part.
          if (!shouldShowSourcesInMainPanel(part, subagentRoleById)) {
            return null;
          }
          if (part.items.length === 0) return null;
          return (
            <SourcesPanel key={idx} ref={sourcesPanelRef} items={part.items} />
          );
        }
        if (part.type === "tool_call" || part.type === "tool_result") {
          if (toolLayout.nestedParts.has(part)) return null;
          return <ToolPartView key={idx} part={part} />;
        }
        if (part.type === "agentic_run_summary" || part.type === "attachment") {
          return null;
        }
        return null;
      })}
      {showEmptyReplyFallback ? (
        <p
          className="ui-body text-muted-foreground"
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
  const subagentRoleById = useMemo(() => buildSubagentRoleById(parts), [parts]);
  // Prefer main-answer / untagged sources; else merge all by global id (B12).
  const sourceItems = useMemo(() => {
    const main = parts.find(
      (p): p is Extract<MessagePart, { type: "sources" }> =>
        p.type === "sources" && shouldShowSourcesInMainPanel(p, subagentRoleById),
    );
    if (main && main.items.length > 0) return main.items;
    return collectGlobalSourceItems(parts);
  }, [parts, subagentRoleById]);
  return { sourcesPanelRef, sourceItems };
}
