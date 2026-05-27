"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { AppHeader } from "@/components/chat/app-header";
import { MessageList } from "@/components/chat/message-list";
import { UserMessage } from "@/components/chat/user-message";
import { AssistantMessage } from "@/components/chat/assistant-message";
import { Composer } from "@/components/chat/composer";
import { LiveRegion } from "@/components/chat/live-region";
import { useMockStream, type MockStreamResult } from "@/lib/use-mock-stream";
import {
  MOCK_CONVERSATION,
  MOCK_MESSAGES,
  MOCK_STREAM_ANSWER,
  MOCK_STREAM_REASONING,
  MOCK_USAGE,
} from "@/lib/mock-data";
import type {
  ChatMessage,
  Feedback,
  MessagePart,
  ModelAttribution,
  ModelTierId,
} from "@/lib/types";

let idCounter = 0;
const uid = () => `local-${Date.now()}-${idCounter++}`;

// Attribution for a freshly streamed turn (mock). Served on the requested tier,
// flat (no long-context surcharge) — the calm, "nothing to see here" case.
function freshAttribution(tier: ModelTierId): ModelAttribution {
  return {
    requestedTierId: tier,
    servedTierId: tier,
    servedModelLabel: "Claude Sonnet 4.6",
    isByok: false,
    costUsd: 0.002934,
    costConfidence: "exact",
    breakdown: {
      currency: "USD",
      listPriceInPerM: 3,
      listPriceOutPerM: 15,
      inputTokens: 143,
      outputTokens: 191,
      reasoningTokens: 72,
      cachedInputTokens: 0,
      longContext: { flat: true, tokensRepriced: "none" },
      promoApplied: false,
      subtotalUsd: 0.002934,
      sessionSurchargeUsd: 0,
    },
  };
}

export function ChatThread() {
  const [messages, setMessages] = useState<ChatMessage[]>(MOCK_MESSAGES);
  const [selectedTierId, setSelectedTierId] = useState<ModelTierId>(
    MOCK_CONVERSATION.selectedTierId,
  );
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState("");
  const tierAtSendRef = useRef<ModelTierId>(selectedTierId);
  const assistantIdRef = useRef<string | null>(null);

  // Commit the finished assistant turn when the stream terminates — event-driven
  // (the hook hands us the final flushed content), not a status-watching effect.
  const handleTerminal = useCallback((result: MockStreamResult) => {
    const id = assistantIdRef.current;
    if (!id) return;

    const parts: MessagePart[] = [];
    if (result.reasoning) {
      parts.push({
        type: "reasoning",
        text: result.reasoning,
        durationSec: result.reasoningDurationSec,
      });
    }
    if (result.answer) parts.push({ type: "text", text: result.answer });

    const finalized: ChatMessage = {
      id,
      role: "assistant",
      createdAt: new Date().toISOString(),
      status: result.status,
      feedback: null,
      attribution:
        result.status === "done" ? freshAttribution(tierAtSendRef.current) : undefined,
      parts,
    };

    setMessages((prev) => [...prev, finalized]);
    setLiveMessage(result.status === "done" ? "Response ready" : "Generation stopped");
    setPendingId(null);
    assistantIdRef.current = null;
  }, []);

  const { state, start, stop, reset } = useMockStream(handleTerminal);

  const isStreaming =
    pendingId !== null && (state.status === "submitted" || state.status === "streaming");

  const handleSend = (text: string) => {
    const userId = uid();
    const assistantId = uid();
    tierAtSendRef.current = selectedTierId;
    assistantIdRef.current = assistantId;
    setMessages((prev) => [
      ...prev,
      {
        id: userId,
        role: "user",
        createdAt: new Date().toISOString(),
        parts: [{ type: "text", text }],
      },
    ]);
    setPendingId(assistantId);
    setLiveMessage("Generating response");
    start({ reasoning: MOCK_STREAM_REASONING, answer: MOCK_STREAM_ANSWER });
  };

  const pendingMessage: ChatMessage | null = useMemo(() => {
    if (!pendingId) return null;
    const parts: MessagePart[] = [];
    if (state.reasoning) {
      parts.push({
        type: "reasoning",
        text: state.reasoning,
        durationSec: state.reasoningDurationSec,
      });
    }
    if (state.answer) parts.push({ type: "text", text: state.answer });
    return {
      id: pendingId,
      role: "assistant",
      createdAt: new Date().toISOString(),
      status: state.status,
      parts,
    };
  }, [pendingId, state]);

  const lastAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return null;
  }, [messages]);

  const setFeedback = (id: string, next: Feedback) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, feedback: next } : m)),
    );
  };

  const handleRegenerate = () => {
    if (isStreaming) return;
    // Drop trailing assistant turn(s), then re-stream a fresh response.
    setMessages((prev) => {
      const next = [...prev];
      while (next.length && next[next.length - 1].role === "assistant") next.pop();
      return next;
    });
    const regenId = uid();
    assistantIdRef.current = regenId;
    setPendingId(regenId);
    setLiveMessage("Regenerating response");
    start({ reasoning: MOCK_STREAM_REASONING, answer: MOCK_STREAM_ANSWER });
  };

  const handleNewChat = () => {
    if (isStreaming) stop();
    setMessages([]);
    setPendingId(null);
    assistantIdRef.current = null;
    setLiveMessage("");
    reset();
  };

  return (
    <div className="flex h-dvh flex-col bg-background">
      <AppHeader title={MOCK_CONVERSATION.title} onNewChat={handleNewChat} />

      <MessageList>
        {messages.map((m) =>
          m.role === "user" ? (
            <UserMessage key={m.id} message={m} />
          ) : (
            <AssistantMessage
              key={m.id}
              message={m}
              status={m.status ?? "done"}
              canRegenerate={!isStreaming && m.id === lastAssistantId}
              onRegenerate={handleRegenerate}
              onFeedback={(f) => setFeedback(m.id, f)}
            />
          ),
        )}

        {pendingMessage ? (
          <AssistantMessage
            message={pendingMessage}
            status={state.status}
            reasoningStreaming={state.reasoningStreaming}
          />
        ) : null}
      </MessageList>

      <div className="shrink-0">
        <Composer
          isStreaming={isStreaming}
          selectedTierId={selectedTierId}
          onSelectTier={setSelectedTierId}
          usage={MOCK_USAGE}
          onSend={handleSend}
          onStop={stop}
        />
      </div>

      <LiveRegion message={liveMessage} />
    </div>
  );
}
