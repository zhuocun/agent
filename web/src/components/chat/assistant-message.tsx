"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Activity, AlertTriangle, Brain, CircleStop, Loader2, RotateCcw, SearchX } from "lucide-react";

import { ReasoningPanel } from "@/components/chat/reasoning-panel";
import {
  SourcesPanel,
  type SourcesPanelHandle,
} from "@/components/chat/sources-panel";
import { ToolPartView } from "@/components/chat/tool-part";
import { ToolGroupPanel } from "@/components/chat/tool-group-panel";
import { WebSearchPanel } from "@/components/chat/web-search-panel";
import {
  SubagentPanel,
  type SubagentSection,
} from "@/components/chat/subagent-panel";
import { MarkdownRenderer } from "@/components/chat/markdown-renderer";
import { AttributionRow } from "@/components/chat/attribution-row";
import { MessageActions } from "@/components/chat/message-actions";
import { FollowUpChips } from "@/components/chat/follow-up-chips";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { postModerationAppeal, type ApiError } from "@/lib/apiClient";
import type { RunCostState, SubagentActivity } from "@/lib/stream-client";
import {
  buildAgenticPanelLayout,
  buildMainSubagentIds,
  buildSubagentSectionsFromParts,
  isNestedToolGroup,
  isNestedWebSearchGroup,
} from "@/lib/agentic-layout";
import { cn } from "@/lib/utils";
import type {
  ChatMessage,
  Feedback,
  MessagePart,
  ModelTier,
  ModelTierId,
  ProviderTierOption,
  StreamStatus,
} from "@/lib/types";

interface AssistantMessageProps {
  message: ChatMessage;
  status: StreamStatus;
  reasoningStreaming?: boolean;
  canBranch?: boolean;
  isBranching?: boolean;
  canRegenerate?: boolean;
  canContinue?: boolean;
  // HITL: true only for the LAST assistant message whose status is
  // `awaiting_approval`. Gates the approve/deny controls so a stale paused
  // bubble higher in the thread never shows live decision buttons (mirrors the
  // `canContinue && isStopped` gating).
  isAwaitingApproval?: boolean;
  onBranch?: () => void;
  onRegenerate?: () => void;
  // Regenerate with a specific model/provider (Feature 4). Threaded straight to
  // MessageActions, which renders the split dropdown when both are present.
  onRegenerateWith?: (tierId: ModelTierId, providerId?: string) => void;
  regenerateOptions?: {
    tiers: ModelTier[];
    providerOptions: ProviderTierOption[];
    selectedTierId: ModelTierId;
  };
  onContinue?: () => void;
  // HITL: the user's approve/deny decision for the tool call this turn paused
  // on. Threaded down to the paused tool part's controls.
  onToolDecision?: (d: {
    toolCallId: string;
    decision: "approve" | "deny";
  }) => void;
  onFeedback?: (next: Feedback) => void;
  // Prefill the composer with a heuristic follow-up suggestion (T11). When
  // provided AND the turn finished cleanly, up to three chips render below the
  // answer; selecting one calls this (the text is never auto-sent).
  onFollowUp?: (text: string) => void;
  // Gate the follow-up chips to a single message (the trailing assistant turn)
  // so a long thread doesn't sprout chips under every answer.
  showFollowUps?: boolean;
  onAttributionOpen?: () => void;
  // Open the Memory manager (D19). Wired to the "Memory used here" chip that
  // appears when this turn injected saved facts.
  onMemoryOpen?: () => void;
  defaultReasoningOpen?: boolean;
  // Set only when `status === "error"` — the canonical ApiErrorEnvelope from
  // the terminal frame. Drives the inline chip + Details + Retry.
  error?: ApiError;
  // Agentic mode: live per-subagent activity for the STREAMING bubble, straight
  // from `ApiStreamState.subagents`. Carries accurate per-worker running/done
  // status mid-stream; committed/reloaded messages omit it and the panel
  // derives its sections from the persisted `subagent` marker + tagged parts.
  liveSubagents?: SubagentActivity[];
  // Agentic mode: live run-cost subtotal vs cap (the `run_cost` SSE event).
  // Streaming bubble only — the BE doesn't persist the cap, so committed
  // messages fall back to the summed per-subagent costs.
  runCost?: RunCostState | null;
}

// Length above which the error body collapses into an expandable Details
// disclosure. Short bodies sit inline next to the chip; longer bodies (full
// sentences, links, etc.) would dominate the message footer otherwise.
const ERROR_BODY_INLINE_MAX = 80;

// Calm, non-judgmental language for a SAFETY_BLOCKED turn. The BE envelope's
// `meta.source` says WHICH input tripped the rule; `meta.reasonCode` is the
// category. Never a silent/generic block — we always say the why.
function safetySourceLabel(source?: string): string {
  switch (source) {
    case "message":
      return "your message";
    case "attachment":
      return "an attachment";
    case "custom_instructions":
      return "your custom instructions";
    default:
      return "your input";
  }
}

function safetyReasonLabel(reasonCode?: string): string {
  switch (reasonCode) {
    case "configured_blocklist":
      return "matched a content safety rule";
    default:
      return reasonCode
        ? `matched a safety rule (${reasonCode})`
        : "matched a safety rule";
  }
}

function metaString(
  meta: Record<string, unknown> | undefined,
  key: string,
): string | undefined {
  const value = meta?.[key];
  return typeof value === "string" ? value : undefined;
}

export function AssistantMessage({
  message,
  status,
  reasoningStreaming,
  canBranch,
  isBranching,
  canRegenerate,
  canContinue,
  isAwaitingApproval,
  onBranch,
  onRegenerate,
  onRegenerateWith,
  regenerateOptions,
  onContinue,
  onToolDecision,
  onFeedback,
  onFollowUp,
  showFollowUps,
  onAttributionOpen,
  onMemoryOpen,
  defaultReasoningOpen = false,
  error,
  liveSubagents,
  runCost,
}: AssistantMessageProps) {
  // Agentic mode: per-subagent sections for the SubagentPanel. Live activity
  // (the streaming bubble) wins — it carries accurate running/done status;
  // otherwise derive from the persisted layout (`subagent` marker opens a
  // section, tagged reasoning/text fill it, status settles to "done").
  const subagentSections = useMemo<SubagentSection[]>(() => {
    if (liveSubagents && liveSubagents.length > 0) return liveSubagents;
    return buildSubagentSectionsFromParts(message.parts);
  }, [liveSubagents, message.parts]);

  const mainSubagentIds = useMemo(
    () => buildMainSubagentIds(message.parts),
    [message.parts],
  );

  const agenticLayout = useMemo(
    () => buildAgenticPanelLayout(message.parts),
    [message.parts],
  );
  const {
    renderedParts,
    firstSubagentIdx,
    nestInPanel: nestWebSearchInPanel,
    webSearchLayout,
    toolLayout,
  } = agenticLayout;

  const isNestedWebSearchGroupCb = useCallback(
    (group: (typeof renderedParts)[number]) =>
      isNestedWebSearchGroup(group, nestWebSearchInPanel),
    [nestWebSearchInPanel],
  );

  const isNestedToolGroupCb = useCallback(
    (group: (typeof renderedParts)[number]) =>
      isNestedToolGroup(group, nestWebSearchInPanel),
    [nestWebSearchInPanel],
  );

  const answerText = useMemo(
    () =>
      message.parts
        .filter(
          (p): p is Extract<MessagePart, { type: "text" }> =>
            p.type === "text" &&
            // Agentic turns: only the main (primary/aggregator) answer counts —
            // copying a message should yield the synthesis, not every worker's
            // intermediate finding.
            // Reloaded messages serialize untagged text with subagentId: null;
            // treat nullish the same as missing so answerText matches render.
            (p.subagentId == null || mainSubagentIds.has(p.subagentId)),
        )
        .map((p) => p.text)
        .join("\n\n"),
    [message.parts, mainSubagentIds],
  );

  // Source list for this message (if any) drives the inline `[n]` citation
  // chips inside the answer markdown. Inline markers reveal the matching card
  // via the SourcesPanel's imperative handle.
  const sourceItems = useMemo(
    () =>
      message.parts.find(
        (p): p is Extract<MessagePart, { type: "sources" }> =>
          p.type === "sources",
      )?.items ?? [],
    [message.parts],
  );
  const sourcesPanelRef = useRef<SourcesPanelHandle>(null);

  const hasContent = message.parts.some(
    (p) =>
      ((p.type === "text" || p.type === "reasoning") && p.text.length > 0) ||
      // A subagent marker means orchestration activity is on screen (the
      // panel), so the typing indicator should yield even before any tagged
      // text lands.
      p.type === "subagent",
  );

  // Defensive fallback trigger: an agentic/tool turn can settle with tool runs
  // and/or subagent activity on screen but no written answer text (the model
  // stopped after the last tool round without emitting a synthesis). Rather
  // than leave the bubble looking blank below the panels, surface a calm note
  // so the turn still reads as finished. Only counts main-body text — a turn
  // whose only text lives inside subagent worker rows still has no top-level
  // answer.
  const hasToolOrSubagentActivity = message.parts.some(
    (p) =>
      p.type === "tool_call" ||
      p.type === "tool_result" ||
      p.type === "subagent",
  );
  const showTyping = status === "submitted" || (status === "streaming" && !hasContent);
  const isDone = status === "done";
  const isStopped = status === "stopped";
  const isErrored = status === "error";
  // Final-as-in-non-streaming: done | stopped | error all surface footer
  // controls (actions for done/stopped, Retry for error). aria-busy still
  // tracks the same set so AT users hear the bubble settle on any terminal.
  const isFinal = isDone || isStopped || isErrored;

  // Tap-to-activate the message toolbar on touch surfaces. On hover-capable
  // pointers we leave the desktop hover idiom alone (group-hover/msg reveals
  // the toolbar), so the click handler is a no-op there to keep the existing
  // behavior pixel-identical for desktop and avoid sticky-after-hover UX.
  // Per-message local state keeps the wiring contained: tapping a different
  // bubble simply activates that one without coordinating with siblings.
  const [active, setActive] = useState(false);
  const handleToggleActive = useCallback((e: React.MouseEvent) => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    if (!window.matchMedia("(hover: none)").matches) return;
    const target = e.target as HTMLElement | null;
    // Ignore taps that land on interactive children (toolbar buttons, links,
    // tool-call controls, the dropdown trigger). Those run their own handler
    // and shouldn't double-toggle the toolbar's visibility.
    if (
      target?.closest(
        "button, a, [role='button'], [role='menuitem'], [role='menuitemcheckbox'], textarea, input, select, [contenteditable='true']",
      )
    ) {
      return;
    }
    setActive((v) => !v);
  }, []);

  return (
    <div
      className="group/msg space-y-3 break-words text-foreground"
      role="article"
      aria-label="Assistant"
      aria-busy={!isFinal}
      // E2E target: a stable hook for the assistant bubble so streaming
      // tests can `locator('[data-testid="assistant-message"]').last()` for
      // the in-flight turn without depending on the aria-label.
      data-testid="assistant-message"
      data-status={status}
      data-active={active ? "true" : undefined}
      onClick={handleToggleActive}
    >
      {showTyping ? <TypingIndicator /> : null}

      {renderedParts.map((part, idx) => {
        if (part.type === "web_search_group") {
          if (isNestedWebSearchGroupCb(part)) return null;
          return (
            <WebSearchPanel
              key={idx}
              group={part}
              onDecision={isAwaitingApproval ? onToolDecision : undefined}
            />
          );
        }
        if (part.type === "tool_group") {
          // When the agentic panel exists, settled generic tool groups nest
          // inside it (see `toolLayout`); skip the standalone render here,
          // mirroring `isNestedWebSearchGroup`.
          if (isNestedToolGroupCb(part)) return null;
          return (
            <ToolGroupPanel
              key={idx}
              group={part}
              // Uniform with the flat path: a group only ever holds settled
              // runs, so the gated handler never actually surfaces approve/deny
              // controls — but forward it so the renderer stays symmetric.
              onDecision={isAwaitingApproval ? onToolDecision : undefined}
            />
          );
        }
        if (part.type === "subagent") {
          // The panel covers ALL sections; render it once at the first marker.
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
              onToolDecision={isAwaitingApproval ? onToolDecision : undefined}
            />
          ) : null;
        }
        if (part.type === "reasoning") {
          // Subagent-tagged reasoning lives inside the panel's per-worker rows;
          // the global reasoning panel renders untagged reasoning only.
          if (part.subagentId) return null;
          return (
            <ReasoningPanel
              key={idx}
              text={part.text}
              durationSec={part.durationSec}
              isStreaming={!!reasoningStreaming}
              defaultOpen={defaultReasoningOpen}
            />
          );
        }
        if (part.type === "text") {
          // Subagent-tagged text: only the main (primary/aggregator) answer
          // renders as the markdown body; worker text stays panel-only.
          if (part.subagentId != null && !mainSubagentIds.has(part.subagentId)) {
            return null;
          }
          return part.text ? (
            <div key={idx} data-testid="assistant-answer">
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
        if (part.type === "status") {
          return <StatusLine key={idx} label={part.label} state={part.state} />;
        }
        if (part.type === "sources") {
          // Rendered AFTER the answer text (the part ordering — text then
          // sources — is established upstream in chat-thread.tsx). Honesty rule
          // (PRD 07 §4.3): an empty list with `requested` is the ungrounded
          // state — show the calm "Answered without live sources" chip instead
          // of an (empty) sources panel. A non-requested empty list renders
          // nothing (SourcesPanel already no-ops on empty).
          if (part.items.length === 0) {
            return part.requested ? <UngroundedMarker key={idx} /> : null;
          }
          return (
            <SourcesPanel key={idx} ref={sourcesPanelRef} items={part.items} />
          );
        }
        if (part.type === "tool_call" || part.type === "tool_result") {
          // A subagent-tagged lone settled run was folded into a single-run
          // group nested in the panel (`toolLayout.nestedParts`); skip its flat
          // render so it doesn't double up. Untagged lone runs aren't in the set
          // and still render in place.
          if (toolLayout.nestedParts.has(part)) return null;
          return (
            <ToolPartView
              key={idx}
              part={part}
              // Only the trailing paused turn gets live approve/deny controls;
              // ToolPartView further narrows to the pending tool_call part.
              onDecision={isAwaitingApproval ? onToolDecision : undefined}
            />
          );
        }
        return null;
      })}

      {isDone && hasToolOrSubagentActivity && !answerText.trim() ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="assistant-empty-fallback"
        >
          Finished without a written reply.
        </p>
      ) : null}

      {isErrored ? (
        <ErrorFooter error={error} onRetry={onRegenerate} />
      ) : null}

      {isFinal && !isErrored ? (
        <div className="space-y-2 pt-1">
          {message.attribution || isStopped ? (
            // Unified footer byline (W4): the always-visible attribution summary
            // (model + cost) and the MemoryUsed / Stopped indicators all share
            // ONE row and ONE grammar — glyph + muted text, no filled chrome.
            // Previously the chips were filled pills sitting next to a bare
            // typographic byline (two visual grammars); now they read as further
            // clauses of the same line. The attribution model+cost summary itself
            // is untouched and stays always-visible — only the chips around it
            // changed styling/placement.
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {message.attribution ? (
                <AttributionRow
                  attribution={message.attribution}
                  onOpen={onAttributionOpen}
                />
              ) : null}
              {message.attribution?.memoryApplied ? (
                <MemoryUsedChip
                  count={message.attribution.memoryApplied}
                  onOpen={onMemoryOpen}
                />
              ) : null}
              {isStopped ? <StoppedChip /> : null}
            </div>
          ) : null}
          {/* iOS-native progressive disclosure: the toolbar is hidden at rest
              on every pointer (no more permanently-painted 5-icon strip on
              touch). It reveals on focus-within (keyboard), on hover (desktop
              mouse), or when the message is tapped active (touch). Kept as
              an opacity-only transition — pointer-events stay auto so the
              overflow button remains hit-testable by Playwright without a
              prior synthetic hover, matching the desktop pattern before this
              redesign. */}
          <div className="flex flex-wrap items-center gap-2 opacity-0 transition-opacity focus-within:opacity-100 group-hover/msg:opacity-100 group-data-[active=true]/msg:opacity-100">
            <MessageActions
              text={answerText}
              feedback={message.feedback ?? null}
              canBranch={canBranch}
              isBranching={isBranching}
              canRegenerate={canRegenerate}
              canContinue={canContinue && isStopped}
              onBranch={onBranch}
              onRegenerate={onRegenerate}
              onRegenerateWith={onRegenerateWith}
              regenerateOptions={regenerateOptions}
              onContinue={onContinue}
              onFeedback={onFeedback}
            />
          </div>
          {/* Heuristic follow-up chips (T11): only on the trailing, cleanly
              finished turn so a long thread doesn't sprout suggestions under
              every answer. Stopped/errored turns are excluded — they aren't a
              settled answer to follow up on. */}
          {isDone && showFollowUps && onFollowUp && answerText.trim() ? (
            <FollowUpChips text={answerText} onSelect={onFollowUp} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** BE keeps the same label for active/done; the FE renders finished wording. */
export function formatStatusLabel(
  label: string,
  state: "active" | "done",
): string {
  if (state !== "done") return label;
  if (label === "Searching the web…") return "Searched the web";
  return label;
}

function StatusLine({ label, state }: { label: string; state: "active" | "done" }) {
  return (
    <div className="flex items-center gap-2 text-sm text-status-line">
      {state === "active" ? (
        <Loader2 className="size-3.5 motion-safe:animate-spin" aria-hidden />
      ) : null}
      <span>{formatStatusLabel(label, state)}</span>
    </div>
  );
}

// Honesty marker for an ungrounded web-search turn (PRD 07 §4.3): web search
// was requested but resolved zero usable sources. Calm and informational — NOT
// an error — so an ungrounded answer never gets to look cited.
function UngroundedMarker() {
  return (
    <div
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
      data-testid="ungrounded-marker"
    >
      <SearchX aria-hidden className="size-3.5" />
      <span>Answered without live sources</span>
    </div>
  );
}

// "Stopped" indicator: shown when a turn was halted before it finished. Rendered
// INLINE (CircleStop glyph + muted text, no filled background) so it joins the
// SAME byline grammar as the attribution clauses (attribution-row.tsx) and the
// MemoryUsedChip — the footer carries zero filled chrome at rest, instead of
// mixing a bare typographic byline with a lone filled pill (the two-grammars
// regression W4 set out to fix). testid preserved.
function StoppedChip() {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-muted-foreground/80"
      data-testid="stopped-chip"
    >
      <CircleStop aria-hidden className="size-3" />
      <span>Stopped</span>
    </span>
  );
}

// "Memory used here" indicator (D19): shown when this turn injected saved facts.
// Turn-level (not per-fact) attribution is the v1 scope. Clicking opens the
// Memory manager so the user can review/edit exactly what the assistant can see.
function MemoryUsedChip({
  count,
  onOpen,
}: {
  count: number;
  onOpen?: () => void;
}) {
  const label = `Memory used here · ${count} ${count === 1 ? "fact" : "facts"}`;
  return (
    // Rendered INLINE (Brain glyph + muted text, no filled background) to match
    // the byline's BYOK/substitution/JSON clauses (attribution-row.tsx) so the
    // attribution row carries zero filled chrome at rest — a lone filled pill
    // next to a bare typographic byline was the regression to avoid. Stays a
    // <button> with its onClick/onOpen open contract, keyboard operability, and
    // testid intact.
    <button
      type="button"
      onClick={onOpen}
      aria-label={`${label}. Open memory manager.`}
      data-testid="memory-used-chip"
      className={cn(
        "inline-flex items-center gap-1 text-xs text-muted-foreground/80",
        "outline-none transition-colors hover:text-foreground",
        "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
      )}
    >
      <Brain aria-hidden className="size-3" />
      <span>Memory used here</span>
    </button>
  );
}

function ErrorFooter({
  error,
  onRetry,
}: {
  error?: ApiError;
  onRetry?: () => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  // PRD 08 §3 fallback: when the envelope is absent (shouldn't happen — the
  // terminal handler always synthesizes one), keep a calm, non-empty surface
  // so the bubble still reads as "this errored" rather than going silent.
  const title = error?.title ?? "Message couldn't finish";
  const body = error?.body ?? "";
  // Anti-pattern A: destructive red is reserved for data-loss class errors.
  // ErrorSeverity = "info" | "warning" | "error" | "fatal" (apiClient.ts);
  // only "fatal" maps to the destructive token. Everything else — including
  // the common stream/network "error" severity — uses the warning role so
  // the chip reads as "couldn't finish", not "something is broken".
  const isDestructive = error?.severity === "fatal";
  const hasLongBody = body.length > ERROR_BODY_INLINE_MAX;
  const hasShortBody = body.length > 0 && !hasLongBody;

  // Rate-limit (429) cooldown: when the envelope carries `retryAfterMs`,
  // disable Retry and count down so the user can't immediately re-fire and
  // 429 again. `secondsLeft` ticks to 0, then Retry re-enables. When
  // `retryAfterMs` is absent, the countdown is inert and Retry stays generic.
  const retryAfterMs = error?.retryAfterMs;
  // Derive a fixed deadline from the first render that carries this envelope
  // (error is set once per errored turn, so retryAfterMs is stable per mount).
  // The effect then only ever calls setState inside the interval callback —
  // not synchronously in the effect body — to satisfy the repo's
  // react-hooks/set-state-in-effect lint (see share-dialog.tsx note).
  const [deadline] = useState(() =>
    retryAfterMs && retryAfterMs > 0 ? Date.now() + retryAfterMs : 0,
  );
  const secondsFromDeadline = () =>
    deadline > 0 ? Math.max(0, Math.ceil((deadline - Date.now()) / 1000)) : 0;
  const [secondsLeft, setSecondsLeft] = useState(secondsFromDeadline);

  useEffect(() => {
    if (deadline <= 0) return;
    const id = window.setInterval(() => {
      const next = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setSecondsLeft(next);
      if (next <= 0) window.clearInterval(id);
    }, 1000);
    return () => window.clearInterval(id);
  }, [deadline]);

  const retryDisabled = secondsLeft > 0;

  // SAFETY_BLOCKED: surface the WHY (category + which input) in calm language
  // and offer a request-review action. Mapped from the error envelope's meta.
  const isSafetyBlocked = error?.code === "SAFETY_BLOCKED";
  // PROVIDER_UPSTREAM is a platform/provider-side failure, so offer a quiet
  // link to the public status page where the user can see if it's a known
  // incident (PRD 08 §10). Calm, non-blocking — sits beside Retry.
  const isProviderError = error?.code === "PROVIDER_UPSTREAM";
  const safetyReasonCode = metaString(error?.meta, "reasonCode");
  const safetySource = metaString(error?.meta, "source");
  const [appealStatus, setAppealStatus] = useState<
    "idle" | "pending" | "done" | "error"
  >("idle");

  const requestReview = async (): Promise<void> => {
    if (appealStatus === "pending" || appealStatus === "done") return;
    setAppealStatus("pending");
    try {
      await postModerationAppeal({
        reasonCode: safetyReasonCode,
        source: safetySource,
      });
      setAppealStatus("done");
    } catch {
      setAppealStatus("error");
    }
  };

  return (
    <div className="space-y-2 pt-1" data-testid="assistant-error">
      <div className="flex flex-wrap items-center gap-2">
        <span
          role="status"
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs",
            isDestructive
              ? "border-destructive/30 bg-destructive/10 text-destructive"
              : "border-warning-foreground/20 bg-warning text-warning-foreground",
          )}
        >
          <AlertTriangle aria-hidden className="size-3.5" />
          <span>{title}</span>
        </span>
        {hasShortBody ? (
          <span className="text-xs text-muted-foreground">{body}</span>
        ) : null}
        {onRetry ? (
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                if (retryDisabled) return;
                onRetry();
              }}
              aria-disabled={retryDisabled}
              className="min-h-11 rounded-full px-4 md:min-h-0 aria-disabled:pointer-events-none aria-disabled:opacity-50"
              data-testid="assistant-error-retry"
            >
              <RotateCcw aria-hidden />
              <span>
                {retryDisabled ? `Try again in ${secondsLeft}s` : "Retry"}
              </span>
            </Button>
            {retryDisabled ? (
              <span className="sr-only" role="status" aria-live="polite">
                Try again in {secondsLeft} seconds
              </span>
            ) : null}
          </>
        ) : null}
        {isProviderError ? (
          <Button
            nativeButton={false}
            render={<Link href="/status" />}
            variant="ghost"
            size="sm"
            className="min-h-11 rounded-full px-4 md:min-h-0"
            data-testid="assistant-error-status"
          >
            <Activity aria-hidden />
            <span>Check status</span>
          </Button>
        ) : null}
      </div>
      {isSafetyBlocked ? (
        <div
          className="space-y-2 rounded-xl border border-warning-foreground/20 bg-warning/40 px-3 py-2"
          data-testid="safety-blocked-detail"
        >
          <p className="text-xs leading-snug text-warning-foreground">
            We couldn&apos;t send this because {safetySourceLabel(safetySource)}{" "}
            {safetyReasonLabel(safetyReasonCode)}. You can edit and try again, or
            ask us to review this decision.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {appealStatus === "done" ? (
              <p
                role="status"
                className="text-xs text-muted-foreground"
                data-testid="safety-appeal-confirmation"
              >
                Thanks — we&apos;ll review this block.
              </p>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void requestReview()}
                disabled={appealStatus === "pending"}
                className="min-h-11 rounded-full px-4 md:min-h-0"
                data-testid="safety-request-review"
              >
                {appealStatus === "pending" ? "Sending…" : "Request review"}
              </Button>
            )}
            {appealStatus === "error" ? (
              <p role="alert" className="text-xs text-destructive">
                Couldn&apos;t send your request. Please try again.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
      {hasLongBody ? (
        <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
          <CollapsibleTrigger
            render={
              <button
                type="button"
                className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                {detailsOpen ? "Hide details" : "Details"}
              </button>
            }
          />
          <CollapsibleContent className="pt-2 text-xs text-muted-foreground">
            {body}
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </div>
  );
}
