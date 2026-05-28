"use client";

import { useMemo } from "react";
import { Loader2, Sparkles, Square } from "lucide-react";

import { ReasoningPanel } from "@/components/chat/reasoning-panel";
import { MarkdownRenderer } from "@/components/chat/markdown-renderer";
import { AttributionRow } from "@/components/chat/attribution-row";
import { MessageActions } from "@/components/chat/message-actions";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import type { ChatMessage, Feedback, MessagePart, StreamStatus } from "@/lib/types";

interface AssistantMessageProps {
  message: ChatMessage;
  status: StreamStatus;
  reasoningStreaming?: boolean;
  canRegenerate?: boolean;
  onRegenerate?: () => void;
  onFeedback?: (next: Feedback) => void;
  // When true, a completed message's reasoning panel starts expanded.
  defaultReasoningOpen?: boolean;
}

export function AssistantMessage({
  message,
  status,
  reasoningStreaming,
  canRegenerate,
  onRegenerate,
  onFeedback,
  defaultReasoningOpen = false,
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
  const isFinal = status === "done" || status === "stopped";

  return (
    <div className="group/msg flex gap-3" role="article" aria-label="Assistant">
      <div
        className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand"
        aria-hidden
      >
        <Sparkles className="size-4" />
      </div>

      <div className="min-w-0 flex-1 space-y-3">
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
              <MarkdownRenderer key={idx}>{part.text}</MarkdownRenderer>
            ) : null;
          }
          if (part.type === "status") {
            return <StatusLine key={idx} label={part.label} state={part.state} />;
          }
          return null;
        })}

        {status === "stopped" ? <StoppedChip /> : null}

        {isFinal ? (
          <div className="space-y-2 pt-0.5">
            {message.attribution ? (
              <AttributionRow attribution={message.attribution} />
            ) : null}
            <div className="opacity-100 transition-opacity focus-within:opacity-100 md:opacity-0 md:group-hover/msg:opacity-100">
              <MessageActions
                text={answerText}
                feedback={message.feedback ?? null}
                canRegenerate={canRegenerate}
                onRegenerate={onRegenerate}
                onFeedback={onFeedback}
              />
            </div>
          </div>
        ) : null}
      </div>
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
    <div className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
      <Square className="size-3 fill-current" aria-hidden />
      Stopped
    </div>
  );
}
