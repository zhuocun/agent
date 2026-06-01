"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Loader2, RotateCcw } from "lucide-react";

import { ReasoningPanel } from "@/components/chat/reasoning-panel";
import { SourcesPanel } from "@/components/chat/sources-panel";
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
import type { ChatMessage, Feedback, MessagePart, StreamStatus } from "@/lib/types";

interface AssistantMessageProps {
  message: ChatMessage;
  status: StreamStatus;
  reasoningStreaming?: boolean;
  canBranch?: boolean;
  isBranching?: boolean;
  canRegenerate?: boolean;
  onBranch?: () => void;
  onRegenerate?: () => void;
  onFeedback?: (next: Feedback) => void;
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
  onBranch,
  onRegenerate,
  onFeedback,
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
              <MarkdownRenderer>{part.text}</MarkdownRenderer>
            </div>
          ) : null;
        }
        if (part.type === "status") {
          return <StatusLine key={idx} label={part.label} state={part.state} />;
        }
        if (part.type === "sources") {
          // Rendered AFTER the answer text (the part ordering — text then
          // sources — is established upstream in chat-thread.tsx).
          return <SourcesPanel key={idx} items={part.items} />;
        }
        if (part.type === "tool_call" || part.type === "tool_result") {
          return <ToolPartView key={idx} part={part} />;
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
                <AttributionRow attribution={message.attribution} />
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
              onBranch={onBranch}
              onRegenerate={onRegenerate}
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
            className="rounded-full"
            data-testid="assistant-error-retry"
          >
            <RotateCcw aria-hidden />
            <span>Retry</span>
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
