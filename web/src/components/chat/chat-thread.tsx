"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import {
  ClipboardCopy,
  Code2,
  KeyRound,
  MessageSquarePlus,
  PanelLeft,
  Settings as SettingsIcon,
  Sparkles,
  TextCursorInput,
  Trash2,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
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
import {
  CommandPalette,
  type CommandAction,
} from "@/components/chat/command-palette";
import {
  ShortcutsDialog,
  type ShortcutSection,
} from "@/components/chat/shortcuts-dialog";
import {
  useKeyboardShortcuts,
  type Shortcut,
} from "@/lib/use-keyboard-shortcuts";
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
  ConversationSummary,
  Feedback,
  MessagePart,
  ModelAttribution,
  ModelTierId,
  UserPreferences,
} from "@/lib/types";

let idCounter = 0;
const uid = () => `local-${Date.now()}-${idCounter++}`;

// `KEY_BINDINGS` carries the static keystroke metadata; `runAction(id)` owns
// the live handler. The split keeps the descriptor array free of state
// closures, which the React Compiler would otherwise flag as ref-tainted.
type ShortcutId =
  | "palette"
  | "new-chat"
  | "focus-composer"
  | "copy-last-response"
  | "copy-last-code"
  | "toggle-sidebar"
  | "custom-instructions"
  | "delete-chat"
  | "shortcuts"
  | "open-settings"
  | "toggle-theme";

type KeyBinding = Omit<Shortcut, "handler"> & {
  id: ShortcutId;
  label: string;
};
const KEY_BINDINGS: KeyBinding[] = [
  {
    id: "palette",
    label: "Command palette",
    key: "k",
    mod: true,
    allowInInput: true,
  },
  {
    id: "new-chat",
    label: "New chat",
    key: "O",
    mod: true,
    shift: true,
    allowInInput: true,
  },
  {
    id: "focus-composer",
    label: "Focus composer",
    key: "Escape",
    shift: true,
    allowInInput: true,
  },
  {
    id: "copy-last-response",
    label: "Copy last response",
    key: "C",
    mod: true,
    shift: true,
    allowInInput: true,
  },
  {
    id: "copy-last-code",
    label: "Copy last code block",
    key: ";",
    mod: true,
    shift: true,
    allowInInput: true,
  },
  {
    id: "toggle-sidebar",
    label: "Toggle sidebar",
    key: "S",
    mod: true,
    shift: true,
    allowInInput: true,
  },
  {
    id: "custom-instructions",
    label: "Open custom instructions",
    key: "I",
    mod: true,
    shift: true,
    allowInInput: true,
  },
  {
    id: "delete-chat",
    label: "Delete current chat",
    key: "Backspace",
    mod: true,
    shift: true,
    allowInInput: true,
  },
  {
    id: "shortcuts",
    label: "Show all shortcuts",
    key: "/",
    mod: true,
    allowInInput: true,
  },
];

// Lookup helper for grouping the palette / dialog views.
const BINDING_BY_ID = (id: ShortcutId): KeyBinding => {
  const found = KEY_BINDINGS.find((b) => b.id === id);
  if (!found) throw new Error(`Missing binding for shortcut ${id}`);
  return found;
};

// Palette rows. "Hidden" entries (the palette itself) are omitted; settings/
// theme entries are palette-only (no global shortcut).
const PALETTE_ACTION_META: Array<{
  id: ShortcutId;
  label: string;
  icon: CommandAction["icon"];
  section: "Actions" | "Settings";
  binding?: KeyBinding;
}> = [
  { id: "new-chat", label: "New chat", icon: MessageSquarePlus, section: "Actions", binding: BINDING_BY_ID("new-chat") },
  { id: "focus-composer", label: "Focus composer", icon: TextCursorInput, section: "Actions", binding: BINDING_BY_ID("focus-composer") },
  { id: "copy-last-response", label: "Copy last response", icon: ClipboardCopy, section: "Actions", binding: BINDING_BY_ID("copy-last-response") },
  { id: "copy-last-code", label: "Copy last code block", icon: Code2, section: "Actions", binding: BINDING_BY_ID("copy-last-code") },
  { id: "toggle-sidebar", label: "Toggle sidebar", icon: PanelLeft, section: "Actions", binding: BINDING_BY_ID("toggle-sidebar") },
  { id: "delete-chat", label: "Delete current chat", icon: Trash2, section: "Actions", binding: BINDING_BY_ID("delete-chat") },
  { id: "custom-instructions", label: "Open custom instructions", icon: Sparkles, section: "Settings", binding: BINDING_BY_ID("custom-instructions") },
  { id: "shortcuts", label: "Show all shortcuts", icon: KeyRound, section: "Settings", binding: BINDING_BY_ID("shortcuts") },
  { id: "open-settings", label: "Open settings", icon: SettingsIcon, section: "Settings" },
  { id: "toggle-theme", label: "Toggle light / dark theme", icon: SettingsIcon, section: "Settings" },
];

// Shortcuts dialog grouping. Ordered to match the PRD §5.5 table loosely:
// general (palette/shortcuts/custom-instructions) → navigation → editing.
const SHORTCUT_DIALOG_SECTIONS: { heading: string; ids: ShortcutId[] }[] = [
  { heading: "General", ids: ["palette", "shortcuts", "custom-instructions"] },
  { heading: "Navigation", ids: ["new-chat", "focus-composer", "toggle-sidebar"] },
  { heading: "Editing", ids: ["copy-last-response", "copy-last-code", "delete-chat"] },
];

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
  // real messages in the demo). Tracked for future use (e.g. an empty-state
  // affordance specific to picked-but-unloaded history); the UI currently shows
  // the same WelcomeScreen for both fresh-new-chat and demo-empty.
  const [, setDemoEmptyConversation] = useState(false);

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
  const [conversations, setConversations] = useState<ConversationSummary[]>(
    MOCK_CONVERSATIONS,
  );
  const [conversationSearch, setConversationSearch] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsDialogOpen, setShortcutsDialogOpen] = useState(false);
  // Both the shortcut and the palette's "Delete current chat" route through
  // this confirm — never delete without it (data-loss guard).
  const [pendingDeleteConversationId, setPendingDeleteConversationId] =
    useState<string | null>(null);
  const { theme, setTheme, resolvedTheme } = useTheme();

  const firstName = MOCK_ACCOUNT.name.split(" ")[0];

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

  // Explicit copy-on-branch (PRD 01 §4.6, P1). We COPY the slice of the thread
  // up-to-and-including the chosen assistant turn into a brand-new conversation;
  // the source thread is left untouched (no in-thread tree). Streaming turns are
  // not branchable — the affordance is gated in the UI and we defensively bail
  // here too.
  const handleBranchFromMessage = (messageId: string) => {
    if (isStreaming) return;
    const idx = messages.findIndex((m) => m.id === messageId);
    if (idx === -1) return;

    const branchSlice = messages.slice(0, idx + 1);

    // Stop any in-flight stream and clear pending refs, mirroring the reset
    // pattern in handleSelectConversation / handleNewChat.
    stop();
    reset();

    // Derive a title from the first user turn in the slice. Trim, collapse
    // internal whitespace, cap at 60 chars. No ellipsis — just truncate.
    const firstUserText = branchSlice
      .find((m) => m.role === "user")
      ?.parts.find((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
      ?.text;
    const normalized = firstUserText?.replace(/\s+/g, " ").trim() ?? "";
    const title = normalized.length > 0 ? normalized.slice(0, 60) : "Branched chat";

    const newId = uid();
    const newConversation: ConversationSummary = {
      id: newId,
      title,
      updatedAt: new Date().toISOString(),
      pinned: false,
    };

    setConversations((prev) => [newConversation, ...prev]);
    setMessages(branchSlice);
    setActiveConversationId(newId);
    setPendingId(null);
    assistantIdRef.current = null;
    setDemoEmptyConversation(false);
    setIsTemporary(false);
    setMobileNavOpen(false);
    setLiveMessage("Branched into new chat");
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

  const handleRenameConversation = (id: string, newTitle: string) => {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    setConversations((prev) => {
      const target = prev.find((c) => c.id === id);
      if (!target || target.title === trimmed) return prev;
      const nowIso = new Date().toISOString();
      return prev.map((c) =>
        c.id === id ? { ...c, title: trimmed, updatedAt: nowIso } : c,
      );
    });
  };

  const handleDeleteConversation = (id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (id === activeConversationId) {
      // Mirror handleNewChat: drop the open thread back to a fresh New chat
      // since the conversation it represented no longer exists.
      if (isStreaming) stop();
      setMessages([]);
      setPendingId(null);
      assistantIdRef.current = null;
      setLiveMessage("");
      reset();
      setActiveConversationId(null);
      setDemoEmptyConversation(false);
    }
  };

  const handleTogglePinConversation = (id: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, pinned: !c.pinned } : c)),
    );
  };

  const showWelcome = messages.length === 0 && !pendingMessage;

  const lastAssistantText = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role !== "assistant") continue;
      const texts: string[] = [];
      for (const p of m.parts) {
        if (p.type === "text") texts.push(p.text);
      }
      return texts.join("\n\n");
    }
    return "";
  }, [messages]);

  // Last fenced code block in the most recent assistant message. Tolerant
  // regex: optional language tag, optional trailing whitespace before fence.
  const lastCodeBlock = useMemo(() => {
    if (!lastAssistantText) return "";
    const re = /```[^\n]*\n([\s\S]*?)\n?```/g;
    let result = "";
    let match: RegExpExecArray | null;
    while ((match = re.exec(lastAssistantText)) !== null) {
      result = match[1] ?? "";
    }
    return result;
  }, [lastAssistantText]);

  const handleCopyLastResponse = () => {
    if (!lastAssistantText) {
      setLiveMessage("No response to copy");
      return;
    }
    void navigator.clipboard?.writeText(lastAssistantText).then(
      () => setLiveMessage("Copied last response"),
      () => setLiveMessage("Copy failed"),
    );
  };

  const handleCopyLastCodeBlock = () => {
    if (!lastCodeBlock) {
      setLiveMessage("No code block to copy");
      return;
    }
    void navigator.clipboard?.writeText(lastCodeBlock).then(
      () => setLiveMessage("Copied last code block"),
      () => setLiveMessage("Copy failed"),
    );
  };

  const handleFocusComposer = () => {
    composerRef.current?.focus();
  };

  // matchMedia gates which surface gets toggled so the desktop and mobile
  // states never silently desync after a viewport resize. md = Tailwind 768px.
  const handleToggleSidebar = () => {
    if (
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 768px)").matches
    ) {
      setSidebarOpen((v) => !v);
    } else {
      setMobileNavOpen((v) => !v);
    }
  };

  // Cycle theme: explicit light <-> dark, falling through System. next-themes
  // returns the active theme on the client so no hydration-mismatch dance.
  const handleToggleTheme = () => {
    const current = theme === "system" ? resolvedTheme : theme;
    setTheme(current === "dark" ? "light" : "dark");
  };

  const handleOpenSettings = () => {
    setSettingsOpen(true);
  };

  // Custom instructions live inside the settings dialog in MVP; wiring the
  // shortcut now so muscle memory transfers when a dedicated panel ships.
  const handleOpenCustomInstructions = () => {
    setSettingsOpen(true);
  };

  // Routes through the same confirmation dialog the sidebar uses — never
  // wipe an active conversation on a single keystroke.
  const handleRequestDeleteCurrentChat = () => {
    if (!activeConversationId) return;
    setPendingDeleteConversationId(activeConversationId);
  };

  const confirmPendingDelete = () => {
    if (!pendingDeleteConversationId) return;
    handleDeleteConversation(pendingDeleteConversationId);
    setPendingDeleteConversationId(null);
  };

  const pendingDeleteConversation = pendingDeleteConversationId
    ? conversations.find((c) => c.id === pendingDeleteConversationId) ?? null
    : null;

  // The hook syncs `boundShortcuts` to a ref each render, so we can build a
  // fresh array (and a fresh `runAction`) every render without re-binding the
  // keydown listener or capturing stale state.
  const runAction = (id: ShortcutId): void => {
    switch (id) {
      case "palette":
        setPaletteOpen((v) => !v);
        return;
      case "new-chat":
        handleNewChat();
        return;
      case "focus-composer":
        handleFocusComposer();
        return;
      case "copy-last-response":
        handleCopyLastResponse();
        return;
      case "copy-last-code":
        handleCopyLastCodeBlock();
        return;
      case "toggle-sidebar":
        handleToggleSidebar();
        return;
      case "custom-instructions":
        handleOpenCustomInstructions();
        return;
      case "delete-chat":
        handleRequestDeleteCurrentChat();
        return;
      case "shortcuts":
        setShortcutsDialogOpen((v) => !v);
        return;
      case "open-settings":
        handleOpenSettings();
        return;
      case "toggle-theme":
        handleToggleTheme();
        return;
    }
  };

  const boundShortcuts = KEY_BINDINGS.map((b) => ({
    ...b,
    handler: () => runAction(b.id),
  }));
  useKeyboardShortcuts(boundShortcuts);

  // Palette actions: every keyboard-bound entry that isn't "Hidden", plus
  // the palette-only Settings/Theme entries. Icon set is hand-picked to stay
  // visually quiet (no emoji, all stroke icons).
  const paletteActions: CommandAction[] = PALETTE_ACTION_META.map((meta) => ({
    id: meta.id,
    label: meta.label,
    icon: meta.icon,
    shortcut: meta.binding,
    section: meta.section,
    run: () => runAction(meta.id),
  }));

  // Sections rendered by the shortcuts dialog (Hidden entries surface here
  // too so power users see Cmd+K listed). Ordered to match the PRD §5.5 table.
  const shortcutSections: ShortcutSection[] = SHORTCUT_DIALOG_SECTIONS.map(
    (section) => ({
      heading: section.heading,
      items: section.ids.map((id) => {
        const binding = KEY_BINDINGS.find((b) => b.id === id);
        if (!binding) throw new Error(`Missing binding for shortcut ${id}`);
        return {
          label: binding.label,
          shortcut: binding,
        };
      }),
    }),
  );

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            conversations={conversations}
            activeId={activeConversationId}
            account={MOCK_ACCOUNT}
            search={conversationSearch}
            onSearchChange={setConversationSearch}
            onSelect={handleSelectConversation}
            onNewChat={handleNewChat}
            onRenameConversation={handleRenameConversation}
            onDeleteConversation={handleDeleteConversation}
            onTogglePinConversation={handleTogglePinConversation}
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
          <div className="pointer-events-none absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-background via-background/85 to-background/0 pt-[env(safe-area-inset-top)] pb-6 md:pb-12">
            <div className="pointer-events-auto">
              <AppHeader
                sidebarOpen={sidebarOpen}
                onOpenMobileNav={() => setMobileNavOpen(true)}
                onOpenSidebar={() => setSidebarOpen(true)}
                onNewChat={handleNewChat}
              />
              {isTemporary ? (
                <TemporaryChatBanner onTurnOff={handleToggleTemporary} />
              ) : null}
            </div>
          </div>

          {/* Message area — for WelcomeScreen (including demo-empty history
              picks) we put a single scroll wrapper that clears both strips.
              For MessageList we let it own its scroll (its internal `<ol>`
              already has matching pt/pb that clears the chrome). */}
          {showWelcome ? (
            <div
              className={
                isTemporary
                  ? "min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+7rem)]"
                  : "min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+3.5rem)] pb-[calc(var(--bottom-inset)+9rem)] md:pt-[calc(env(safe-area-inset-top)+5rem)]"
              }
            >
              <WelcomeScreen userName={firstName} />
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
                    canBranch={!isStreaming && m.id !== pendingId}
                    onBranch={() => handleBranchFromMessage(m.id)}
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

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        actions={paletteActions}
        conversations={conversations}
        activeId={activeConversationId}
        onSelectConversation={handleSelectConversation}
      />

      <ShortcutsDialog
        open={shortcutsDialogOpen}
        onOpenChange={setShortcutsDialogOpen}
        shortcuts={shortcutSections}
      />

      <Dialog
        open={pendingDeleteConversationId !== null}
        onOpenChange={(next) => {
          if (!next) setPendingDeleteConversationId(null);
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
            <DialogDescription>
              {pendingDeleteConversation
                ? `This will delete "${pendingDeleteConversation.title}" permanently. This can't be undone.`
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPendingDeleteConversationId(null)}
              className="rounded-full"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmPendingDelete}
              className="rounded-full"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <LiveRegion message={liveMessage} />
    </>
  );
}
