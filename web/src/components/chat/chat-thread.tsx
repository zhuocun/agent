"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/chat/app-shell";
import { Sidebar } from "@/components/chat/sidebar";
import { AppHeader } from "@/components/chat/app-header";
import { MessageList } from "@/components/chat/message-list";
import { UserMessage } from "@/components/chat/user-message";
import { AssistantMessage } from "@/components/chat/assistant-message";
import { WelcomeScreen } from "@/components/chat/welcome-screen";
import { TemporaryChatBanner } from "@/components/chat/temporary-chat-banner";
import { SettingsDialog } from "@/components/chat/settings-dialog";
import { Composer, type ComposerHandle } from "@/components/chat/composer";
import { LiveRegion } from "@/components/chat/live-region";
import { MODEL_TIERS_BY_ID } from "@/lib/model-tiers";
import { useMockStream, type MockStreamResult } from "@/lib/use-mock-stream";
import {
  MOCK_ACCOUNT,
  MOCK_CONVERSATION,
  MOCK_CONVERSATIONS,
  MOCK_MESSAGES,
  MOCK_PREFERENCES,
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
  UserPreferences,
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
  const composerRef = useRef<ComposerHandle>(null);

  // True when a history entry without loaded content is selected (only "c1" has
  // real messages in the demo). Distinct from the new-chat welcome hero.
  const [demoEmptyConversation, setDemoEmptyConversation] = useState(false);

  // Chrome state: sidebar (desktop rail + mobile drawer), settings, prefs,
  // temporary mode, and which history entry is active.
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [preferences, setPreferences] =
    useState<UserPreferences>(MOCK_PREFERENCES);
  const [isTemporary, setIsTemporary] = useState(
    MOCK_PREFERENCES.temporaryByDefault,
  );
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(MOCK_CONVERSATION.id);

  const firstName = MOCK_ACCOUNT.name.split(" ")[0];
  const headerTitle = isTemporary
    ? "Temporary chat"
    : (MOCK_CONVERSATIONS.find((c) => c.id === activeConversationId)?.title ??
      "New chat");

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
    setDemoEmptyConversation(false);
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

  const handleEditUserMessage = (messageId: string, newText: string) => {
    if (isStreaming) return;
    const idx = messages.findIndex((m) => m.id === messageId);
    if (idx === -1) return;
    const userId = uid();
    const assistantId = uid();
    tierAtSendRef.current = selectedTierId;
    assistantIdRef.current = assistantId;
    setDemoEmptyConversation(false);
    setMessages((prev) => [
      ...prev.slice(0, idx),
      {
        id: userId,
        role: "user",
        createdAt: new Date().toISOString(),
        parts: [{ type: "text", text: newText }],
      },
    ]);
    setPendingId(assistantId);
    setLiveMessage("Generating response");
    start({ reasoning: MOCK_STREAM_REASONING, answer: MOCK_STREAM_ANSWER });
  };

  const handleNewChat = () => {
    if (isStreaming) stop();
    setMessages([]);
    setPendingId(null);
    assistantIdRef.current = null;
    setLiveMessage("");
    reset();
    setActiveConversationId(null);
    setDemoEmptyConversation(false);
    setSelectedTierId(preferences.defaultTierId);
    setIsTemporary(preferences.temporaryByDefault);
    setMobileNavOpen(false);
  };

  // Header Ghost / banner toggle. Turning Temporary ON starts a FRESH temporary
  // chat (clears like New chat) so the "won't be saved" promise is always true.
  // Turning it OFF just exits temporary mode and keeps the current messages.
  const handleToggleTemporary = () => {
    if (isTemporary) {
      setIsTemporary(false);
      return;
    }
    if (isStreaming) stop();
    setMessages([]);
    setPendingId(null);
    assistantIdRef.current = null;
    setLiveMessage("");
    reset();
    setActiveConversationId(null);
    setDemoEmptyConversation(false);
    setSelectedTierId(preferences.defaultTierId);
    setIsTemporary(true);
    setMobileNavOpen(false);
  };

  // Mock selection: highlight the chosen entry and exit temporary mode. Only
  // "c1" has loaded content; other entries clear the thread and show an honest
  // placeholder rather than leaving an unrelated body on screen.
  const handleSelectConversation = (id: string) => {
    if (isStreaming) stop();
    setPendingId(null);
    assistantIdRef.current = null;
    setLiveMessage("");
    reset();
    if (id === MOCK_CONVERSATION.id) {
      setMessages(MOCK_MESSAGES);
      setDemoEmptyConversation(false);
    } else {
      setMessages([]);
      setDemoEmptyConversation(true);
    }
    setActiveConversationId(id);
    setIsTemporary(false);
    setMobileNavOpen(false);
  };

  const handlePickSuggestion = (prompt: string) => {
    composerRef.current?.setDraft(prompt);
  };

  const showWelcome =
    messages.length === 0 && !pendingMessage && !demoEmptyConversation;

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            conversations={MOCK_CONVERSATIONS}
            activeId={activeConversationId}
            account={MOCK_ACCOUNT}
            onSelect={handleSelectConversation}
            onNewChat={handleNewChat}
            onOpenSettings={() => setSettingsOpen(true)}
            onCollapse={() => {
              setSidebarOpen(false);
              setMobileNavOpen(false);
            }}
          />
        }
        sidebarOpen={sidebarOpen}
        mobileNavOpen={mobileNavOpen}
        onMobileNavOpenChange={setMobileNavOpen}
      >
        {/* Three-layer chrome stack: messages scroll *under* gradient strips at
            the top and bottom, with the floating header buttons and composer
            capsule sitting fully opaque on top. iOS Claude / Codex chrome. */}
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          {/* Top chrome strip — positions the floating buttons (and the
              temporary-chat banner when on) at the top with safe-area
              reservation. Gradient bg keeps the iOS status bar text
              readable as messages scroll up under the notch; fades to
              transparent below so messages emerge cleanly. */}
          <div className="pointer-events-none absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-background via-background/85 to-background/0 pt-[env(safe-area-inset-top)] pb-2 md:pb-6">
            <div className="pointer-events-auto">
              <AppHeader
                title={headerTitle}
                subtitle={MODEL_TIERS_BY_ID[selectedTierId].label}
                sidebarOpen={sidebarOpen}
                onOpenMobileNav={() => setMobileNavOpen(true)}
                onOpenSidebar={() => setSidebarOpen(true)}
                onNewChat={handleNewChat}
                onOpenSettings={() => setSettingsOpen(true)}
                isTemporary={isTemporary}
                onToggleTemporary={handleToggleTemporary}
              />
              {isTemporary ? (
                <TemporaryChatBanner onTurnOff={handleToggleTemporary} />
              ) : null}
            </div>
          </div>

          {/* Message area — for WelcomeScreen / demo-empty we put a single
              scroll wrapper that clears both strips. For MessageList we let
              it own its scroll (its internal `<ol>` already has matching
              pt/pb that clears the chrome). */}
          {showWelcome ? (
            <div
              className={
                isTemporary
                  ? "min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+7rem)]"
                  : "min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+3.5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+5rem)]"
              }
            >
              <WelcomeScreen
                onPickSuggestion={handlePickSuggestion}
                userName={firstName}
              />
            </div>
          ) : demoEmptyConversation ? (
            <div
              className={
                isTemporary
                  ? "flex min-h-0 flex-1 items-center justify-center px-4 pt-[calc(env(safe-area-inset-top)+5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+7rem)]"
                  : "flex min-h-0 flex-1 items-center justify-center px-4 pt-[calc(env(safe-area-inset-top)+3.5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+5rem)]"
              }
            >
              <p className="max-w-sm text-center text-sm text-muted-foreground">
                This is a demo — only the pinned conversation has saved messages.
              </p>
            </div>
          ) : (
            <MessageList>
              {messages.map((m) =>
                m.role === "user" ? (
                  <UserMessage
                    key={m.id}
                    message={m}
                    canEdit={!isStreaming}
                    onEdit={(newText) => handleEditUserMessage(m.id, newText)}
                  />
                ) : (
                  <AssistantMessage
                    key={m.id}
                    message={m}
                    status={m.status ?? "done"}
                    canRegenerate={!isStreaming && m.id === lastAssistantId}
                    onRegenerate={handleRegenerate}
                    onFeedback={(f) => setFeedback(m.id, f)}
                    defaultReasoningOpen={preferences.autoExpandReasoning}
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
          )}

          {/* Bottom chrome strip — opaque at the bottom edge, fades upward. */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-background via-background/85 to-background/0 pt-6 pb-[var(--bottom-inset)]">
            <div className="pointer-events-auto">
              <Composer
                ref={composerRef}
                isStreaming={isStreaming}
                selectedTierId={selectedTierId}
                onSelectTier={setSelectedTierId}
                usage={MOCK_USAGE}
                onSend={handleSend}
                onStop={stop}
                sendOnEnter={preferences.sendOnEnter}
              />
            </div>
          </div>
        </div>
      </AppShell>

      <SettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        preferences={preferences}
        onPreferencesChange={setPreferences}
        account={MOCK_ACCOUNT}
        usage={MOCK_USAGE}
      />

      <LiveRegion message={liveMessage} />
    </>
  );
}
