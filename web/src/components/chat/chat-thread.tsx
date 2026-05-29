"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import {
  ClipboardCopy,
  Code2,
  KeyRound,
  MessageSquarePlus,
  PanelLeft,
  Settings as SettingsIcon,
  Sparkles,
  Sun,
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
import { showToast } from "@/components/ui/toast";
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
import { useApiStream, type TerminalResult } from "@/lib/stream-client";
import {
  ApiError,
  ApiNetworkError,
  createConversation,
  deleteConversation,
  fetchBootstrap,
  fetchConversation,
  patchConversation,
  postFeedback,
  postAuthSignout,
  putPreferences,
  type BootstrapResponse,
} from "@/lib/apiClient";
import { REASONING_EFFORTS } from "@/lib/reasoning-efforts";
import type {
  AccountInfo,
  ChatMessage,
  ConversationSummary,
  Feedback,
  MessagePart,
  ModelTier,
  ModelTierId,
  ReasoningEffortId,
  UsageBudget,
  UserPreferences,
} from "@/lib/types";

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
  { id: "toggle-theme", label: "Toggle theme", icon: Sun, section: "Settings" },
];

// Shortcuts dialog grouping. Ordered to match the PRD §5.5 table loosely:
// general (palette/shortcuts/custom-instructions) → navigation → editing.
const SHORTCUT_DIALOG_SECTIONS: { heading: string; ids: ShortcutId[] }[] = [
  { heading: "General", ids: ["palette", "shortcuts", "custom-instructions"] },
  { heading: "Navigation", ids: ["new-chat", "focus-composer", "toggle-sidebar"] },
  { heading: "Editing", ids: ["copy-last-response", "copy-last-code", "delete-chat"] },
];

// Local-only id generator for optimistic message bubbles before the server
// echoes the real uuid. Never sent to the server (clientMessageId uses
// crypto.randomUUID() instead). Replaced on terminal via reconciliation.
let localIdCounter = 0;
const localId = (): string => `local-${Date.now()}-${localIdCounter++}`;

// In-memory message variant. ChatMessage is the canonical wire/persisted shape;
// `error` is FE-only state from a stream-terminal error frame and never
// round-trips to the server.
type LocalChatMessage = ChatMessage & { error?: ApiError };

// Default tier when bootstrap is still pending — only used to seed the picker
// for the brief loading frame; replaced by `preferences.defaultTierId` once
// bootstrap resolves.
const DEFAULT_TIER_ID: ModelTierId = "auto";

export function ChatThread() {
  // Bootstrap-derived state. `null` until `fetchBootstrap()` resolves.
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [bootstrapError, setBootstrapError] = useState<ApiError | null>(null);
  const [bootstrapAttempt, setBootstrapAttempt] = useState(0);

  // Chat state. The in-memory message shape carries an optional `error` field
  // on assistant turns — the canonical ApiErrorEnvelope from the terminal
  // frame — so the bubble can render the inline chip + Details + Retry per
  // PRD 08 §3 + §11.2. Server-loaded conversations never carry it (errored
  // turns are not persisted as turns); the field is in-memory only.
  const [messages, setMessages] = useState<LocalChatMessage[]>([]);
  const [selectedTierId, setSelectedTierId] =
    useState<ModelTierId>(DEFAULT_TIER_ID);
  const [selectedReasoningEffortId, setSelectedReasoningEffortId] =
    useState<ReasoningEffortId>("auto");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState("");
  const tierAtSendRef = useRef<ModelTierId>(selectedTierId);
  // The optimistic id of the user message we just sent — set on send, cleared
  // on terminal (after we replace it with the server-issued uuid). Reconciling
  // user + assistant ids happens together on the `terminal` callback so the
  // message list and feedback POSTs always reference server-issued ids.
  const pendingUserIdRef = useRef<string | null>(null);
  const assistantIdRef = useRef<string | null>(null);
  // Latest in-flight `fetchConversation` request id; the load callback drops
  // its response if a faster selection has since superseded it.
  const selectConversationTokenRef = useRef<string | null>(null);
  const composerRef = useRef<ComposerHandle>(null);

  // Chrome state: sidebar (desktop rail + mobile drawer), settings, prefs,
  // temporary mode, and which conversation is active.
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isTemporary, setIsTemporary] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [conversationSearch, setConversationSearch] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsDialogOpen, setShortcutsDialogOpen] = useState(false);
  // Both the shortcut and the palette's "Delete current chat" route through
  // this confirm — never delete without it (data-loss guard).
  const [pendingDeleteConversationId, setPendingDeleteConversationId] =
    useState<string | null>(null);
  // Welcome→thread choreography (Decision 11, Opportunity 11): on first send
  // the welcome hero exits before the user bubble enters. Sequential — only
  // one disclosure surface in motion at a time (Pattern: Choreography of
  // disclosure). The timeout below is the fallback under reduced-motion where
  // animationend won't fire because CSS transition-duration is collapsed.
  // `welcomeSeamLanding` flags the post-exit moment so MessageList enters on
  // the same spring curve from below; cleared after the entrance budget so
  // unrelated mounts (conversation select, regenerate) don't animate.
  const [welcomeExiting, setWelcomeExiting] = useState(false);
  const [welcomeSeamLanding, setWelcomeSeamLanding] = useState(false);
  const welcomeExitTimerRef = useRef<number | null>(null);
  const welcomeSeamTimerRef = useRef<number | null>(null);
  const { theme, setTheme, resolvedTheme } = useTheme();

  // Bootstrap fetch — single trip on mount (and on retry). The in-flight ref
  // short-circuits StrictMode's double-mount in dev: AbortController alone
  // doesn't help because the BE assigns an anonymous user on the cookieless
  // first hit BEFORE the response arrives, so a second concurrent request
  // would mint a second user row even if we discard its response.
  const bootstrapInFlightRef = useRef(false);
  useEffect(() => {
    if (bootstrapInFlightRef.current) return;
    bootstrapInFlightRef.current = true;
    const controller = new AbortController();
    void (async () => {
      try {
        const result = await fetchBootstrap(controller.signal);
        if (controller.signal.aborted) return;
        setBootstrap(result);
        setBootstrapError(null);
        setSelectedTierId(result.preferences.defaultTierId);
        setIsTemporary(result.preferences.temporaryByDefault);
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (cause instanceof ApiError) {
          setBootstrapError(cause);
        } else if (cause instanceof ApiNetworkError) {
          setBootstrapError(
            new ApiError(
              {
                code: "NETWORK",
                severity: "error",
                title: "Can't reach the server",
                body:
                  "We couldn't load your session. Check your connection and try again.",
              },
              0,
            ),
          );
        } else {
          throw cause;
        }
      } finally {
        bootstrapInFlightRef.current = false;
      }
    })();
    return () => {
      controller.abort();
    };
  }, [bootstrapAttempt]);

  // Stable derived bootstrap views — read once per render with `null` fallbacks
  // so the rest of the handler graph stays simple. The render guards below
  // ensure these are never read while `bootstrap === null`.
  const account: AccountInfo | null = bootstrap?.account ?? null;
  const preferences: UserPreferences | null = bootstrap?.preferences ?? null;
  const usage: UsageBudget | null = bootstrap?.usage ?? null;
  const modelTiers: ModelTier[] = bootstrap?.modelTiers ?? [];
  const [conversations, setConversations] = useState<ConversationSummary[]>(
    [],
  );
  // Sync conversation list from bootstrap exactly once it lands. After that,
  // mutations own the list locally (optimistic) and bootstrap is not refetched.
  const conversationsHydratedRef = useRef(false);
  useEffect(() => {
    if (bootstrap && !conversationsHydratedRef.current) {
      conversationsHydratedRef.current = true;
      setConversations(bootstrap.conversations);
    }
  }, [bootstrap]);

  const firstName = useMemo(() => {
    if (!account?.name) return undefined;
    const trimmed = account.name.trim();
    if (!trimmed) return undefined;
    return trimmed.split(/\s+/)[0];
  }, [account]);

  // Commit the finished assistant turn when the stream terminates. We
  // reconcile both the user and assistant ids HERE (terminal-time) rather than
  // on `submitted`: doing both at once keeps the message list mutation single-
  // shot, and a turn that errors out before `submitted` lands still leaves the
  // user bubble visible with its local id (feedback is disabled on errored
  // turns, so the local id is harmless).
  const handleTerminal = useCallback((result: TerminalResult) => {
    const assistantId = assistantIdRef.current;
    if (!assistantId) return;

    const parts: MessagePart[] = [];
    if (result.reasoning) {
      parts.push({
        type: "reasoning",
        text: result.reasoning,
        durationSec: result.reasoningDurationSec,
      });
    }
    if (result.answer) parts.push({ type: "text", text: result.answer });

    const serverAssistantId = result.serverAssistantMessageId ?? assistantId;
    const serverUserId = result.serverUserMessageId;

    const finalized: LocalChatMessage = {
      id: serverAssistantId,
      role: "assistant",
      createdAt: new Date().toISOString(),
      status: result.status,
      feedback: null,
      attribution: result.status === "done" ? result.attribution : undefined,
      parts,
      error: result.status === "error" ? result.error : undefined,
    };

    const optimisticUserId = pendingUserIdRef.current;
    setMessages((prev) => {
      const next = optimisticUserId && serverUserId
        ? prev.map((m) =>
            m.id === optimisticUserId ? { ...m, id: serverUserId } : m,
          )
        : prev;
      return [...next, finalized];
    });

    if (result.status === "done") setLiveMessage("Response ready");
    else if (result.status === "stopped") setLiveMessage("Generation stopped");
    else setLiveMessage("Generation failed");

    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
  }, []);

  const { state, start, stop, reset } = useApiStream(handleTerminal);

  const isStreaming =
    pendingId !== null && (state.status === "submitted" || state.status === "streaming");

  // Begin (or continue) a streamed turn. Shared by send / regenerate / edit.
  // Creates the conversation lazily on the FIRST send when none is active.
  // Returns the conversation id used so callers can fall through their own
  // post-start state updates.
  const beginTurn = useCallback(
    async (args: {
      text: string;
      tierId: ModelTierId;
      regenerate?: boolean;
      editMessageId?: string;
    }): Promise<void> => {
      let conversationId = activeConversationId;
      if (!conversationId) {
        try {
          const created = await createConversation({
            selectedTierId: args.tierId,
            isTemporary,
          });
          conversationId = created.id;
          setActiveConversationId(conversationId);
          // Temporary chats get a synthetic id but bootstrap won't list them;
          // skip sidebar insertion so the rail doesn't gain a row that 404s.
          if (!isTemporary) {
            const summary: ConversationSummary = {
              id: created.id,
              title: created.title,
              updatedAt: new Date().toISOString(),
              pinned: false,
            };
            setConversations((prev) => [summary, ...prev]);
          }
        } catch (cause) {
          const title =
            cause instanceof ApiError ? cause.title : "Couldn't start chat";
          setLiveMessage(title);
          // Roll back the optimistic user bubble we may have just appended.
          const optimisticUserId = pendingUserIdRef.current;
          if (optimisticUserId) {
            setMessages((prev) => prev.filter((m) => m.id !== optimisticUserId));
          }
          pendingUserIdRef.current = null;
          assistantIdRef.current = null;
          setPendingId(null);
          showToast({
            severity: "error",
            title:
              cause instanceof ApiError ? cause.title : "Couldn't create conversation",
            body:
              cause instanceof ApiError
                ? cause.body
                : cause instanceof Error
                  ? cause.message
                  : undefined,
          });
          return;
        }
      }

      start({
        conversationId,
        clientMessageId: crypto.randomUUID(),
        tierId: args.tierId,
        text: args.text,
        isTemporary: isTemporary || undefined,
        regenerate: args.regenerate,
        editMessageId: args.editMessageId,
      });
    },
    [activeConversationId, isTemporary, start],
  );

  const handleSend = (text: string) => {
    const userBubbleId = localId();
    const assistantPlaceholderId = localId();
    tierAtSendRef.current = selectedTierId;
    assistantIdRef.current = assistantPlaceholderId;
    pendingUserIdRef.current = userBubbleId;

    const commitTurn = () => {
      setMessages((prev) => [
        ...prev,
        {
          id: userBubbleId,
          role: "user",
          createdAt: new Date().toISOString(),
          parts: [{ type: "text", text }],
        },
      ]);
      setPendingId(assistantPlaceholderId);
      setLiveMessage("Generating response");
      void beginTurn({ text, tierId: tierAtSendRef.current });
    };

    // Welcome→thread seam: if the welcome surface is showing, run its exit
    // first (200ms) so the user bubble lands into a quiet thread rather than
    // colliding with a still-mounted hero. Decision 11's named designed moment.
    if (messages.length === 0 && !pendingId && !welcomeExiting) {
      setWelcomeExiting(true);
      if (welcomeExitTimerRef.current !== null) {
        window.clearTimeout(welcomeExitTimerRef.current);
      }
      welcomeExitTimerRef.current = window.setTimeout(() => {
        welcomeExitTimerRef.current = null;
        setWelcomeExiting(false);
        setWelcomeSeamLanding(true);
        commitTurn();
        if (welcomeSeamTimerRef.current !== null) {
          window.clearTimeout(welcomeSeamTimerRef.current);
        }
        welcomeSeamTimerRef.current = window.setTimeout(() => {
          welcomeSeamTimerRef.current = null;
          setWelcomeSeamLanding(false);
        }, 400);
      }, 200);
      return;
    }

    commitTurn();
  };

  const handlePromptSelect = (text: string) => {
    composerRef.current?.setDraft(text);
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
    // Skip the API call for messages that haven't been reconciled with a
    // server id yet (e.g. optimistic local-… ids on errored turns). The UI
    // disables actions on non-final turns, so this only catches edge cases.
    if (id.startsWith("local-")) return;
    const previous = messages.find((m) => m.id === id)?.feedback ?? null;
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, feedback: next } : m)),
    );
    void postFeedback(id, next).catch((cause) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, feedback: previous } : m)),
      );
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't save your reaction",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  const handleRegenerate = () => {
    if (isStreaming) return;
    // Drop trailing assistant turn(s), then re-stream a fresh response.
    setMessages((prev) => {
      const next = [...prev];
      while (next.length && next[next.length - 1].role === "assistant") next.pop();
      return next;
    });
    const regenId = localId();
    assistantIdRef.current = regenId;
    pendingUserIdRef.current = null;
    tierAtSendRef.current = selectedTierId;
    setPendingId(regenId);
    setLiveMessage("Regenerating response");
    // Regenerate keeps the trailing user message verbatim — send its text
    // back to the server, which ignores `text` on regenerate but the wire
    // schema still requires it.
    const lastUserText = (() => {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role !== "user") continue;
        for (const p of m.parts) if (p.type === "text") return p.text;
      }
      return "";
    })();
    void beginTurn({
      text: lastUserText,
      tierId: tierAtSendRef.current,
      regenerate: true,
    });
  };

  const handleEditUserMessage = (messageId: string, newText: string) => {
    if (isStreaming) return;
    // Local-only ids belong to user bubbles whose turn never persisted
    // (e.g. a prior error before terminal). The BE rejects non-uuid edit
    // targets with 400, so skip rather than emit a doomed request.
    if (messageId.startsWith("local-")) return;
    const idx = messages.findIndex((m) => m.id === messageId);
    if (idx === -1) return;
    const userBubbleId = localId();
    const assistantPlaceholderId = localId();
    tierAtSendRef.current = selectedTierId;
    assistantIdRef.current = assistantPlaceholderId;
    pendingUserIdRef.current = userBubbleId;
    setMessages((prev) => [
      ...prev.slice(0, idx),
      {
        id: userBubbleId,
        role: "user",
        createdAt: new Date().toISOString(),
        parts: [{ type: "text", text: newText }],
      },
    ]);
    setPendingId(assistantPlaceholderId);
    setLiveMessage("Generating response");
    void beginTurn({
      text: newText,
      tierId: tierAtSendRef.current,
      editMessageId: messageId,
    });
  };

  // Branch-from-here (PRD 01 §4.6 P1) is deferred until the BE exposes a
  // copy-messages-on-create primitive. Shipping the button against the
  // current `POST /api/conversations` (which only accepts `selectedTierId`
  // + `isTemporary`) created an empty new chat and called it "branched" —
  // a UX lie. The action is removed from MessageActions until either the
  // create endpoint accepts an `initialMessages` payload or a dedicated
  // `/branch` route lands; re-adding the button without that wire is a
  // correctness regression, not a feature gain.

  const handleNewChat = () => {
    // Cancel any in-flight welcome→thread seam (see handleSelectConversation
    // for the corruption shape). New chat nulls activeConversationId, so a
    // pending exit timer firing here would commitTurn() into the wrong
    // (newly-empty) state.
    if (welcomeExitTimerRef.current !== null) {
      window.clearTimeout(welcomeExitTimerRef.current);
      welcomeExitTimerRef.current = null;
    }
    if (welcomeSeamTimerRef.current !== null) {
      window.clearTimeout(welcomeSeamTimerRef.current);
      welcomeSeamTimerRef.current = null;
    }
    setWelcomeExiting(false);
    setWelcomeSeamLanding(false);
    if (isStreaming) reset();
    setMessages([]);
    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
    setLiveMessage("");
    reset();
    setActiveConversationId(null);
    if (preferences) {
      setSelectedTierId(preferences.defaultTierId);
      setIsTemporary(preferences.temporaryByDefault);
    }
    setSelectedReasoningEffortId("auto");
    setMobileNavOpen(false);
  };

  // Header Ghost / banner toggle. Turning Temporary ON starts a FRESH temporary
  // chat (clears like New chat) so the "won't be saved" promise is always true.
  // Turning it OFF just exits temporary mode and keeps the current messages —
  // any subsequent send creates a real (persisted) conversation lazily.
  const handleToggleTemporary = () => {
    if (isTemporary) {
      setIsTemporary(false);
      return;
    }
    if (isStreaming) reset();
    setMessages([]);
    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
    setLiveMessage("");
    reset();
    setActiveConversationId(null);
    if (preferences) setSelectedTierId(preferences.defaultTierId);
    setSelectedReasoningEffortId("auto");
    setIsTemporary(true);
    setMobileNavOpen(false);
  };

  const handleSelectConversation = (id: string) => {
    // Cancel any in-flight welcome→thread seam. Without this, an exit timer
    // scheduled against the previous (empty) conversation would fire after we
    // switch — calling commitTurn() with the closure-captured `text` and
    // appending a stale user bubble into the just-selected conversation's
    // messages, plus kicking off a stream for it. That's data corruption, not
    // just a visual glitch. The same clear runs in handleNewChat /
    // handleDeleteConversation paths that null `activeConversationId`.
    if (welcomeExitTimerRef.current !== null) {
      window.clearTimeout(welcomeExitTimerRef.current);
      welcomeExitTimerRef.current = null;
    }
    if (welcomeSeamTimerRef.current !== null) {
      window.clearTimeout(welcomeSeamTimerRef.current);
      welcomeSeamTimerRef.current = null;
    }
    setWelcomeExiting(false);
    setWelcomeSeamLanding(false);
    if (isStreaming) reset();
    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
    setLiveMessage("");
    reset();
    setActiveConversationId(id);
    setIsTemporary(false);
    setMobileNavOpen(false);
    // Show empty until the server payload lands; then populate. A faster
    // subsequent selection will overwrite `selectConversationToken`, and the
    // in-flight response below checks it before committing — late responses
    // for an abandoned id are dropped.
    setMessages([]);
    selectConversationTokenRef.current = id;
    void (async () => {
      try {
        const conversation = await fetchConversation(id);
        if (selectConversationTokenRef.current !== id) return;
        setMessages(conversation.messages);
        setSelectedTierId(conversation.selectedTierId);
      } catch (cause) {
        if (selectConversationTokenRef.current !== id) return;
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't load chat";
        setLiveMessage(title);
        showToast({
          severity: "error",
          title:
            cause instanceof ApiError ? cause.title : "Couldn't load conversation",
          body:
            cause instanceof ApiError
              ? cause.body
              : cause instanceof Error
                ? cause.message
                : undefined,
        });
      }
    })();
  };

  const handleRenameConversation = (id: string, newTitle: string) => {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    const previous = conversations;
    const target = previous.find((c) => c.id === id);
    if (!target || target.title === trimmed) return;
    const nowIso = new Date().toISOString();
    setConversations((prev) =>
      prev.map((c) =>
        c.id === id ? { ...c, title: trimmed, updatedAt: nowIso } : c,
      ),
    );
    void patchConversation(id, { title: trimmed }).catch((cause) => {
      setConversations(previous);
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't rename conversation",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  const handleDeleteConversation = (id: string) => {
    const previous = conversations;
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (id === activeConversationId) {
      // Cancel any in-flight welcome→thread seam — same data-corruption guard
      // as handleSelectConversation / handleNewChat, since we're nulling
      // activeConversationId here too.
      if (welcomeExitTimerRef.current !== null) {
        window.clearTimeout(welcomeExitTimerRef.current);
        welcomeExitTimerRef.current = null;
      }
      if (welcomeSeamTimerRef.current !== null) {
        window.clearTimeout(welcomeSeamTimerRef.current);
        welcomeSeamTimerRef.current = null;
      }
      setWelcomeExiting(false);
      setWelcomeSeamLanding(false);
      if (isStreaming) reset();
      setMessages([]);
      setPendingId(null);
      assistantIdRef.current = null;
      pendingUserIdRef.current = null;
      setLiveMessage("");
      reset();
      setActiveConversationId(null);
    }
    void deleteConversation(id).catch((cause) => {
      setConversations(previous);
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't delete conversation",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  const handleTogglePinConversation = (id: string) => {
    const previous = conversations;
    const target = previous.find((c) => c.id === id);
    if (!target) return;
    const nextPinned = !target.pinned;
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, pinned: nextPinned } : c)),
    );
    void patchConversation(id, { pinned: nextPinned }).catch((cause) => {
      setConversations(previous);
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't pin conversation",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  const handlePreferencesChange = (next: UserPreferences) => {
    if (!bootstrap) return;
    const previous = bootstrap.preferences;
    setBootstrap({ ...bootstrap, preferences: next });
    void putPreferences(next).catch((cause) => {
      setBootstrap((prev) =>
        prev ? { ...prev, preferences: previous } : prev,
      );
      if (cause instanceof ApiError) setLiveMessage(cause.title);
    });
  };

  const handleAccountChange = (next: AccountInfo) => {
    setBootstrap((prev) => (prev ? { ...prev, account: next } : prev));
  };

  // Sign-out + full reload so bootstrap re-runs against the fresh anonymous
  // session the backend mints on the cookieless follow-up request.
  const handleSignOut = () => {
    void postAuthSignout()
      .then(() => {
        setLiveMessage("Signed out");
        if (typeof window !== "undefined") window.location.reload();
      })
      .catch((cause) => {
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't sign out";
        const body =
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined;
        showToast({ severity: "error", title, body });
      });
  };

  const showWelcome =
    (messages.length === 0 && !pendingMessage) || welcomeExiting;

  // Clear the pending welcome-exit timer if the component unmounts mid-seam
  // (e.g. user closes the tab during the 200ms exit).
  useEffect(() => {
    return () => {
      if (welcomeExitTimerRef.current !== null) {
        window.clearTimeout(welcomeExitTimerRef.current);
      }
      if (welcomeSeamTimerRef.current !== null) {
        window.clearTimeout(welcomeSeamTimerRef.current);
      }
    };
  }, []);

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

  // Whole-conversation copy-as-markdown (PRD 01 §4.10 P0). Local copy is
  // exempt from the public-share cost/token redaction rule (PRD 07 §6.4) —
  // attribution metadata stays on the in-app message rows; the markdown
  // payload itself is just turns and content so it round-trips cleanly into
  // notes/docs/issues. Reasoning parts are intentionally omitted: they're a
  // streaming-time disclosure and dump noisily when copied. Pending and
  // errored assistant turns are skipped — the markdown should represent the
  // settled thread, not a half-streamed snapshot.
  const renderConversationMarkdown = (
    source: ReadonlyArray<ChatMessage>,
  ): string => {
    const turns: string[] = [];
    for (const m of source) {
      if (m.role === "assistant" && (m.status === "error" || m.status === "submitted" || m.status === "streaming")) {
        continue;
      }
      const text = m.parts
        .filter((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
        .map((p) => p.text)
        .join("\n\n")
        .trim();
      if (!text) continue;
      turns.push(`**${m.role === "user" ? "You" : "Assistant"}**\n\n${text}`);
    }
    return turns.join("\n\n---\n\n");
  };

  const writeMarkdownToClipboard = (payload: string): void => {
    if (!payload) {
      setLiveMessage("Nothing to copy");
      showToast({ severity: "info", title: "Nothing to copy" });
      return;
    }
    void navigator.clipboard?.writeText(payload).then(
      () => {
        setLiveMessage("Conversation copied");
        showToast({ severity: "info", title: "Conversation copied" });
      },
      () => {
        setLiveMessage("Copy failed");
        showToast({ severity: "error", title: "Copy failed" });
      },
    );
  };

  const handleCopyConversation = () => {
    writeMarkdownToClipboard(renderConversationMarkdown(messages));
  };

  // Sidebar kebab path — works for any row. Fast-path the active conversation
  // off the in-memory `messages` so the user doesn't pay a round-trip when
  // they copy what they're already looking at; non-active rows fetch and copy.
  const handleCopyConversationById = (id: string) => {
    if (id === activeConversationId) {
      handleCopyConversation();
      return;
    }
    void (async () => {
      try {
        const conversation = await fetchConversation(id);
        writeMarkdownToClipboard(renderConversationMarkdown(conversation.messages));
      } catch (cause) {
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't copy conversation";
        setLiveMessage(title);
        showToast({
          severity: "error",
          title,
          body:
            cause instanceof ApiError
              ? cause.body
              : cause instanceof Error
                ? cause.message
                : undefined,
        });
      }
    })();
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

  // --- Render guards ------------------------------------------------------
  // Bootstrap is the gate: nothing renders the main shell until we have the
  // account + preferences + tier registry. Both states are intentionally tiny
  // — there's no FE auth surface, so the user can't recover from a failure
  // other than retrying.

  if (bootstrapError) {
    return (
      <div className="flex h-full min-h-svh items-center justify-center p-6">
        <div className="max-w-sm space-y-4 text-center">
          <h2 className="text-lg font-semibold">{bootstrapError.title}</h2>
          <p className="text-sm text-muted-foreground">{bootstrapError.body}</p>
          <Button
            type="button"
            onClick={() => {
              setBootstrapError(null);
              setBootstrapAttempt((n) => n + 1);
            }}
            className="rounded-full"
          >
            Try again
          </Button>
        </div>
      </div>
    );
  }

  if (!bootstrap || !account || !preferences || !usage) {
    return <div aria-hidden className="h-full min-h-svh" />;
  }

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            conversations={conversations}
            activeId={activeConversationId}
            account={account}
            search={conversationSearch}
            onSearchChange={setConversationSearch}
            onSelect={handleSelectConversation}
            onNewChat={handleNewChat}
            onRenameConversation={handleRenameConversation}
            onDeleteConversation={handleDeleteConversation}
            onTogglePinConversation={handleTogglePinConversation}
            onCopyConversation={handleCopyConversationById}
            onOpenSettings={() => setSettingsOpen(true)}
            onSignOut={handleSignOut}
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
          <div className="pointer-events-none absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-background via-background/85 to-background/0 pt-[env(safe-area-inset-top)] pr-[env(safe-area-inset-right)] pb-6 pl-[env(safe-area-inset-left)] md:pb-12">
            <div className="pointer-events-auto">
              <AppHeader
                sidebarOpen={sidebarOpen}
                onOpenMobileNav={() => setMobileNavOpen(true)}
                onOpenSidebar={() => setSidebarOpen(true)}
                onNewChat={handleNewChat}
                onOpenSettings={() => setSettingsOpen(true)}
                isTemporary={isTemporary}
                onToggleTemporary={handleToggleTemporary}
                onCopyConversation={handleCopyConversation}
                canCopyConversation={messages.length > 0}
                tiers={modelTiers}
                selectedTierId={selectedTierId}
                onSelectTier={setSelectedTierId}
                efforts={REASONING_EFFORTS}
                selectedEffortId={selectedReasoningEffortId}
                onSelectEffort={setSelectedReasoningEffortId}
              />
              {isTemporary ? (
                <TemporaryChatBanner onTurnOff={handleToggleTemporary} />
              ) : null}
            </div>
          </div>

          {/* Message area — for WelcomeScreen we put a single scroll wrapper
              that clears both strips. For MessageList we let it own its
              scroll (its internal `<ol>` already has matching pt/pb that
              clears the chrome). */}
          {showWelcome ? (
            // Welcome state is the canonical Ma surface (Decision 11; Spacing §Ma).
            // Padding on each side equals the chrome floor it must clear, so the
            // greeting sits at the true visual center of the uncovered area —
            // not biased toward either the header or the composer.
            <div
              className={
                isTemporary
                  ? "min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+7rem)] pr-[env(safe-area-inset-right)] pb-[calc(var(--bottom-inset)+7rem)] pl-[env(safe-area-inset-left)] md:pt-[calc(env(safe-area-inset-top)+9rem)] md:pb-[calc(var(--bottom-inset)+9rem)]"
                  : "min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+5.5rem)] pr-[env(safe-area-inset-right)] pb-[calc(var(--bottom-inset)+7rem)] pl-[env(safe-area-inset-left)] md:pt-[calc(env(safe-area-inset-top)+7rem)] md:pb-[calc(var(--bottom-inset)+9rem)]"
              }
            >
              <WelcomeScreen
                userName={firstName}
                exiting={welcomeExiting}
                onPromptSelect={handlePromptSelect}
              />
            </div>
          ) : (
            <div
              className={
                welcomeSeamLanding
                  ? "flex min-h-0 flex-1 flex-col animate-welcome-enter"
                  : "flex min-h-0 flex-1 flex-col"
              }
            >
              <MessageList>
                {messages.map((m) =>
                  m.role === "user" ? (
                    <UserMessage
                      key={m.id}
                      message={m}
                      canEdit={!isStreaming && !m.id.startsWith("local-")}
                      onEdit={(newText) => handleEditUserMessage(m.id, newText)}
                    />
                  ) : (
                    <AssistantMessage
                      key={m.id}
                      message={m}
                      status={m.status ?? "done"}
                      canRegenerate={!isStreaming && m.id === lastAssistantId && ((m.status ?? "done") === "done" || m.status === "stopped")}
                      onRegenerate={handleRegenerate}
                      onFeedback={(f) => setFeedback(m.id, f)}
                      defaultReasoningOpen={preferences.autoExpandReasoning}
                      error={m.error}
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
            </div>
          )}

          {/* Bottom chrome strip — opaque at the bottom edge, fades upward. */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-background via-background/85 to-background/0 pt-6 pr-[env(safe-area-inset-right)] pb-[var(--bottom-inset)] pl-[env(safe-area-inset-left)]">
            <div className="pointer-events-auto">
              <Composer
                ref={composerRef}
                isStreaming={isStreaming}
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
        onPreferencesChange={handlePreferencesChange}
        account={account}
        onAccountChange={handleAccountChange}
        usage={usage}
        onSignOut={handleSignOut}
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
              autoFocus
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
