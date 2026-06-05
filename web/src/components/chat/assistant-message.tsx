"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Loader2, RotateCcw, SearchX } from "lucide-react";

import { ReasoningPanel } from "@/components/chat/reasoning-panel";
import {
  SourcesPanel,
  type SourcesPanelHandle,
} from "@/components/chat/sources-panel";
import { ToolPartView } from "@/components/chat/tool-part";
import { MarkdownRenderer } from "@/components/chat/markdown-renderer";
import { AttributionRow } from "@/components/chat/attribution-row";
import { MessageActions } from "@/components/chat/message-actions";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ApiError } from "@/lib/apiClient";
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
  onAttributionOpen?: () => void;
  defaultReasoningOpen?: boolean;
  // Set only when `status === "error"` — the canonical ApiErrorEnvelope from
  // the terminal frame. Drives the inline chip + Details + Retry.
  error?: ApiError;
}

// Length above which the error body collapses into an expandable Details
// disclosure. Short bodies sit inline next to the chip; longer bodies (full
// sentences, links, etc.) would dominate the message footer otherwise.
const ERROR_BODY_INLINE_MAX = 80;

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
  onAttributionOpen,
  defaultReasoningOpen = false,
  error,
}: AssistantMessageProps) {
  const answerText = useMemo(
    () =>
      message.parts
        .filter((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
        .map((p) => p.text)
        .join("\n\n"),
    [message.parts],
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
    (p) => (p.type === "text" || p.type === "reasoning") && p.text.length > 0,
  );
  const showTyping = status === "submitted" || (status === "streaming" && !hasContent);
  const isDone = status === "done";
  const isStopped = status === "stopped";
  const isErrored = status === "error";
  // Final-as-in-non-streaming: done | stopped | error all surface footer
  // controls (actions for done/stopped, Retry for error). aria-busy still
  // tracks the same set so AT users hear the bubble settle on any terminal.
  const isFinal = isDone || isStopped || isErrored;

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
    >
      {showTyping ? <TypingIndicator /> : null}

      {message.parts.map((part, idx) => {
        if (part.type === "reasoning") {
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

      {isErrored ? (
        <ErrorFooter error={error} onRetry={onRegenerate} />
      ) : null}

      {isFinal && !isErrored ? (
        <div className="space-y-2 pt-1">
          {message.attribution || isStopped ? (
            <div className="flex flex-wrap items-center gap-2">
              {message.attribution ? (
                <AttributionRow
                  attribution={message.attribution}
                  onOpen={onAttributionOpen}
                />
              ) : null}
              {isStopped ? <StoppedChip /> : null}
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2 opacity-100 transition-opacity focus-within:opacity-100 md:opacity-0 md:group-hover/msg:opacity-100 [@media(hover:none)]:opacity-100">
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
        </div>
      ) : null}
    </div>
  );
}

function StatusLine({ label, state }: { label: string; state: "active" | "done" }) {
  return (
    <div className="flex items-center gap-2 text-sm text-status-line">
      {state === "active" ? (
        <Loader2 className="size-3.5 motion-safe:animate-spin" aria-hidden />
      ) : null}
      <span>{label}</span>
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

function StoppedChip() {
  return (
    <span
      className="inline-flex items-center rounded-full bg-foreground/[0.06] px-2 py-0.5 text-xs text-muted-foreground"
      data-testid="stopped-chip"
    >
      Stopped
    </span>
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
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRetry}
            disabled={retryDisabled}
            aria-disabled={retryDisabled}
            className="rounded-full"
            data-testid="assistant-error-retry"
          >
            <RotateCcw aria-hidden />
            <span>
              {retryDisabled ? `Try again in ${secondsLeft}s` : "Retry"}
            </span>
          </Button>
        ) : null}
      </div>
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
