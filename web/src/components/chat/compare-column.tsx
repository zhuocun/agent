"use client";

import {
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
  type Ref,
} from "react";

import { AssistantMessage } from "@/components/chat/assistant-message";
import { useApiStream, type TerminalResult } from "@/lib/stream-client";
import type { ApiStreamState } from "@/lib/stream-client";
import type { ChatMessage, ModelTier, MessagePart } from "@/lib/types";

// A single compare column owns ONE `useApiStream` instance — the hook holds all
// of its state in component-local refs + an own AbortController (no singletons),
// so instantiating it per column is the supported way to fan a prompt out to N
// independent streams (stream-client.ts:374). The parent (CompareView) drives
// each column through the imperative handle: it calls `start()` once the shared
// temporary conversation exists, and `stop()` on a global Stop.
export interface CompareColumnHandle {
  // Fan-out send: `conversationId` is the shared temp conversation, and the
  // caller passes a per-column `clientMessageId` so each POST is independently
  // idempotent. `isTemporary: true` is hard-wired in `start()` below — never a
  // caller's responsibility — so the column can NEVER claim the per-conversation
  // active-stream lock and collide with its sibling (the 409 STREAM_IN_PROGRESS
  // invariant — temporary turns skip the claim, conversations.py:1242).
  start: (args: {
    conversationId: string;
    clientMessageId: string;
    text: string;
  }) => void;
  stop: () => void;
}

interface CompareColumnProps {
  // The tier this column answers with. Drives the visible header label and the
  // per-turn `tierId`/`providerId` sent to the BE.
  tier: ModelTier;
  // 1-based position, used only for the accessible region label ("Column 1 of 2").
  position: number;
  total: number;
  // Streaming-time disclosure preference, forwarded to the reasoning panel.
  defaultReasoningOpen?: boolean;
  handleRef: Ref<CompareColumnHandle>;
  // Reports this column's in-flight state up to CompareView so the composer can
  // expose a Stop affordance while ANY column is still streaming.
  onStreamingChange?: (tierId: string, streaming: boolean) => void;
}

// Mirror of chat-thread.tsx's `pendingMessage` derivation: build a live
// ChatMessage from the hook's accumulating state so the same AssistantMessage
// renderer composes reasoning + answer + sources mid-stream. On terminal the
// frozen `terminal` result takes over so the column keeps its final
// reasoning/answer/sources and gains its `attribution` (→ AttributionRow).
function deriveMessage(
  id: string,
  state: ApiStreamState,
  terminal: TerminalResult | null,
): ChatMessage {
  const parts: MessagePart[] = [];
  const reasoning = terminal?.reasoning ?? state.reasoning;
  const reasoningDurationSec =
    terminal?.reasoningDurationSec ?? state.reasoningDurationSec;
  const answer = terminal?.answer ?? state.answer;
  const searchStatus = terminal?.searchStatus ?? state.searchStatus;
  const sources = terminal?.sources ?? state.sources;
  const toolParts = terminal?.toolParts ?? state.toolParts;

  if (reasoning) {
    parts.push({ type: "reasoning", text: reasoning, durationSec: reasoningDurationSec });
  }
  parts.push(...toolParts);
  if (searchStatus) {
    parts.push({
      type: "status",
      label: searchStatus.label,
      // After terminal the search has settled — force the spinner off.
      state: terminal ? "done" : searchStatus.state,
    });
  }
  if (answer) parts.push({ type: "text", text: answer });
  if (sources.length > 0) parts.push({ type: "sources", items: sources });

  return {
    id,
    role: "assistant",
    createdAt: new Date().toISOString(),
    status: terminal?.status ?? state.status,
    attribution: terminal?.status === "done" ? terminal.attribution : undefined,
    parts,
  };
}

export function CompareColumn({
  tier,
  position,
  total,
  defaultReasoningOpen = false,
  handleRef,
  onStreamingChange,
}: CompareColumnProps) {
  // Frozen terminal snapshot for this column, held in STATE (not a ref) so the
  // render reads it directly without tripping the refs-during-render rule. We
  // render from `state` while the turn streams, then from this once a terminal
  // arrives — the same split the single-stream thread does between
  // `pendingMessage` (live) and a committed message (frozen).
  const [terminal, setTerminal] = useState<TerminalResult | null>(null);

  const { state, start, stop } = useApiStream((result) => {
    setTerminal(result);
  });

  useImperativeHandle(
    handleRef,
    () => ({
      start: (args) => {
        setTerminal(null);
        start({
          conversationId: args.conversationId,
          clientMessageId: args.clientMessageId,
          tierId: tier.id,
          providerId: tier.providerId,
          text: args.text,
          // INVARIANT: every compare column sends isTemporary so the BE skips
          // the active-stream claim and N parallel POSTs to one conversation
          // never 409 (AGENTS brief + conversations.py:1093/1242).
          isTemporary: true,
        });
      },
      stop,
    }),
    [start, stop, tier.id, tier.providerId],
  );

  const message = useMemo(
    () => deriveMessage(`compare-${tier.id}`, state, terminal),
    [tier.id, state, terminal],
  );

  const hasStarted = state.status !== "idle";
  const streaming = state.status === "submitted" || state.status === "streaming";

  // Report streaming transitions up so the parent can aggregate an "any column
  // busy" flag for the composer's Stop affordance.
  useEffect(() => {
    onStreamingChange?.(tier.id, streaming);
  }, [streaming, tier.id, onStreamingChange]);

  return (
    <section
      aria-label={`Compare column ${position} of ${total}: ${tier.label}`}
      data-testid="compare-column"
      data-tier={tier.id}
      className="flex min-w-0 flex-1 flex-col gap-3"
    >
      <header className="flex items-center gap-2 border-b border-border/60 pb-2">
        <span
          className="truncate text-sm font-semibold text-foreground"
          data-testid="compare-column-tier"
        >
          {tier.label}
        </span>
        {tier.modelLabel ? (
          <span className="truncate text-xs text-muted-foreground">
            {tier.modelLabel}
          </span>
        ) : null}
      </header>
      <div className="min-w-0">
        {hasStarted ? (
          <AssistantMessage
            message={message}
            status={message.status ?? "submitted"}
            reasoningStreaming={state.reasoningStreaming}
            defaultReasoningOpen={defaultReasoningOpen}
          />
        ) : (
          <p className="text-sm text-muted-foreground">Waiting for your prompt…</p>
        )}
      </div>
    </section>
  );
}
