"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import {
  Activity as ActivityIcon,
  Boxes,
  Brain,
  ClipboardCopy,
  Code2,
  Columns2,
  DollarSign,
  FileText,
  FolderPlus,
  KeyRound,
  LoaderCircle,
  MessageSquarePlus,
  Mic,
  PanelLeft,
  Settings as SettingsIcon,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Tag as TagIcon,
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
import { ModelModePicker } from "@/components/chat/model-mode-picker";
import { MessageList } from "@/components/chat/message-list";
import { UserMessage } from "@/components/chat/user-message";
import { AssistantMessage } from "@/components/chat/assistant-message";
import { WelcomeScreen } from "@/components/chat/welcome-screen";
import { TemporaryChatBanner } from "@/components/chat/temporary-chat-banner";
import { DegradedStatusBanner } from "@/components/chat/degraded-status-banner";
import {
  SettingsDialog,
  type SettingsTab,
} from "@/components/chat/settings-dialog";
import { AuthDialog } from "@/components/chat/auth-dialog";
import { ShareDialog } from "@/components/chat/share-dialog";
import { AiDisclosure } from "@/components/chat/ai-disclosure";
import { Composer, type ComposerHandle } from "@/components/chat/composer";
import {
  CompareTierBar,
  CompareView,
  type CompareTurn,
  type CompareViewHandle,
} from "@/components/chat/compare-view";
import { LiveRegion } from "@/components/chat/live-region";
import { showToast } from "@/components/ui/toast";
import {
  CHAT_CHROME_PAD_CLASS,
  topChromePaddingStyle,
} from "@/lib/chat-chrome-padding";
import { cn } from "@/lib/utils";
import {
  CommandPalette,
  type CommandAction,
} from "@/components/chat/command-palette";
import type { ShortcutSection } from "@/components/chat/shortcuts-dialog";
import {
  useKeyboardShortcuts,
  type Shortcut,
} from "@/lib/use-keyboard-shortcuts";
import {
  clearOverride,
  defaultsFromBindings,
  deserializeShortcuts,
  resetAllOverrides,
  resolveBindings,
  serializeShortcuts,
  setOverride,
  type RebindableBinding,
} from "@/lib/shortcut-defaults";
import {
  useApiStream,
  type SubagentActivity,
  type TerminalResult,
} from "@/lib/stream-client";
import {
  ApiError,
  ApiNetworkError,
  branchConversation,
  bulkConversationAction,
  createConversation,
  deleteAccount,
  deleteConversation,
  createProject,
  createTag,
  deleteProject,
  deleteTag,
  fetchAccountExport,
  fetchBootstrap,
  fetchConversation,
  patchConversation,
  postFeedback,
  postAuthSignout,
  putPreferences,
  searchConversations,
  updateProject,
  updateTag,
  type BootstrapResponse,
  type ProjectUpdateInput,
} from "@/lib/apiClient";
import { REASONING_EFFORTS } from "@/lib/reasoning-efforts";
import { reportTelemetry } from "@/lib/telemetry";
import { isAnonymousAccount } from "@/lib/types";
import type {
  AccountInfo,
  AgenticMode,
  AttachmentPart,
  ChatMessage,
  ConversationSummary,
  Feedback,
  KeyboardShortcuts,
  MessagePart,
  ModelTier,
  ModelTierId,
  Project,
  ProviderTierOption,
  ReasoningEffortId,
  ShortcutId,
  Tag,
  UsageBudget,
  UserPreferences,
} from "@/lib/types";

// `KEY_BINDINGS` carries the static keystroke metadata; `runAction(id)` owns
// the live handler. The split keeps the descriptor array free of state
// closures, which the React Compiler would otherwise flag as ref-tainted.
// `ShortcutId` is the persistence-safe action id union, shared from `types.ts`
// so the override map / rebind dialog / resolver agree on it (D23).
type KeyBinding = RebindableBinding;
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
    id: "toggle-dictation",
    label: "Toggle dictation",
    key: "D",
    mod: true,
    shift: true,
    // Fires while the composer textarea is focused — dictation is composer-
    // centric, so the user is typically focused there when toggling it.
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

// The built-in default keystroke for every action, keyed by id. This is the
// merge base for the user's `keyboardShortcuts` overrides (D23); the EFFECTIVE
// bindings (defaults + overrides) drive the live matcher, palette, and dialog.
const DEFAULT_BINDINGS = defaultsFromBindings(KEY_BINDINGS);

// Human label per action id (stable; never overridden).
const LABEL_BY_ID = ((): Record<ShortcutId, string> => {
  const out = {} as Record<ShortcutId, string>;
  for (const b of KEY_BINDINGS) out[b.id] = b.label;
  // Palette-only actions have no KEY_BINDINGS entry; label them here.
  out["open-settings"] = "Open settings";
  out["toggle-theme"] = "Toggle theme";
  out["search-history"] = "Search history";
  return out;
})();

// Palette rows. "Hidden" entries (the palette itself) are omitted; settings/
// theme entries are palette-only (`hasBinding: false` ⇒ no global shortcut, so
// no keycap hint). The effective keystroke is resolved at render from the live
// bindings, not baked in here.
const PALETTE_ACTION_META: Array<{
  id: ShortcutId;
  label: string;
  icon: CommandAction["icon"];
  section: "Actions" | "Settings";
  hasBinding: boolean;
}> = [
  { id: "new-chat", label: "New chat", icon: MessageSquarePlus, section: "Actions", hasBinding: true },
  { id: "focus-composer", label: "Focus composer", icon: TextCursorInput, section: "Actions", hasBinding: true },
  { id: "copy-last-response", label: "Copy last response", icon: ClipboardCopy, section: "Actions", hasBinding: true },
  { id: "copy-last-code", label: "Copy last code block", icon: Code2, section: "Actions", hasBinding: true },
  { id: "toggle-sidebar", label: "Toggle sidebar", icon: PanelLeft, section: "Actions", hasBinding: true },
  { id: "delete-chat", label: "Delete current chat", icon: Trash2, section: "Actions", hasBinding: true },
  { id: "toggle-dictation", label: "Toggle dictation", icon: Mic, section: "Actions", hasBinding: true },
  { id: "custom-instructions", label: "Open custom instructions", icon: Sparkles, section: "Settings", hasBinding: true },
  { id: "shortcuts", label: "Show all shortcuts", icon: KeyRound, section: "Settings", hasBinding: true },
  { id: "open-settings", label: "Open settings", icon: SettingsIcon, section: "Settings", hasBinding: false },
  { id: "toggle-theme", label: "Toggle theme", icon: Sun, section: "Settings", hasBinding: false },
];

// Keyword aliases for the shortcut-bound palette rows so type-to-find lands
// them from synonyms / destination names that aren't in the visible label.
const PALETTE_ACTION_KEYWORDS: Partial<Record<ShortcutId, string[]>> = {
  shortcuts: ["shortcuts", "keyboard", "keys", "hotkeys", "bindings"],
  "custom-instructions": ["custom instructions", "system prompt", "persona"],
  "open-settings": ["settings", "preferences", "options"],
  "new-chat": ["new chat", "new conversation"],
  "toggle-theme": ["theme", "dark mode", "light mode", "appearance"],
};

// Shortcuts dialog grouping. Ordered to match the PRD §5.5 table loosely:
// general (palette/shortcuts/custom-instructions) → navigation → editing.
const SHORTCUT_DIALOG_SECTIONS: { heading: string; ids: ShortcutId[] }[] = [
  { heading: "General", ids: ["palette", "shortcuts", "custom-instructions"] },
  { heading: "Navigation", ids: ["new-chat", "focus-composer", "toggle-sidebar"] },
  { heading: "Editing", ids: ["copy-last-response", "copy-last-code", "toggle-dictation", "delete-chat"] },
];

// Every rebindable action surfaced in the shortcuts dialog (= the union of all
// section ids). Used to validate/coerce a deserialized override map and to drive
// duplicate detection across the full set.
const REBINDABLE_IDS: ShortcutId[] = SHORTCUT_DIALOG_SECTIONS.flatMap(
  (section) => section.ids,
);

// Local-only id generator for optimistic message bubbles before the server
// echoes the real uuid. Never sent to the server (clientMessageId uses
// crypto.randomUUID() instead). Replaced on terminal via reconciliation.
let localIdCounter = 0;
const localId = (): string => `local-${Date.now()}-${localIdCounter++}`;

// In-memory message variant. ChatMessage is the canonical wire/persisted shape;
// `error` is FE-only state from a stream-terminal error frame and never
// round-trips to the server.
type LocalChatMessage = ChatMessage & { error?: ApiError };
type ConversationSearchState = {
  query: string;
  results: ConversationSummary[] | null;
  pending: boolean;
};

// Default tier when bootstrap is still pending — only used to seed the picker
// for the brief loading frame; replaced by `preferences.defaultTierId` once
// bootstrap resolves.
const DEFAULT_TIER_ID: ModelTierId = "auto";
const PREFERRED_PROVIDER_STORAGE_KEY = "olune.preferredProviderId";

// Upper bound on the first-paint bootstrap fetch. The production BE scales to
// zero (Fly + Neon), so the first hit after an idle spell boots a machine + a
// cold DB before any response — generous enough to clear a normal cold start
// (~5–20 s) yet short enough that a genuinely stalled boot surfaces the retry
// UI instead of an unbounded spinner ("the page keeps loading").
const BOOTSTRAP_TIMEOUT_MS = 30_000;

function readStoredPreferredProviderId(): string | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.localStorage.getItem(PREFERRED_PROVIDER_STORAGE_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

function storePreferredProviderId(providerId: string | undefined): void {
  if (typeof window === "undefined") return;
  try {
    if (providerId) {
      window.localStorage.setItem(PREFERRED_PROVIDER_STORAGE_KEY, providerId);
    } else {
      window.localStorage.removeItem(PREFERRED_PROVIDER_STORAGE_KEY);
    }
  } catch {
    // Storage can be disabled in private contexts; provider selection still
    // works for the current session through React state.
  }
}

function activeProviderOptionForTier(tier: ModelTier): ProviderTierOption {
  return {
    providerId: tier.providerId,
    label: tier.providerLabel,
    status: tier.providerRouteStatus,
    modelLabel: tier.modelLabel,
    supportsWebSearch: tier.supportsWebSearch,
    supportsAttachments: tier.supportsAttachments,
    defaultRouteEligible: tier.defaultRouteEligible,
    dataPolicy: tier.dataPolicy,
    listPriceInPerM: tier.listPriceInPerM,
    listPriceOutPerM: tier.listPriceOutPerM,
  };
}

function providerOptionsForTier(tier: ModelTier | undefined): ProviderTierOption[] {
  if (!tier) return [];
  const nested = tier.providerOptions ?? [];
  if (nested.some((option) => option.providerId === tier.providerId)) {
    return nested;
  }
  return [activeProviderOptionForTier(tier), ...nested];
}

function providerOptionForTier(
  tier: ModelTier | undefined,
  preferredProviderId?: string,
): ProviderTierOption | undefined {
  const options = providerOptionsForTier(tier);
  return (
    options.find(
      (option) =>
        option.providerId === preferredProviderId && option.status === "available",
    ) ??
    options.find(
      (option) => option.providerId === tier?.providerId && option.status === "available",
    ) ??
    options.find(
      (option) => option.defaultRouteEligible && option.status === "available",
    ) ??
    options.find((option) => option.status === "available") ??
    options[0]
  );
}

function effectiveTierForProvider(
  tier: ModelTier,
  preferredProviderId?: string,
): ModelTier {
  const option = providerOptionForTier(tier, preferredProviderId);
  if (!option) return tier;
  return {
    ...tier,
    providerId: option.providerId,
    providerLabel: option.label,
    providerRouteStatus: option.status,
    defaultRouteEligible: option.defaultRouteEligible,
    dataPolicy: option.dataPolicy,
    modelLabel: option.modelLabel,
    supportsWebSearch: option.supportsWebSearch,
    supportsAttachments: option.supportsAttachments,
    listPriceInPerM: option.listPriceInPerM,
    listPriceOutPerM: option.listPriceOutPerM,
  };
}

function providerOptionForTierId(
  tiers: ModelTier[],
  tierId: ModelTierId,
  preferredProviderId?: string,
): ProviderTierOption | undefined {
  return providerOptionForTier(
    tiers.find((tier) => tier.id === tierId),
    preferredProviderId,
  );
}

type ToolTranscriptPart = Extract<
  MessagePart,
  { type: "tool_call" | "tool_result" }
>;

// Mirror the BE's persisted agentic layout (`_build_agentic_parts` in
// api/app/streaming/handler.py): per subagent in first-seen order — a
// `subagent` marker (role + per-subagent cost), its tagged reasoning, its
// tagged tool transcript, then its tagged answer text. Shared by the live
// pendingMessage and the terminal commit so the streaming bubble, the committed
// bubble, and a reloaded transcript all render identically.
function buildSubagentParts(
  subagents: SubagentActivity[],
  toolParts: ToolTranscriptPart[],
): MessagePart[] {
  const parts: MessagePart[] = [];
  for (const sub of subagents) {
    parts.push({
      type: "subagent",
      subagentId: sub.subagentId,
      label: sub.label,
      role: sub.role,
      ...(sub.costUsd !== undefined ? { costUsd: sub.costUsd } : {}),
    });
    if (sub.reasoning) {
      parts.push({
        type: "reasoning",
        text: sub.reasoning,
        subagentId: sub.subagentId,
      });
    }
    for (const toolPart of toolParts) {
      if (toolPart.subagentId === sub.subagentId) parts.push(toolPart);
    }
    if (sub.answer) {
      parts.push({ type: "text", text: sub.answer, subagentId: sub.subagentId });
    }
  }
  return parts;
}

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
  const [selectedProviderId, setSelectedProviderId] = useState<string | undefined>(
    undefined,
  );
  const [selectedReasoningEffortId, setSelectedReasoningEffortId] =
    useState<ReasoningEffortId>("auto");
  // Composer web-search toggle. Only ever sent (and only ever togglable) when
  // the selected tier supports web search; switching to a non-supporting tier
  // clears it (see the effect below), so an off-tier turn can never carry it.
  const [searchEnabled, setSearchEnabled] = useState(false);
  // Captured at send-time alongside the tier so a mid-stream toggle can't
  // retroactively change what this turn requested.
  const searchAtSendRef = useRef(false);
  // Composer JSON-mode (structured-output) toggle. Unlike web search this is
  // NOT tier-gated — every tier accepts it (the BE handles provider-specific
  // best-effort), so there is no clearing-on-tier-switch effect. Purely
  // ephemeral session state, mirroring `searchEnabled`.
  const [jsonModeEnabled, setJsonModeEnabled] = useState(false);
  // Captured at send-time so a mid-stream toggle can't retroactively change
  // what this turn requested (mirrors `searchAtSendRef`).
  const jsonModeAtSendRef = useRef(false);
  // Composer Deep Research (agentic) toggle. Only offered — and only ever
  // sent — when the bootstrap advertised `agenticEnabled`; against a flag-off
  // server the picker hides the toggle and the wire never carries the mode.
  // Not tier-gated (any tier can orchestrate), so no clearing-on-tier-switch
  // effect. Ephemeral session state, mirroring `jsonModeEnabled`.
  const [deepResearchEnabled, setDeepResearchEnabled] = useState(false);
  // Captured at send-time so a mid-stream toggle can't retroactively change
  // what this turn requested (mirrors `searchAtSendRef`).
  const deepResearchAtSendRef = useRef(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState("");
  const tierAtSendRef = useRef<ModelTierId>(selectedTierId);
  const providerAtSendRef = useRef<string | undefined>(selectedProviderId);
  // Captured at send-time alongside the tier/provider so a mid-stream effort
  // change can't retroactively alter what this turn requested (mirrors
  // tierAtSendRef / searchAtSendRef).
  const effortAtSendRef = useRef<ReasoningEffortId>(selectedReasoningEffortId);
  const selectedTierIdRef = useRef<ModelTierId>(selectedTierId);
  const selectedProviderIdRef = useRef<string | undefined>(selectedProviderId);
  // Live mirror of the project context for a NEW chat (D20), so the send path's
  // `useCallback` reads the current value without re-creating on every list
  // change. Synced in an effect once `activeProjectId` is derived below.
  const activeProjectIdRef = useRef<string | null>(null);
  // The optimistic id of the user message we just sent — set on send, cleared
  // on terminal (after we replace it with the server-issued uuid). Reconciling
  // user + assistant ids happens together on the `terminal` callback so the
  // message list and feedback POSTs always reference server-issued ids.
  const pendingUserIdRef = useRef<string | null>(null);
  const assistantIdRef = useRef<string | null>(null);
  // Set true when Stop is pressed during the pre-stream window (welcome-exit
  // timer or the createConversation round-trip, before `start()` has armed a
  // real AbortController). `beginTurn` checks this after the await resolves and
  // bails out of `start()` so an early Stop cleanly cancels the turn. (P0-1)
  const abortBeforeStartRef = useRef(false);
  // Latest in-flight `fetchConversation` request id; the load callback drops
  // its response if a faster selection has since superseded it.
  const selectConversationTokenRef = useRef<string | null>(null);
  const composerRef = useRef<ComposerHandle>(null);

  // --- Compare mode (parallel model comparison) -------------------------------
  // Flagship multi-model differentiator: one prompt → two tiers answer side by
  // side, each column streaming independently with its own answer + cost
  // attribution. Entirely TRANSIENT — a single temporary conversation backs the
  // fan-out (so its id is never persisted/listed), and no compare turn ever
  // commits into `messages` or the sidebar.
  const [compareMode, setCompareMode] = useState(false);
  // The two tiers being compared, in column order. Seeded once compare turns on
  // (see handleToggleCompare) so the two slots start DISTINCT.
  const [compareTierIds, setCompareTierIds] = useState<
    [ModelTierId, ModelTierId]
  >(["fast", "pro"]);
  // The active fan-out turn handed to CompareView, or null before the first
  // compare send. The `token` makes each send fire the fan-out exactly once.
  const [compareTurn, setCompareTurn] = useState<CompareTurn | null>(null);
  // The compare prompt bubble, rendered above the columns. Transient.
  const [compareUserMessage, setCompareUserMessage] =
    useState<ChatMessage | null>(null);
  const compareTokenRef = useRef(0);
  const compareViewRef = useRef<CompareViewHandle>(null);
  // True while any compare column is streaming — drives the composer Stop morph.
  const [compareStreaming, setCompareStreaming] = useState(false);

  // Chrome state: sidebar (desktop rail + mobile drawer), settings, prefs,
  // temporary mode, and which conversation is active.
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Which Settings hub tab to land on when it opens. Memory/Templates/Models/
  // Shortcuts/Activity are folded into the hub as tabs, so deep-links (the
  // "Memory used here" chip, the shortcuts hotkey) set this before opening.
  const [settingsInitialTab, setSettingsInitialTab] =
    useState<SettingsTab>("general");
  // Advanced history search is now folded into the command palette's filter
  // mode (no separate dialog). When the host summons the palette for search —
  // from the sidebar "Advanced search" affordance or the search-history
  // shortcut — it flips this so the palette opens straight into filter mode.
  const [paletteFilterMode, setPaletteFilterMode] = useState(false);
  // Quick-create surface summoned from the command palette ("New project" /
  // "New tag"). The sidebar owns its own inline create dialog; this is the
  // palette's equivalent entry point so those destinations are reachable from
  // the universal action spine without the sidebar being open. It does NOT
  // duplicate the create logic — it reuses `handleCreateProject` /
  // `handleCreateTag` — and uses the shared Base UI Dialog (focus trap + Esc +
  // focus-restore + reduced-motion all inherited).
  const [paletteCreate, setPaletteCreate] = useState<
    null | "project" | "tag"
  >(null);
  const [paletteCreateDraft, setPaletteCreateDraft] = useState("");
  const [authOpen, setAuthOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [isTemporary, setIsTemporary] = useState(false);
  // Lifted from DegradedStatusBanner so the two top status pills can share one
  // prioritized slot (degraded > temporary) instead of stacking into a
  // multi-banner wall. The banner stays always-mounted and self-renders null.
  const [degradedActive, setDegradedActive] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [conversationSearch, setConversationSearch] = useState("");
  const [conversationSearchState, setConversationSearchState] =
    useState<ConversationSearchState | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Both the shortcut and the palette's "Delete current chat" route through
  // this confirm — never delete without it (data-loss guard).
  const [pendingDeleteConversationId, setPendingDeleteConversationId] =
    useState<string | null>(null);
  const [branchingMessageId, setBranchingMessageId] = useState<string | null>(
    null,
  );
  const [pendingDeleteAccount, setPendingDeleteAccount] = useState(false);
  // Type-to-confirm value for the delete-account dialog. The BE requires the
  // caller to echo their email (or "DELETE" when anonymous) — see
  // handleDeleteAccount / the delete confirm dialog below.
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
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

  useEffect(() => {
    selectedTierIdRef.current = selectedTierId;
  }, [selectedTierId]);

  useEffect(() => {
    selectedProviderIdRef.current = selectedProviderId;
  }, [selectedProviderId]);

  // Bootstrap fetch — single trip on mount (and on retry). The in-flight ref
  // short-circuits StrictMode's double-mount in dev: AbortController alone
  // doesn't help because the BE assigns an anonymous user on the cookieless
  // first hit BEFORE the response arrives, so a second concurrent request
  // would mint a second user row even if we discard its response.
  const bootstrapInFlightRef = useRef(false);
  // Holds the live bootstrap AbortController so the "Try again" handler can
  // abort a genuinely in-flight request and clear the in-flight latch before
  // bumping `bootstrapAttempt` — otherwise the re-run sees `inFlight === true`
  // (the prior async `finally` hasn't run yet) and returns without retrying,
  // so retry looks dead. (P1-5)
  const bootstrapControllerRef = useRef<AbortController | null>(null);
  useEffect(() => {
    if (bootstrapInFlightRef.current) return;
    bootstrapInFlightRef.current = true;
    const controller = new AbortController();
    bootstrapControllerRef.current = controller;
    // Cold-start guard: bound the request so a slow/stalled cold boot can't
    // strand the user on an indefinite first-paint spinner. On timeout we abort
    // and fall through to the retry UI below — a now-warm machine answers the
    // retry quickly. `timedOut` distinguishes this abort from the unmount /
    // explicit-retry aborts (which stay silent).
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, BOOTSTRAP_TIMEOUT_MS);
    void (async () => {
      try {
        const result = await fetchBootstrap(controller.signal);
        if (controller.signal.aborted) return;
        setBootstrap(result);
        setBootstrapError(null);
        setSelectedTierId(result.preferences.defaultTierId);
        setSelectedProviderId(
          providerOptionForTierId(
            result.modelTiers,
            result.preferences.defaultTierId,
            selectedProviderIdRef.current ?? readStoredPreferredProviderId(),
          )?.providerId,
        );
        setIsTemporary(result.preferences.temporaryByDefault);
      } catch (cause) {
        // Aborted: either our timeout fired (surface the retry UI) or the effect
        // was torn down / superseded by an explicit retry (stay silent — the
        // re-run owns the next fetch).
        if (controller.signal.aborted) {
          if (timedOut) {
            setBootstrapError(
              new ApiError(
                {
                  code: "TIMEOUT",
                  severity: "error",
                  title: "Taking longer than usual",
                  body:
                    "The server is taking a while to respond — this can happen on the first visit after a quiet spell. Try again.",
                },
                0,
              ),
            );
          }
          return;
        }
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
        window.clearTimeout(timeoutId);
        // Only clear the latch if a newer attempt hasn't already replaced this
        // controller (the retry handler aborts + supersedes synchronously). (P1-5)
        if (bootstrapControllerRef.current === controller) {
          bootstrapInFlightRef.current = false;
          bootstrapControllerRef.current = null;
        }
      }
    })();
    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [bootstrapAttempt]);

  // Stable derived bootstrap views — read once per render with `null` fallbacks
  // so the rest of the handler graph stays simple. The render guards below
  // ensure these are never read while `bootstrap === null`.
  const account: AccountInfo | null = bootstrap?.account ?? null;
  const preferences: UserPreferences | null = bootstrap?.preferences ?? null;
  const usage: UsageBudget | null = bootstrap?.usage ?? null;
  const baseModelTiers: ModelTier[] = bootstrap?.modelTiers ?? [];
  const baseSelectedTier = baseModelTiers.find((t) => t.id === selectedTierId);
  const selectedProviderOption = providerOptionForTier(
    baseSelectedTier,
    selectedProviderId,
  );
  const effectiveProviderId = selectedProviderOption?.providerId;
  const providerOptions = providerOptionsForTier(baseSelectedTier);
  const modelTiers: ModelTier[] = baseModelTiers.map((tier) =>
    effectiveTierForProvider(tier, effectiveProviderId),
  );
  const selectedModelTier = modelTiers.find((t) => t.id === selectedTierId);
  // "Can use Pro on the platform" — mirrors the BE entitlement rule
  // (`_has_platform_pro_access`): a BYOK key OR an active Pro plan grants Pro.
  // We read the same signal the settings dialog uses (`billing.proEnabled`,
  // falling back to `planLabel === "Pro"`), plus BYOK. Anonymous/free users
  // without BYOK can't use Pro. Used to gate the Pro option in compare slots so
  // a non-entitled user isn't offered a column that would just 402.
  const canUsePro =
    !!account &&
    (account.byokEnabled === true ||
      account.billing?.proEnabled === true ||
      account.planLabel === "Pro");
  // Tiers offered in the compare slot pickers. Pro is filtered out for users
  // who can't use it (compare is a new surface, so there's no regression in
  // hiding it — selecting it would only graceful-402 per column). The two
  // slots' collision-swap logic in `handleSelectCompareTier` still holds on a
  // filtered list (it never assumes Pro is present).
  const compareModelTiers = canUsePro
    ? modelTiers
    : modelTiers.filter((tier) => tier.id !== "pro");
  // Resolved ModelTier objects for the two compare slots (provider-effective).
  // Resolve against the entitlement-filtered list so a non-entitled user whose
  // saved slot is Pro falls back to an offered tier (never a Pro column they
  // can't run). Fall back to the first offered tier so the columns always have
  // a label even before bootstrap settles the registry.
  const compareTierA =
    compareModelTiers.find((t) => t.id === compareTierIds[0]) ??
    compareModelTiers[0];
  const compareTierB =
    compareModelTiers.find((t) => t.id === compareTierIds[1]) ??
    compareModelTiers[0];
  // The selected tier's web-search capability. Drives the picker's toggle
  // visibility and gates whether `webSearch` is ever sent. Defaults to false
  // while bootstrap is pending. Selection handlers clear it when moving to a
  // tier/provider that cannot search, and send paths still gate on this flag.
  const selectedTierSupportsSearch = selectedModelTier?.supportsWebSearch === true;
  const selectedTierSupportsAttachments =
    selectedModelTier?.supportsAttachments === true;
  // Whether the selected tier can interpret images. DISTINCT from attachment
  // support: a tier may accept files (PDF/text as transcript) without vision.
  // Drives the composer's image-only auto-removal. Defaults to true while
  // bootstrap is pending so we never spuriously strip images mid-load.
  const selectedTierSupportsVision = selectedModelTier?.supportsVision !== false;
  // Effective, gated view used by every consumer.
  const effectiveSearchEnabled = searchEnabled && selectedTierSupportsSearch;
  // Whether the server's agentic seam is on (AGENTIC_ENABLED && TOOLS_ENABLED,
  // surfaced on bootstrap). Gates the picker's Deep Research toggle AND every
  // send path, so the mode is never sent to a server that would ignore it.
  const agenticEnabled = bootstrap?.agenticEnabled === true;
  // Effective, gated view used by every consumer (mirrors web search above).
  const effectiveDeepResearch = deepResearchEnabled && agenticEnabled;
  // Whether the served provider honours a reasoning-effort knob. Anthropic
  // ignores the control, so we DISABLE the effort rows (a graceful, honest UX:
  // the picker shows a one-line note rather than ever surfacing an error). The
  // check is on the effective provider id so switching provider re-evaluates.
  // Defaults to supported while bootstrap is pending.
  const effortSupported = effectiveProviderId !== "anthropic";
  // Effective, gated reasoning effort actually sent: forced to "auto" when the
  // served provider ignores effort, so an unsupported turn never carries a
  // stale non-auto value onto the wire.
  const effectiveReasoningEffort: ReasoningEffortId = effortSupported
    ? selectedReasoningEffortId
    : "auto";
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

  // Projects/Spaces (D20). Same hydrate-once-then-own-locally discipline as the
  // conversation list. `Project` (the full shape) is a superset of the bootstrap
  // `ProjectSummary`, so the summaries hydrate this list directly.
  const [projects, setProjects] = useState<Project[]>([]);
  const projectsHydratedRef = useRef(false);
  useEffect(() => {
    if (bootstrap && !projectsHydratedRef.current) {
      projectsHydratedRef.current = true;
      setProjects(
        (bootstrap.projects ?? []).map((p) => ({
          ...p,
          // ProjectSummary omits timestamps; fill placeholders so the FE `Project`
          // shape is satisfied. They are only used by the export view, never the
          // sidebar/settings, so the empty string is inert here.
          createdAt: "",
          updatedAt: "",
        })),
      );
    }
  }, [bootstrap]);

  // Tags (Conversation Org v2). Same hydrate-once-then-own-locally discipline as
  // the projects list. `activeTagId` is the current sidebar filter (null = all).
  const [tags, setTags] = useState<Tag[]>([]);
  const [activeTagId, setActiveTagId] = useState<string | null>(null);
  const tagsHydratedRef = useRef(false);
  useEffect(() => {
    if (bootstrap && !tagsHydratedRef.current) {
      tagsHydratedRef.current = true;
      setTags(bootstrap.tags ?? []);
    }
  }, [bootstrap]);

  const reconcileProviderAvailability = useCallback(
    (tiers: ModelTier[], preferredProviderId?: string) => {
      const tierId = selectedTierIdRef.current;
      const nextBaseTier = tiers.find((tier) => tier.id === tierId);
      const nextProvider = providerOptionForTier(nextBaseTier, preferredProviderId);
      const nextTier = nextBaseTier
        ? effectiveTierForProvider(nextBaseTier, nextProvider?.providerId)
        : undefined;
      setSelectedProviderId(nextProvider?.providerId);
      if (nextTier?.supportsWebSearch !== true) setSearchEnabled(false);
      if (nextTier?.supportsAttachments !== true) {
        composerRef.current?.clearAttachments("unsupported");
      }
    },
    [],
  );

  useEffect(() => {
    const query = conversationSearch.trim();
    if (query.length === 0) return;

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setConversationSearchState({ query, results: null, pending: true });
      void searchConversations(query, controller.signal)
        .then((results) => {
          if (!controller.signal.aborted) {
            setConversationSearchState({ query, results, pending: false });
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setConversationSearchState({ query, results: null, pending: false });
          }
        });
    }, 150);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [conversationSearch]);

  const firstName = useMemo(() => {
    if (!account?.name) return undefined;
    // Anonymous accounts carry a server-minted placeholder name ("Guest").
    // A bare greeting ("Got an idea?") is warmer than naming a stranger, so
    // suppress the name entirely for guests — only registered users keep theirs.
    if (isAnonymousAccount(account)) return undefined;
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

    // Stop pressed before any content streamed: committing an empty assistant
    // bubble (parts:[]) reads as a blank/errored turn. Skip the assistant
    // commit entirely — keep the user message, just clear the pending state.
    // (P1-3)
    if (
      result.status === "stopped" &&
      !result.reasoning &&
      !result.answer &&
      result.sources.length === 0 &&
      result.subagents.length === 0
    ) {
      const optimisticUserId = pendingUserIdRef.current;
      const serverUserId = result.serverUserMessageId;
      if (optimisticUserId && serverUserId) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === optimisticUserId ? { ...m, id: serverUserId } : m,
          ),
        );
      }
      setLiveMessage("Generation stopped");
      setPendingId(null);
      assistantIdRef.current = null;
      pendingUserIdRef.current = null;
      return;
    }

    const parts: MessagePart[] = [];
    if (result.subagents.length > 0) {
      // Agentic turn: commit the same subagent-grouped layout the BE persists
      // (and the live pendingMessage already rendered), so the settled bubble
      // and a later reload are pixel-identical.
      parts.push(...buildSubagentParts(result.subagents, result.toolParts));
    } else {
      if (result.reasoning) {
        parts.push({
          type: "reasoning",
          text: result.reasoning,
          durationSec: result.reasoningDurationSec,
        });
      }
      parts.push(...result.toolParts);
      // The search has finished by terminal time, so force `state: "done"` —
      // the spinner stops, the label stays (e.g. "Searched the web").
      if (result.searchStatus) {
        parts.push({
          type: "status",
          label: result.searchStatus.label,
          state: "done",
        });
      }
      if (result.answer) parts.push({ type: "text", text: result.answer });
      // Sources part follows the answer text (contract ordering). Emit it
      // whenever web search was effective — even with zero sources — so the
      // ungrounded marker ("Answered without live sources") survives the
      // commit; grounded ⇔ non-empty items.
      if (result.sources.length > 0 || result.sourcesRequested) {
        parts.push({
          type: "sources",
          items: result.sources,
          requested: result.sourcesRequested,
        });
      }
    }

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

    if (result.status === "done") {
      setLiveMessage("Response ready");
      // BE title autogen completes after terminal; refresh placeholder rows.
      if (activeConversationId && !isTemporary) {
        const convId = activeConversationId;
        void (async () => {
          for (const delayMs of [500, 3000]) {
            await new Promise((resolve) => setTimeout(resolve, delayMs));
            try {
              const conv = await fetchConversation(convId);
              setConversations((prev) =>
                prev.map((c) =>
                  c.id === convId &&
                  c.title === "New chat" &&
                  conv.title !== "New chat"
                    ? { ...c, title: conv.title }
                    : c,
                ),
              );
              if (conv.title !== "New chat") return;
            } catch {
              return;
            }
          }
        })();
      }
    } else if (result.status === "stopped") setLiveMessage("Generation stopped");
    else if (result.status === "awaiting_approval")
      // HITL pause: the turn committed in place (with its tool parts) and the
      // bubble now shows the approve/deny card. Not "ready" — it's waiting on us.
      setLiveMessage("Action needs your approval");
    else setLiveMessage("Generation failed");

    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
  }, [activeConversationId, isTemporary]);

  // A second send was rejected with 409 STREAM_IN_PROGRESS — a response is
  // still generating. The hook suppressed the error terminal so the live answer
  // survives; here we just roll back THIS turn's optimistic user bubble + clear
  // its pending state and tell the user to wait. (P0-2)
  const handleStreamInProgress = useCallback(() => {
    const optimisticUserId = pendingUserIdRef.current;
    if (optimisticUserId) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticUserId));
    }
    pendingUserIdRef.current = null;
    assistantIdRef.current = null;
    setPendingId(null);
    setLiveMessage("A response is still generating");
    showToast({
      severity: "info",
      title: "A response is still generating — wait for it to finish or stop it.",
    });
  }, []);

  const { state, start, stop, reset } = useApiStream(
    handleTerminal,
    handleStreamInProgress,
  );

  // Cancel the welcome→thread exit/seam timers. Shared by every handler that
  // nulls activeConversationId or otherwise abandons a pending turn, so a
  // scheduled commitTurn() can never fire into the wrong (or torn-down) thread.
  // (P1-4 — hoisted out of handleNewChat / handleSelectConversation /
  // handleDeleteConversation, and reused by handleToggleTemporary + handleStop.)
  const cancelWelcomeTimers = useCallback(() => {
    if (welcomeExitTimerRef.current !== null) {
      window.clearTimeout(welcomeExitTimerRef.current);
      welcomeExitTimerRef.current = null;
    }
    if (welcomeSeamTimerRef.current !== null) {
      window.clearTimeout(welcomeSeamTimerRef.current);
      welcomeSeamTimerRef.current = null;
    }
  }, []);

  const isStreaming =
    pendingId !== null && (state.status === "submitted" || state.status === "streaming");

  const handleSelectTier = (id: ModelTierId): void => {
    const previousTierId = selectedTierId;
    const nextBaseTier = baseModelTiers.find((tier) => tier.id === id);
    const nextProvider = providerOptionForTier(nextBaseTier, selectedProviderId);
    const nextTier = nextBaseTier
      ? effectiveTierForProvider(nextBaseTier, nextProvider?.providerId)
      : undefined;
    setSelectedTierId(id);
    setSelectedProviderId(nextProvider?.providerId);
    if (id !== previousTierId) {
      reportTelemetry(preferences, "tier.changed", {
        fromTierId: previousTierId,
        toTierId: id,
        surface: "chat",
      });
    }
    if (nextTier?.supportsWebSearch !== true) setSearchEnabled(false);
    if (nextTier?.supportsAttachments !== true) {
      composerRef.current?.clearAttachments("unsupported");
    }
  };

  const handleSelectProvider = (id: string): void => {
    const nextProvider = providerOptions.find(
      (option) => option.providerId === id && option.status === "available",
    );
    if (!nextProvider) return;
    const previousProviderId = selectedProviderId;
    const nextTier = baseSelectedTier
      ? effectiveTierForProvider(baseSelectedTier, id)
      : undefined;
    setSelectedProviderId(id);
    storePreferredProviderId(id);
    if (id !== previousProviderId) {
      reportTelemetry(preferences, "provider.changed", {
        fromProviderId: previousProviderId ?? null,
        toProviderId: id,
        tierId: selectedTierId,
      });
    }
    if (nextTier?.supportsWebSearch !== true) setSearchEnabled(false);
    if (nextTier?.supportsAttachments !== true) {
      composerRef.current?.clearAttachments("unsupported");
    }
  };

  // Synchronous "busy" signal for the composer + edit/regenerate gates. Unlike
  // `isStreaming` (which only flips once the first SSE frame lands), this goes
  // true the instant a turn is initiated — `pendingId` is set synchronously in
  // commitTurn / handleEditUserMessage / handleRegenerate before any await, so
  // the composer morphs to Stop and the second send is blocked immediately,
  // closing the double-submit window during the `createConversation` round-trip.
  // `welcomeExiting` covers the ~200ms welcome-exit timer before commitTurn runs
  // (where `pendingId` is not yet set) so the composer is armed-busy for that
  // gap too. (P0-1)
  const isBusy =
    pendingId !== null || isStreaming || welcomeExiting || compareStreaming;

  // Stop handler that copes with the pre-stream window opened by the P0-1 busy
  // signal. If a real stream is in flight, defer to the hook's `stop()` (which
  // aborts + synthesizes the `stopped` terminal). If Stop is pressed BEFORE the
  // first frame — during the welcome-exit timer or the createConversation
  // round-trip — there's no AbortController yet, so we tear the turn down here:
  // cancel the seam timers, flag `beginTurn` to skip `start()`, roll back the
  // optimistic user bubble, and clear the synchronous busy state so the composer
  // re-arms. (P0-1 requirement (a))
  const handleStop = () => {
    // Compare mode owns its own per-column streams; fan Stop out to all of them
    // (the single-stream `stop()` below is inert here — no main stream is in
    // flight in compare mode).
    if (compareMode) {
      compareViewRef.current?.stopAll();
      setLiveMessage("Generation stopped");
      return;
    }
    if (isStreaming) {
      stop();
      return;
    }
    // Pre-stream abort.
    abortBeforeStartRef.current = true;
    cancelWelcomeTimers();
    setWelcomeExiting(false);
    setWelcomeSeamLanding(false);
    const optimisticUserId = pendingUserIdRef.current;
    if (optimisticUserId) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticUserId));
    }
    pendingUserIdRef.current = null;
    assistantIdRef.current = null;
    setPendingId(null);
    setLiveMessage("Generation stopped");
  };

  // Begin (or continue) a streamed turn. Shared by send / regenerate / edit.
  // Creates the conversation lazily on the FIRST send when none is active.
  // Returns the conversation id used so callers can fall through their own
  // post-start state updates.
  const beginTurn = useCallback(
    async (args: {
      text: string;
      tierId: ModelTierId;
      providerId?: string;
      regenerate?: boolean;
      continueTurn?: boolean;
      editMessageId?: string;
      // HITL resume decision; mutually exclusive with regenerate/continue/edit.
      toolApproval?: {
        toolCallId: string;
        decision: "approve" | "deny";
        editedInput?: Record<string, unknown>;
      };
      webSearch?: boolean;
      reasoningEffort?: ReasoningEffortId;
      responseFormat?: { type: "json_object" };
      attachments?: AttachmentPart[];
      agenticMode?: AgenticMode;
    }): Promise<void> => {
      abortBeforeStartRef.current = false;
      let conversationId = activeConversationId;
      if (!conversationId) {
        try {
          // File a fresh (non-temporary) chat under the active project context
          // (D20) when one exists; temp chats can't carry a project.
          const projectIdForCreate =
            !isTemporary && activeProjectIdRef.current
              ? activeProjectIdRef.current
              : undefined;
          const created = await createConversation({
            selectedTierId: args.tierId,
            isTemporary,
            providerId: args.providerId,
            ...(projectIdForCreate ? { projectId: projectIdForCreate } : {}),
          });
          // Stop pressed during the create round-trip — abandon this turn
          // before arming the stream. handleStop already cleared the optimistic
          // bubble + pendingId; just don't create/insert/start. (P0-1)
          if (abortBeforeStartRef.current) {
            abortBeforeStartRef.current = false;
            return;
          }
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
              projectId: created.projectId ?? null,
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
          // Restore the typed text to the composer so a failed first-send
          // create doesn't lose the user's message (the composer cleared it on
          // submit). Only the plain-send path reaches create with no active
          // conversation; edit/regenerate/continue/tool-approval run against an
          // existing one. (P2-5)
          if (
            !args.regenerate &&
            !args.editMessageId &&
            !args.continueTurn &&
            !args.toolApproval
          ) {
            composerRef.current?.setDraft(args.text);
          }
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
        providerId: args.providerId,
        text: args.text,
        isTemporary: isTemporary || undefined,
        regenerate: args.regenerate,
        continueTurn: args.continueTurn,
        editMessageId: args.editMessageId,
        // HITL resume decision; stream-client sends it on the wire only when set.
        toolApproval: args.toolApproval,
        // Sent only when on; stream-client further drops it from the wire when
        // falsy, so the off path is byte-identical to today.
        webSearch: args.webSearch,
        // Sent only when non-"auto"; stream-client drops it from the wire on
        // "auto"/absent, so the default path is byte-identical to today.
        reasoningEffort: args.reasoningEffort,
        // Sent only when JSON mode is on; stream-client drops it from the wire
        // when undefined, so the off path is byte-identical to today.
        responseFormat: args.responseFormat,
        attachments: args.attachments,
        // Sent only on a Deep Research turn; stream-client drops anything but
        // "deep_research" from the wire, so the off path is byte-identical.
        agenticMode: args.agenticMode,
      });
    },
    [activeConversationId, isTemporary, start],
  );

  const handleSend = (text: string, attachments: AttachmentPart[]) => {
    // Compare mode hijacks send: fan the prompt out to two columns instead of
    // committing a single turn. Attachments aren't offered in compare mode
    // (the toggle replaces the attach affordance contextually), so they're
    // ignored here.
    if (compareMode) {
      if (!text.trim()) return;
      handleCompareSend(text);
      return;
    }
    const userBubbleId = localId();
    const assistantPlaceholderId = localId();
    const visibleAttachments: AttachmentPart[] = attachments.map((attachment) => ({
      type: "attachment",
      id: attachment.id,
      name: attachment.name,
      mediaType: attachment.mediaType,
      mimeType: attachment.mimeType,
      sizeBytes: attachment.sizeBytes,
      storagePolicy: "transient",
    }));
    tierAtSendRef.current = selectedTierId;
    providerAtSendRef.current = effectiveProviderId;
    // Only ride web search along when the selected tier actually supports it —
    // the effect already keeps `searchEnabled` false off-tier, but gate here too
    // so a same-tick tier switch can't leak a stale flag.
    searchAtSendRef.current = effectiveSearchEnabled;
    // Capture the effort picked at send-time (gated below so an unsupported
    // tier never rides a stale value onto the wire).
    effortAtSendRef.current = effectiveReasoningEffort;
    // JSON mode isn't tier-gated, so capture the raw toggle at send-time.
    jsonModeAtSendRef.current = jsonModeEnabled;
    // Deep Research rides only when the bootstrap advertised the agentic seam
    // (mirrors the web-search gate above).
    deepResearchAtSendRef.current = effectiveDeepResearch;
    assistantIdRef.current = assistantPlaceholderId;
    pendingUserIdRef.current = userBubbleId;

    const commitTurn = () => {
      setMessages((prev) => [
        ...prev,
        {
          id: userBubbleId,
          role: "user",
          createdAt: new Date().toISOString(),
          parts: [{ type: "text", text }, ...visibleAttachments],
        },
      ]);
      setPendingId(assistantPlaceholderId);
      setLiveMessage("Generating response");
      void beginTurn({
        text,
        tierId: tierAtSendRef.current,
        providerId: providerAtSendRef.current,
        webSearch: searchAtSendRef.current || undefined,
        reasoningEffort: effortAtSendRef.current,
        responseFormat: jsonModeAtSendRef.current
          ? { type: "json_object" }
          : undefined,
        attachments,
        agenticMode: deepResearchAtSendRef.current ? "deep_research" : undefined,
      });
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

  // --- Compare-mode handlers --------------------------------------------------

  // Reset every transient compare turn artifact. Shared by toggling compare off
  // and by any navigation that abandons compare (new chat, select conversation,
  // toggle temporary), so leaving compare never strands a streaming column or
  // a stale prompt bubble.
  const resetCompareTurn = useCallback(() => {
    compareViewRef.current?.stopAll();
    setCompareTurn(null);
    setCompareUserMessage(null);
    setCompareStreaming(false);
  }, []);

  // Compose the two-slot compare selection so the slots always stay DISTINCT —
  // picking the tier already in the other slot swaps them rather than letting
  // both columns answer with the same tier (which would defeat the comparison
  // AND make the two columns' attribution labels identical).
  const handleSelectCompareTier = (slot: 0 | 1, id: ModelTierId): void => {
    setCompareTierIds((prev) => {
      const other = prev[slot === 0 ? 1 : 0];
      if (id === other) {
        // Swap: the picked tier collides with the other slot, so trade places.
        return slot === 0 ? [id, prev[0]] : [prev[1], id];
      }
      return slot === 0 ? [id, prev[1]] : [prev[0], id];
    });
    // A live turn's columns are pinned to the tiers they started with; clear it
    // so the next send fans out with the new selection (and the stale columns
    // stop streaming).
    resetCompareTurn();
  };

  // Enter/exit compare. Entering seeds two distinct tiers (the current single-
  // stream tier plus a different default) and clears any in-flight single turn;
  // exiting tears down all compare state and returns to the normal thread.
  const handleToggleCompare = () => {
    if (compareMode) {
      resetCompareTurn();
      setCompareMode(false);
      setLiveMessage("Exited compare mode");
      return;
    }
    // Abort any in-flight single-stream turn before swapping the surface out —
    // otherwise it keeps streaming hidden and commits to the now-offscreen
    // thread (mirrors the new-chat / select-conversation reset paths).
    if (isStreaming) reset();
    // Seed slot 0 with the currently-selected tier and slot 1 with a distinct
    // one so the two columns never start identical.
    const first = selectedTierId;
    const second =
      baseModelTiers.find((t) => t.id !== first)?.id ??
      (first === "fast" ? "pro" : "fast");
    setCompareTierIds([first, second]);
    setCompareTurn(null);
    setCompareUserMessage(null);
    setCompareMode(true);
    setLiveMessage("Compare mode on. Pick two models and send a prompt.");
  };

  // Compare send: create ONE temporary conversation, then hand a fresh turn to
  // CompareView, which fans `start()` out to every column. Belt-and-suspenders
  // on the isTemporary invariant: the conversation is created with
  // `isTemporary: true` for the URL id, AND every column's `start()` also sends
  // `isTemporary: true` (compare-column.tsx) so no column can claim the
  // per-conversation active-stream lock and 409 its sibling.
  const handleCompareSend = (text: string) => {
    setCompareUserMessage({
      id: `compare-user-${crypto.randomUUID()}`,
      role: "user",
      createdAt: new Date().toISOString(),
      parts: [{ type: "text", text }],
    });
    setLiveMessage("Comparing two models");
    void (async () => {
      try {
        const created = await createConversation({
          selectedTierId: compareTierIds[0],
          isTemporary: true,
          providerId: effectiveProviderId,
        });
        const token = ++compareTokenRef.current;
        setCompareTurn({
          token,
          text,
          conversationId: created.id,
          clientMessageIds: compareTierIds.map(() => crypto.randomUUID()),
        });
      } catch (cause) {
        setCompareUserMessage(null);
        composerRef.current?.setDraft(text);
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't start compare";
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

  const pendingMessage: ChatMessage | null = useMemo(() => {
    if (!pendingId) return null;
    const parts: MessagePart[] = [];
    if (state.subagents.length > 0) {
      // Agentic turn: every content delta arrived tagged, so the flat
      // accumulators below are empty — build the subagent-grouped layout the
      // BE persists instead (marker + tagged reasoning/tools/text per
      // subagent). AssistantMessage renders the panel + main answer from it.
      parts.push(...buildSubagentParts(state.subagents, state.toolParts));
    } else {
      if (state.reasoning) {
        parts.push({
          type: "reasoning",
          text: state.reasoning,
          durationSec: state.reasoningDurationSec,
        });
      }
      parts.push(...state.toolParts);
      if (state.searchStatus) {
        parts.push({
          type: "status",
          label: state.searchStatus.label,
          state: state.searchStatus.state,
        });
      }
      if (state.answer) parts.push({ type: "text", text: state.answer });
      // Sources render AFTER the answer text (contract: sources part follows
      // the answer). They stream in once the search resolves. When web search
      // was effective but resolved nothing, the empty + requested part drives
      // the live ungrounded marker.
      if (state.sources.length > 0 || state.sourcesRequested) {
        parts.push({
          type: "sources",
          items: state.sources,
          requested: state.sourcesRequested,
        });
      }
    }
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
    // Capture the overwritten feedback from INSIDE the updater so a fast
    // up→down toggle whose first POST fails reverts to exactly the value it
    // replaced — not a stale render-time snapshot. (P0-3)
    let previous: Feedback = null;
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== id) return m;
        previous = m.feedback ?? null;
        return { ...m, feedback: next };
      }),
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
    // Compute the trailing user text from the pre-update `messages` snapshot
    // BEFORE the setMessages updater runs, so the value we send and the trim
    // below agree on one consistent view. (P2-4)
    const lastUserText = (() => {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role !== "user") continue;
        for (const p of m.parts) if (p.type === "text") return p.text;
      }
      return "";
    })();
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
    providerAtSendRef.current = effectiveProviderId;
    searchAtSendRef.current = effectiveSearchEnabled;
    effortAtSendRef.current = effectiveReasoningEffort;
    jsonModeAtSendRef.current = jsonModeEnabled;
    deepResearchAtSendRef.current = effectiveDeepResearch;
    setPendingId(regenId);
    setLiveMessage("Regenerating response");
    // Regenerate keeps the trailing user message verbatim — send its text
    // back to the server, which ignores `text` on regenerate but the wire
    // schema still requires it.
    void beginTurn({
      text: lastUserText,
      tierId: tierAtSendRef.current,
      providerId: providerAtSendRef.current,
      regenerate: true,
      webSearch: searchAtSendRef.current || undefined,
      reasoningEffort: effortAtSendRef.current,
      responseFormat: jsonModeAtSendRef.current
        ? { type: "json_object" }
        : undefined,
      agenticMode: deepResearchAtSendRef.current ? "deep_research" : undefined,
    });
  };

  // Regenerate the trailing turn with a DIFFERENT model/provider (Feature 4).
  // A copy of `handleRegenerate` that uses the passed tier/provider instead of
  // the currently-selected one, and also moves the picker selection to match so
  // the served model is reflected going forward. The BE regenerate route
  // already accepts tierId/providerId, so this rides the existing wire path.
  const handleRegenerateWith = (tierId: ModelTierId, providerId?: string) => {
    if (isStreaming) return;
    // Resolve the provider route for the chosen tier the same way the picker
    // does — honour the explicit providerId when given, else the default route.
    const resolvedProviderId =
      providerOptionForTierId(baseModelTiers, tierId, providerId)?.providerId ??
      providerId;
    // Reflect the new served model in the picker for subsequent turns.
    setSelectedTierId(tierId);
    setSelectedProviderId(resolvedProviderId);
    const lastUserText = (() => {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role !== "user") continue;
        for (const p of m.parts) if (p.type === "text") return p.text;
      }
      return "";
    })();
    setMessages((prev) => {
      const next = [...prev];
      while (next.length && next[next.length - 1].role === "assistant") next.pop();
      return next;
    });
    const regenId = localId();
    assistantIdRef.current = regenId;
    pendingUserIdRef.current = null;
    tierAtSendRef.current = tierId;
    providerAtSendRef.current = resolvedProviderId;
    // Web search rides only when the CHOSEN tier/provider supports it.
    const chosenTier = baseModelTiers.find((t) => t.id === tierId);
    const chosenEffectiveTier = chosenTier
      ? effectiveTierForProvider(chosenTier, resolvedProviderId)
      : undefined;
    searchAtSendRef.current =
      searchEnabled && chosenEffectiveTier?.supportsWebSearch === true;
    // Effort rides only when the chosen provider honours it (Anthropic ignores).
    effortAtSendRef.current =
      resolvedProviderId !== "anthropic" ? selectedReasoningEffortId : "auto";
    // JSON mode isn't tier-gated, so capture the raw toggle at send-time.
    jsonModeAtSendRef.current = jsonModeEnabled;
    deepResearchAtSendRef.current = effectiveDeepResearch;
    setPendingId(regenId);
    setLiveMessage("Regenerating response");
    void beginTurn({
      text: lastUserText,
      tierId,
      providerId: resolvedProviderId,
      regenerate: true,
      webSearch: searchAtSendRef.current || undefined,
      reasoningEffort: effortAtSendRef.current,
      responseFormat: jsonModeAtSendRef.current
        ? { type: "json_object" }
        : undefined,
      agenticMode: deepResearchAtSendRef.current ? "deep_research" : undefined,
    });
  };

  const handleContinue = () => {
    if (isStreaming) return;
    // CRITICAL: unlike regenerate, continue MUST NOT pop the trailing stopped
    // assistant bubble — the user paid for that partial and we keep it. The
    // continuation streams in as a NEW assistant bubble right after it.
    //
    // Find the trailing user text so the wire schema's required `text` is
    // satisfied; the BE ignores it on continue (it replays the persisted
    // history + appends a fixed continuation instruction).
    const lastUserText = (() => {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role !== "user") continue;
        for (const p of m.parts) if (p.type === "text") return p.text;
      }
      return "";
    })();
    const continueId = localId();
    assistantIdRef.current = continueId;
    pendingUserIdRef.current = null;
    tierAtSendRef.current = selectedTierId;
    providerAtSendRef.current = effectiveProviderId;
    searchAtSendRef.current = effectiveSearchEnabled;
    effortAtSendRef.current = effectiveReasoningEffort;
    jsonModeAtSendRef.current = jsonModeEnabled;
    deepResearchAtSendRef.current = effectiveDeepResearch;
    setPendingId(continueId);
    setLiveMessage("Continuing response");
    void beginTurn({
      text: lastUserText,
      tierId: tierAtSendRef.current,
      providerId: providerAtSendRef.current,
      continueTurn: true,
      webSearch: searchAtSendRef.current || undefined,
      reasoningEffort: effortAtSendRef.current,
      responseFormat: jsonModeAtSendRef.current
        ? { type: "json_object" }
        : undefined,
      agenticMode: deepResearchAtSendRef.current ? "deep_research" : undefined,
    });
  };

  // HITL resume. Mirrors `handleContinue` exactly: the paused (awaiting_approval)
  // bubble is RETAINED — the continuation streams in as a NEW assistant bubble
  // via the existing pendingMessage live path. The decision rides a follow-up
  // message POST (`toolApproval`), which the BE treats as a resume of the paused
  // turn (replay history + apply decision). `messageId` is unused for the wire
  // (the BE keys off the conversation's paused turn + toolCallId), but kept in
  // the signature to match the per-message handler shape.
  const handleToolDecision = (
    _messageId: string,
    decision: { toolCallId: string; decision: "approve" | "deny" },
  ) => {
    if (isStreaming) return;
    // Trailing user text satisfies the wire schema's required `text`; the BE
    // ignores it on a tool-approval resume (it replays the persisted history).
    const lastUserText = (() => {
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role !== "user") continue;
        for (const p of m.parts) if (p.type === "text") return p.text;
      }
      return "";
    })();
    // An agentic plan-approval resume MUST re-carry `deep_research`: the BE
    // re-runs the orchestrator only when the resume body has the mode (the
    // handler's agentic gate reads it per-request, not from the paused turn).
    // Detect it from the paused tool call itself — the pseudo
    // `agentic_plan_approval` tool — so the resume works even if the user has
    // since flipped the composer toggle off.
    const isPlanApproval = messages.some(
      (m) =>
        m.role === "assistant" &&
        m.parts.some(
          (p) =>
            p.type === "tool_call" &&
            p.id === decision.toolCallId &&
            p.name === "agentic_plan_approval",
        ),
    );
    const resumeId = localId();
    assistantIdRef.current = resumeId;
    pendingUserIdRef.current = null;
    tierAtSendRef.current = selectedTierId;
    providerAtSendRef.current = effectiveProviderId;
    searchAtSendRef.current = effectiveSearchEnabled;
    effortAtSendRef.current = effectiveReasoningEffort;
    jsonModeAtSendRef.current = jsonModeEnabled;
    deepResearchAtSendRef.current = isPlanApproval || effectiveDeepResearch;
    setPendingId(resumeId);
    setLiveMessage(
      decision.decision === "approve"
        ? "Approving action"
        : "Denying action",
    );
    void beginTurn({
      text: lastUserText,
      tierId: tierAtSendRef.current,
      providerId: providerAtSendRef.current,
      toolApproval: {
        toolCallId: decision.toolCallId,
        decision: decision.decision,
      },
      webSearch: searchAtSendRef.current || undefined,
      reasoningEffort: effortAtSendRef.current,
      responseFormat: jsonModeAtSendRef.current
        ? { type: "json_object" }
        : undefined,
      agenticMode: deepResearchAtSendRef.current ? "deep_research" : undefined,
    });
  };

  const handleEditUserMessage = (messageId: string, newText: string) => {
    if (isStreaming) {
      // Don't silently drop the edit — tell the user why it didn't apply. (P1-1)
      showToast({
        severity: "info",
        title: "Wait for the current response to finish before editing.",
      });
      return;
    }
    // Local-only ids belong to user bubbles whose turn never persisted
    // (e.g. a prior error before terminal). The BE rejects non-uuid edit
    // targets with 400, so skip rather than emit a doomed request.
    if (messageId.startsWith("local-")) return;
    const idx = messages.findIndex((m) => m.id === messageId);
    if (idx === -1) return;
    const userBubbleId = localId();
    const assistantPlaceholderId = localId();
    tierAtSendRef.current = selectedTierId;
    providerAtSendRef.current = effectiveProviderId;
    searchAtSendRef.current = effectiveSearchEnabled;
    effortAtSendRef.current = effectiveReasoningEffort;
    jsonModeAtSendRef.current = jsonModeEnabled;
    deepResearchAtSendRef.current = effectiveDeepResearch;
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
      providerId: providerAtSendRef.current,
      editMessageId: messageId,
      webSearch: searchAtSendRef.current || undefined,
      reasoningEffort: effortAtSendRef.current,
      responseFormat: jsonModeAtSendRef.current
        ? { type: "json_object" }
        : undefined,
      agenticMode: deepResearchAtSendRef.current ? "deep_research" : undefined,
    });
  };

  const handleBranchFromMessage = (messageId: string) => {
    if (!activeConversationId || isTemporary || isStreaming) return;
    if (messageId.startsWith("local-")) return;
    const sourceConversationId = activeConversationId;
    setBranchingMessageId(messageId);
    void (async () => {
      try {
        const branched = await branchConversation(sourceConversationId, {
          messageId,
        });
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
        setPendingId(null);
        assistantIdRef.current = null;
        pendingUserIdRef.current = null;
        reset();
        selectConversationTokenRef.current = branched.id;
        setActiveConversationId(branched.id);
        setIsTemporary(false);
        setMessages(branched.messages);
        setSelectedTierId(branched.selectedTierId);
        setSelectedProviderId(
          providerOptionForTierId(
            baseModelTiers,
            branched.selectedTierId,
            selectedProviderIdRef.current,
          )?.providerId,
        );
        setMobileNavOpen(false);
        setConversations((prev) => {
          const summary: ConversationSummary = {
            id: branched.id,
            title: branched.title,
            updatedAt: new Date().toISOString(),
            isTemporary: false,
            pinned: false,
          };
          return [summary, ...prev.filter((c) => c.id !== branched.id)];
        });
        setLiveMessage("Branched into new chat");
        showToast({ severity: "info", title: "Branched into new chat" });
      } catch (cause) {
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't branch conversation";
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
      } finally {
        setBranchingMessageId(null);
      }
    })();
  };

  const handleNewChat = () => {
    // Cancel any in-flight welcome→thread seam (see handleSelectConversation
    // for the corruption shape). New chat nulls activeConversationId, so a
    // pending exit timer firing here would commitTurn() into the wrong
    // (newly-empty) state.
    cancelWelcomeTimers();
    setWelcomeExiting(false);
    setWelcomeSeamLanding(false);
    if (isStreaming) reset();
    // Leaving for a fresh chat exits compare cleanly (stop columns, drop turn).
    if (compareMode) {
      resetCompareTurn();
      setCompareMode(false);
    }
    setMessages([]);
    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
    setLiveMessage("");
    reset();
    setActiveConversationId(null);
    if (preferences) {
      setSelectedTierId(preferences.defaultTierId);
      setSelectedProviderId(
        providerOptionForTierId(
          baseModelTiers,
          preferences.defaultTierId,
          selectedProviderIdRef.current ?? readStoredPreferredProviderId(),
        )?.providerId,
      );
      setIsTemporary(preferences.temporaryByDefault);
    }
    setSelectedReasoningEffortId("auto");
    setSearchEnabled(false);
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
    // Cancel any in-flight welcome→thread seam before nulling
    // activeConversationId — otherwise a pending exit timer could fire
    // commitTurn() into the now-temporary thread (data corruption). (P1-4)
    cancelWelcomeTimers();
    setWelcomeExiting(false);
    setWelcomeSeamLanding(false);
    if (isStreaming) reset();
    if (compareMode) {
      resetCompareTurn();
      setCompareMode(false);
    }
    setMessages([]);
    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
    setLiveMessage("");
    reset();
    setActiveConversationId(null);
    if (preferences) {
      setSelectedTierId(preferences.defaultTierId);
      setSelectedProviderId(
        providerOptionForTierId(
          baseModelTiers,
          preferences.defaultTierId,
          selectedProviderIdRef.current ?? readStoredPreferredProviderId(),
        )?.providerId,
      );
    }
    setSelectedReasoningEffortId("auto");
    setSearchEnabled(false);
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
    cancelWelcomeTimers();
    setWelcomeExiting(false);
    setWelcomeSeamLanding(false);
    if (isStreaming) reset();
    if (compareMode) {
      resetCompareTurn();
      setCompareMode(false);
    }
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
        setSelectedProviderId(
          providerOptionForTierId(
            baseModelTiers,
            conversation.selectedTierId,
            selectedProviderIdRef.current,
          )?.providerId,
        );
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
      cancelWelcomeTimers();
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

  // Set (number) or clear (null) a conversation's per-conversation retention
  // override (D31). Optimistic, with the same rollback-on-failure discipline as
  // rename / pin. The PATCH carries `retentionDays` three-valued: `null` clears
  // the override so the conversation inherits the global retention.
  const handleSetConversationRetention = (
    id: string,
    retentionDays: number | null,
  ) => {
    const previous = conversations;
    const target = previous.find((c) => c.id === id);
    if (!target || (target.retentionDays ?? null) === retentionDays) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, retentionDays } : c)),
    );
    void patchConversation(id, { retentionDays }).catch((cause) => {
      setConversations(previous);
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError
            ? cause.title
            : "Couldn't update retention",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  // --- Projects/Spaces (D20) -------------------------------------------------

  // File (projectId) or un-file (null) a conversation. Optimistic + rollback +
  // toast, mirroring `handleSetConversationRetention`.
  const handleAssignConversationToProject = (
    id: string,
    projectId: string | null,
  ) => {
    const previous = conversations;
    const target = previous.find((c) => c.id === id);
    if (!target || (target.projectId ?? null) === projectId) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, projectId } : c)),
    );
    void patchConversation(id, { projectId }).catch((cause) => {
      setConversations(previous);
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't move conversation",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  // Palette "New project" / "New tag" entry points. Open the small quick-create
  // surface; the actual create runs through the shared `handleCreateProject` /
  // `handleCreateTag` handlers on submit (no logic duplicated).
  const handlePaletteNewProject = () => {
    setPaletteCreateDraft("");
    setPaletteCreate("project");
  };
  const handlePaletteNewTag = () => {
    setPaletteCreateDraft("");
    setPaletteCreate("tag");
  };
  const handlePaletteCreateSubmit = () => {
    const trimmed = paletteCreateDraft.trim();
    if (!trimmed) {
      setPaletteCreate(null);
      return;
    }
    if (paletteCreate === "project") handleCreateProject(trimmed);
    else if (paletteCreate === "tag") handleCreateTag(trimmed);
    setPaletteCreate(null);
    setPaletteCreateDraft("");
  };

  // Create a project. Optimistic insert with a temporary id replaced by the
  // server row on success; rollback + toast on failure.
  const handleCreateProject = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const tempId = `temp-project-${crypto.randomUUID()}`;
    const optimistic: Project = {
      id: tempId,
      name: trimmed,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setProjects((prev) => [optimistic, ...prev]);
    void createProject({ name: trimmed })
      .then((created) => {
        setProjects((prev) =>
          prev.map((p) => (p.id === tempId ? created : p)),
        );
      })
      .catch((cause) => {
        setProjects((prev) => prev.filter((p) => p.id !== tempId));
        if (cause instanceof ApiError) setLiveMessage(cause.title);
        showToast({
          severity: "error",
          title:
            cause instanceof ApiError ? cause.title : "Couldn't create project",
          body:
            cause instanceof ApiError
              ? cause.body
              : cause instanceof Error
                ? cause.message
                : undefined,
        });
      });
  };

  // Shared optimistic project-settings update (rename + the settings panel).
  const handleUpdateProject = (id: string, patch: ProjectUpdateInput) => {
    const previous = projects;
    const target = previous.find((p) => p.id === id);
    if (!target) return;
    setProjects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    );
    void updateProject(id, patch).catch((cause) => {
      setProjects(previous);
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't update project",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  const handleRenameProject = (id: string, name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    handleUpdateProject(id, { name: trimmed });
  };

  // Delete a project. Conversations are un-filed (BE SET NULL); reflect that
  // locally by clearing membership on any conversation that pointed at it.
  const handleDeleteProject = (id: string) => {
    const previousProjects = projects;
    const previousConversations = conversations;
    setProjects((prev) => prev.filter((p) => p.id !== id));
    setConversations((prev) =>
      prev.map((c) => (c.projectId === id ? { ...c, projectId: null } : c)),
    );
    void deleteProject(id).catch((cause) => {
      setProjects(previousProjects);
      setConversations(previousConversations);
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't delete project",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  // --- Tags + archive + bulk actions (Conversation Org v2) ------------------
  //
  // Each mutation follows the same optimistic shape as the project handlers:
  // snapshot -> setState -> fire-and-forget -> rollback + toast on error.

  // Small shared error toast for these handlers (rollback already applied).
  const showMutationError = (cause: unknown, fallback: string) => {
    if (cause instanceof ApiError) setLiveMessage(cause.title);
    showToast({
      severity: "error",
      title: cause instanceof ApiError ? cause.title : fallback,
      body:
        cause instanceof ApiError
          ? cause.body
          : cause instanceof Error
            ? cause.message
            : undefined,
    });
  };

  const handleSetTagFilter = (tagId: string | null) => {
    setActiveTagId(tagId);
  };

  // Create a tag. Optimistic insert with a temp id swapped for the server row.
  const handleCreateTag = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const tempId = `temp-tag-${crypto.randomUUID()}`;
    const optimistic: Tag = {
      id: tempId,
      name: trimmed,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setTags((prev) => [...prev, optimistic]);
    void createTag({ name: trimmed })
      .then((created) => {
        setTags((prev) => prev.map((t) => (t.id === tempId ? created : t)));
      })
      .catch((cause) => {
        setTags((prev) => prev.filter((t) => t.id !== tempId));
        showMutationError(cause, "Couldn't create tag");
      });
  };

  const handleRenameTag = (id: string, name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const previous = tags;
    const target = previous.find((t) => t.id === id);
    if (!target || target.name === trimmed) return;
    setTags((prev) =>
      prev.map((t) => (t.id === id ? { ...t, name: trimmed } : t)),
    );
    void updateTag(id, { name: trimmed }).catch((cause) => {
      setTags(previous);
      showMutationError(cause, "Couldn't rename tag");
    });
  };

  // Delete a tag. Optimistically drop the tag AND strip it from every
  // conversation's `tagIds` (the BE removes the join rows); rollback both.
  const handleDeleteTag = (id: string) => {
    const previousTags = tags;
    const previousConversations = conversations;
    if (activeTagId === id) setActiveTagId(null);
    setTags((prev) => prev.filter((t) => t.id !== id));
    setConversations((prev) =>
      prev.map((c) =>
        (c.tagIds ?? []).includes(id)
          ? { ...c, tagIds: (c.tagIds ?? []).filter((tid) => tid !== id) }
          : c,
      ),
    );
    void deleteTag(id).catch((cause) => {
      setTags(previousTags);
      setConversations(previousConversations);
      showMutationError(cause, "Couldn't delete tag");
    });
  };

  // Full-replace a single conversation's tag set (PATCH tagIds).
  const handleAssignConversationTags = (id: string, tagIds: string[]) => {
    const previous = conversations;
    const target = previous.find((c) => c.id === id);
    if (!target) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, tagIds } : c)),
    );
    void patchConversation(id, { tagIds }).catch((cause) => {
      setConversations(previous);
      showMutationError(cause, "Couldn't update tags");
    });
  };

  // Archive / unarchive a single conversation (PATCH archived).
  const handleArchiveConversation = (id: string, archived: boolean) => {
    const previous = conversations;
    const target = previous.find((c) => c.id === id);
    if (!target || (target.archived ?? false) === archived) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, archived } : c)),
    );
    void patchConversation(id, { archived }).catch((cause) => {
      setConversations(previous);
      showMutationError(
        cause,
        archived ? "Couldn't archive conversation" : "Couldn't unarchive conversation",
      );
    });
  };

  // Bulk archive/unarchive: snapshot the whole list, apply to all selected ids,
  // one API call, rollback the whole snapshot on error.
  const handleBulkArchive = (ids: string[], archived: boolean) => {
    if (ids.length === 0) return;
    const previous = conversations;
    const idSet = new Set(ids);
    setConversations((prev) =>
      prev.map((c) => (idSet.has(c.id) ? { ...c, archived } : c)),
    );
    void bulkConversationAction({
      conversationIds: ids,
      action: archived ? "archive" : "unarchive",
    }).catch((cause) => {
      setConversations(previous);
      showMutationError(cause, "Couldn't update conversations");
    });
  };

  // Bulk delete: snapshot, drop all selected ids, one API call, rollback on
  // error. If the active conversation was deleted, fall back to a new chat.
  const handleBulkDelete = (ids: string[]) => {
    if (ids.length === 0) return;
    const previous = conversations;
    const idSet = new Set(ids);
    setConversations((prev) => prev.filter((c) => !idSet.has(c.id)));
    if (activeConversationId && idSet.has(activeConversationId)) {
      handleNewChat();
    }
    void bulkConversationAction({
      conversationIds: ids,
      action: "delete",
    }).catch((cause) => {
      setConversations(previous);
      showMutationError(cause, "Couldn't delete conversations");
    });
  };

  // Bulk add/remove a tag across the selected conversations.
  const handleBulkAddTag = (ids: string[], tagId: string) => {
    if (ids.length === 0) return;
    const previous = conversations;
    const idSet = new Set(ids);
    setConversations((prev) =>
      prev.map((c) =>
        idSet.has(c.id) && !(c.tagIds ?? []).includes(tagId)
          ? { ...c, tagIds: [...(c.tagIds ?? []), tagId] }
          : c,
      ),
    );
    void bulkConversationAction({
      conversationIds: ids,
      action: "tag",
      tagId,
    }).catch((cause) => {
      setConversations(previous);
      showMutationError(cause, "Couldn't tag conversations");
    });
  };

  const handleBulkRemoveTag = (ids: string[], tagId: string) => {
    if (ids.length === 0) return;
    const previous = conversations;
    const idSet = new Set(ids);
    setConversations((prev) =>
      prev.map((c) =>
        idSet.has(c.id)
          ? { ...c, tagIds: (c.tagIds ?? []).filter((tid) => tid !== tagId) }
          : c,
      ),
    );
    void bulkConversationAction({
      conversationIds: ids,
      action: "untag",
      tagId,
    }).catch((cause) => {
      setConversations(previous);
      showMutationError(cause, "Couldn't untag conversations");
    });
  };

  const handlePreferencesChange = (next: UserPreferences) => {
    if (!bootstrap) return;
    const previous = bootstrap.preferences;
    if (next.defaultTierId !== previous.defaultTierId) {
      reportTelemetry(previous, "tier.changed", {
        fromTierId: previous.defaultTierId,
        toTierId: next.defaultTierId,
        surface: "settings",
      });
    }
    setBootstrap({ ...bootstrap, preferences: next });
    void putPreferences(next).catch((cause) => {
      setBootstrap((prev) =>
        prev ? { ...prev, preferences: previous } : prev,
      );
      if (cause instanceof ApiError) setLiveMessage(cause.title);
      // Surface the rollback to sighted users too (e.g. a 429), matching the
      // rename / pin handlers — a silent revert is invisible otherwise. (P1-2)
      showToast({
        severity: "error",
        title:
          cause instanceof ApiError ? cause.title : "Couldn't save your preferences",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined,
      });
    });
  };

  // Persist a new monthly spend cap (Feature 3). Routes through the SAME
  // optimistic preferences flow as every other setting — `handlePreferencesChange`
  // already does the optimistic setBootstrap + PUT + rollback-on-error — so the
  // cap rides the existing wire path and surfacing instead of a bespoke one.
  const handleSaveBudget = (value: number | null) => {
    if (!bootstrap) return;
    handlePreferencesChange({
      ...bootstrap.preferences,
      monthlyBudgetUsd: value,
    });
  };

  const settingsOpenRef = useRef(settingsOpen);

  // Open the Settings hub, optionally deep-linked to a tab. Memory/Templates/
  // Models/Shortcuts/Activity are tabs in the hub now, so their entry points
  // pass the target tab here instead of opening a sibling dialog.
  const openSettings = (tab: SettingsTab = "general") => {
    setSettingsInitialTab(tab);
    if (!settingsOpenRef.current) {
      settingsOpenRef.current = true;
      reportTelemetry(preferences, "settings.opened");
      reportTelemetry(preferences, "usage.viewed", {
        isByok: usage?.isByok ?? null,
      });
    }
    setSettingsOpen(true);
  };

  const handleSettingsOpenChange = (open: boolean) => {
    if (open) {
      openSettings();
      return;
    }
    settingsOpenRef.current = false;
    setSettingsOpen(false);
  };

  const handleAttributionOpen = () => {
    reportTelemetry(preferences, "attribution.opened", {
      conversationId: activeConversationId,
    });
  };

  const handleAccountChange = async (next: AccountInfo) => {
    setBootstrap((prev) => (prev ? { ...prev, account: next } : prev));
    try {
      const refreshed = await fetchBootstrap();
      setBootstrap((prev) =>
        prev
          ? {
              ...prev,
              account: refreshed.account,
              usage: refreshed.usage,
              modelTiers: refreshed.modelTiers,
            }
          : refreshed,
      );
      reconcileProviderAvailability(
        refreshed.modelTiers,
        selectedProviderIdRef.current ?? readStoredPreferredProviderId(),
      );
    } catch (cause) {
      showToast({
        severity: "warning",
        title: "Availability not refreshed",
        body:
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : "Reload to refresh provider availability.",
      });
    }
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

  // Account data export: the BE returns raw JSON; the fetch client ignores
  // Content-Disposition, so build the download client-side from the payload.
  const handleExportData = () => {
    void fetchAccountExport()
      .then((data) => {
        if (typeof window === "undefined" || typeof document === "undefined")
          return;
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "account-export.json";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setLiveMessage("Your data was downloaded");
        showToast({ severity: "success", title: "Your data was downloaded" });
      })
      .catch((cause) => {
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't export your data";
        const body =
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined;
        showToast({ severity: "error", title, body });
      });
  };

  // Delete account + full reload. The BE clears the cookie, so the reload
  // bootstraps as a fresh anonymous user (identical pattern to sign-out).
  const handleDeleteAccount = (confirmation: string) => {
    void deleteAccount(confirmation)
      .then(() => {
        setLiveMessage("Account deleted");
        if (typeof window !== "undefined") window.location.reload();
      })
      .catch((cause) => {
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't delete account";
        const body =
          cause instanceof ApiError
            ? cause.body
            : cause instanceof Error
              ? cause.message
              : undefined;
        showToast({ severity: "error", title, body });
      });
  };

  // Sign-in / account-creation success: close the dialog and full-reload so
  // bootstrap re-runs against the now-registered session. A reload (rather than
  // a local re-fetch) is the correct call here — login swaps identity wholesale
  // (conversations, prefs, usage, account), and the conversation list only
  // hydrates once per mount (see `conversationsHydratedRef`), so a partial
  // re-fetch would leave the sidebar showing the guest's chats. This mirrors
  // `handleSignOut` exactly, keeping both identity transitions on one path.
  const handleAuthSuccess = () => {
    setAuthOpen(false);
    setLiveMessage("Signed in");
    if (typeof window !== "undefined") window.location.reload();
  };

  const showWelcome =
    !compareMode &&
    ((messages.length === 0 && !pendingMessage) || welcomeExiting);

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

  const markdownFilename = (title: string | null | undefined): string => {
    const safeTitle = (title || "conversation")
      .trim()
      .replace(/[^\w\s.-]/g, "")
      .replace(/\s+/g, "-")
      .slice(0, 80);
    return `${safeTitle || "conversation"}.md`;
  };

  const downloadMarkdown = (payload: string, title?: string | null): void => {
    if (!payload) {
      setLiveMessage("Nothing to download");
      showToast({ severity: "info", title: "Nothing to download" });
      return;
    }
    const blob = new Blob([payload], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = markdownFilename(title);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    setLiveMessage("Conversation downloaded");
    showToast({ severity: "info", title: "Conversation downloaded" });
  };

  const handleDownloadConversation = () => {
    const activeTitle =
      conversations.find((conversation) => conversation.id === activeConversationId)
        ?.title ?? "conversation";
    downloadMarkdown(renderConversationMarkdown(messages), activeTitle);
  };

  // --- PDF + Word export (T12) ----------------------------------------------

  const exportFilename = (
    title: string | null | undefined,
    ext: string,
  ): string => {
    const safeTitle = (title || "conversation")
      .trim()
      .replace(/[^\w\s.-]/g, "")
      .replace(/\s+/g, "-")
      .slice(0, 80);
    return `${safeTitle || "conversation"}.${ext}`;
  };

  const escapeHtml = (value: string): string =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  // Build a self-contained HTML rendering of the settled thread (same turn
  // selection as the Markdown export). Each turn becomes a role heading plus
  // paragraphs, with blank-line-delimited paragraphs and single newlines kept
  // as line breaks. Shared by the PDF (print) and Word (.docx) exporters.
  const renderConversationTurnsHtml = (
    source: ReadonlyArray<ChatMessage>,
  ): string => {
    const blocks: string[] = [];
    for (const m of source) {
      if (
        m.role === "assistant" &&
        (m.status === "error" ||
          m.status === "submitted" ||
          m.status === "streaming")
      ) {
        continue;
      }
      const text = m.parts
        .filter((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
        .map((p) => p.text)
        .join("\n\n")
        .trim();
      if (!text) continue;
      const role = m.role === "user" ? "You" : "Assistant";
      const paragraphs = text
        .split(/\n{2,}/)
        .map(
          (para) =>
            `<p>${escapeHtml(para).replace(/\n/g, "<br/>")}</p>`,
        )
        .join("");
      blocks.push(
        `<section class="turn turn-${m.role}"><h2>${role}</h2>${paragraphs}</section>`,
      );
    }
    return blocks.join("\n");
  };

  const conversationDocumentHtml = (
    source: ReadonlyArray<ChatMessage>,
    title: string | null | undefined,
    forPrint: boolean,
  ): string => {
    const heading = escapeHtml((title || "Conversation").trim() || "Conversation");
    const body = renderConversationTurnsHtml(source);
    // Print CSS lives inside the generated document so it prints cleanly
    // regardless of the app's (virtualized) message list. Word ignores most of
    // it but reads the basic typography.
    const printAuto = forPrint
      ? "<script>window.onload=function(){window.focus();window.print();}</script>"
      : "";
    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>${heading}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; color: #111; line-height: 1.5; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.4rem; margin: 0 0 1.5rem; }
  .turn { margin: 0 0 1.5rem; padding: 0 0 1.25rem; border-bottom: 1px solid #e5e7eb; }
  .turn:last-child { border-bottom: none; }
  .turn h2 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin: 0 0 0.5rem; }
  .turn-user h2 { color: #2563eb; }
  p { margin: 0 0 0.75rem; white-space: normal; }
  @media print {
    body { margin: 0; max-width: none; }
    .turn { break-inside: avoid; }
  }
</style></head>
<body><h1>${heading}</h1>${body}${printAuto}</body></html>`;
  };

  // PDF export: render the conversation into a hidden same-origin iframe with
  // its own `@media print` stylesheet, then invoke the browser's print dialog
  // (Save as PDF). Using a generated document rather than `window.print()` on
  // the live page sidesteps the virtualized message list (off-screen turns
  // aren't in the DOM) and the app chrome.
  const activeConversationTitleNow = (): string | null =>
    conversations.find((c) => c.id === activeConversationId)?.title ?? null;

  const handlePrintConversation = () => {
    const source = messages;
    const html = renderConversationTurnsHtml(source);
    if (!html) {
      setLiveMessage("Nothing to export");
      showToast({ severity: "info", title: "Nothing to export" });
      return;
    }
    const iframe = document.createElement("iframe");
    iframe.setAttribute("aria-hidden", "true");
    iframe.style.position = "fixed";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.width = "0";
    iframe.style.height = "0";
    iframe.style.border = "0";
    iframe.style.opacity = "0";
    document.body.appendChild(iframe);
    const cleanup = () => {
      window.setTimeout(() => iframe.remove(), 1000);
    };
    const doc = iframe.contentWindow?.document;
    if (!doc) {
      iframe.remove();
      showToast({ severity: "error", title: "Couldn't open print view" });
      return;
    }
    // The iframe load fires after the document is written; the auto-print
    // script inside the doc focuses + prints. We still clean the iframe up.
    iframe.onload = cleanup;
    doc.open();
    doc.write(conversationDocumentHtml(source, activeConversationTitleNow(), true));
    doc.close();
    setLiveMessage("Opening print view");
  };

  // Word export: a minimal HTML-flavored .docx — Word opens HTML content saved
  // with the OOXML mime, which is the documented lightweight fallback (no OOXML
  // zip packaging needed for a text export).
  const handleDownloadDocx = () => {
    const html = renderConversationTurnsHtml(messages);
    if (!html) {
      setLiveMessage("Nothing to export");
      showToast({ severity: "info", title: "Nothing to export" });
      return;
    }
    const title = activeConversationTitleNow();
    const doc = conversationDocumentHtml(messages, title, false);
    const blob = new Blob([doc], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = exportFilename(title, "docx");
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    setLiveMessage("Conversation downloaded");
    showToast({ severity: "info", title: "Conversation downloaded (Word)" });
  };

  const handleDownloadConversationById = (id: string) => {
    if (id === activeConversationId) {
      handleDownloadConversation();
      return;
    }
    void (async () => {
      try {
        const conversation = await fetchConversation(id);
        downloadMarkdown(
          renderConversationMarkdown(conversation.messages),
          conversation.title,
        );
      } catch (cause) {
        const title =
          cause instanceof ApiError ? cause.title : "Couldn't download conversation";
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
    openSettings();
  };

  const handleOpenShare = () => {
    setShareOpen(true);
  };

  // Sharing is only meaningful once the active conversation is a real,
  // persisted (non-temporary) row: temporary chats 404 on the share routes,
  // and before the first send no conversation exists yet. The header gates the
  // menu item on this flag and the dialog is only fed a real id.
  const canShareActiveConversation =
    activeConversationId !== null && !isTemporary;

  // The active conversation's title (for the dialog's heading copy). Falls back
  // to null when the row isn't in the list yet (e.g. just created); the dialog
  // copes with a null title.
  const activeConversationTitle = activeConversationId
    ? conversations.find((c) => c.id === activeConversationId)?.title ?? null
    : null;

  // Project/Space context for a NEW chat (D20): when the user is viewing a
  // conversation filed under a known project, a fresh chat started from that
  // context inherits the project (so the BE pre-seeds its default tier and
  // scopes its instructions/retention/budget). On the welcome screen (no active
  // conversation) a new chat is unfiled. A `projectId` pointing at a project not
  // in the current list (stale) is treated as unfiled.
  const activeProjectId: string | null = (() => {
    if (!activeConversationId) return null;
    const active = conversations.find((c) => c.id === activeConversationId);
    const pid = active?.projectId ?? null;
    if (pid && projects.some((p) => p.id === pid)) return pid;
    return null;
  })();
  useEffect(() => {
    activeProjectIdRef.current = activeProjectId;
  }, [activeProjectId]);

  // Custom instructions live inside the settings dialog in MVP; wiring the
  // shortcut now so muscle memory transfers when a dedicated panel ships.
  const handleOpenCustomInstructions = () => {
    openSettings();
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

  const visibleConversationSearchResults = useMemo(() => {
    const query = conversationSearch.trim();
    if (
      query.length === 0 ||
      conversationSearchState === null ||
      conversationSearchState.query !== query ||
      conversationSearchState.results === null
    ) {
      return null;
    }
    return conversationSearchState.results;
  }, [conversationSearch, conversationSearchState]);
  const conversationSearchPending =
    conversationSearch.trim().length > 0 &&
    conversationSearchState?.query === conversationSearch.trim() &&
    conversationSearchState.pending;

  // The hook syncs `boundShortcuts` to a ref each render, so we can build a
  // fresh array (and a fresh `runAction`) every render without re-binding the
  // keydown listener or capturing stale state.
  const runAction = (id: ShortcutId): void => {
    switch (id) {
      case "palette":
        // Plain palette summon always lands in the default action/conversation
        // listbox (never filter mode).
        setPaletteFilterMode(false);
        setPaletteOpen((v) => !v);
        return;
      case "new-chat":
        handleNewChat();
        return;
      case "search-history":
        // Search history opens the palette straight into filter mode (the
        // folded advanced history search) — no separate dialog.
        setPaletteFilterMode(true);
        setPaletteOpen(true);
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
      case "toggle-dictation":
        composerRef.current?.toggleDictation();
        return;
      case "shortcuts":
        // Folded into the Settings hub: the hotkey/palette open the hub on the
        // Shortcuts tab rather than a standalone dialog.
        openSettings("shortcuts");
        return;
      case "open-settings":
        handleOpenSettings();
        return;
      case "toggle-theme":
        handleToggleTheme();
        return;
    }
  };

  // The EFFECTIVE bindings = built-in defaults merged with the user's saved
  // overrides (D23). Drives the live keydown matcher, the palette keycaps, and
  // the shortcuts dialog so a remap takes effect everywhere at once.
  // `preferences` can be null before the bootstrap render-gate below, so fall
  // back to "no overrides". `deserializeShortcuts` hardens the wire value: it
  // drops unknown action ids and malformed combos so a stale/forward-compatible
  // payload can never crash the resolver.
  const shortcutOverrides: KeyboardShortcuts = deserializeShortcuts(
    preferences?.keyboardShortcuts,
    REBINDABLE_IDS,
  );
  const effectiveBindings = resolveBindings(DEFAULT_BINDINGS, shortcutOverrides);

  const boundShortcuts: Shortcut[] = KEY_BINDINGS.map((b) => ({
    ...effectiveBindings[b.id],
    handler: () => runAction(b.id),
  }));
  useKeyboardShortcuts(boundShortcuts);

  // Palette actions: every keyboard-bound entry that isn't "Hidden", plus
  // the palette-only Settings/Theme entries. Icon set is hand-picked to stay
  // visually quiet (no emoji, all stroke icons).
  const shortcutBoundActions: CommandAction[] = PALETTE_ACTION_META.map(
    (meta) => ({
      id: meta.id,
      label: meta.label,
      icon: meta.icon,
      shortcut: meta.hasBinding ? effectiveBindings[meta.id] : undefined,
      section: meta.section,
      keywords: PALETTE_ACTION_KEYWORDS[meta.id],
      run: () => runAction(meta.id),
    }),
  );

  // Palette-only management destinations (M1 — the palette is the universal
  // action spine). Each routes into the EXISTING Settings-tab hub via
  // `openSettings(tab)` — no logic is duplicated; these are thin entry points to
  // the same surfaces the hub already owns. They carry their own `run` closures
  // (no `ShortcutId`, no global keystroke) and rich keyword aliases so
  // type-to-find lands them from synonyms ("usage" → Spend, "filters" →
  // Advanced search). Spend has no dedicated tab; its dashboard (UsageDetails +
  // SpendDialog + BudgetEditor) lives on the General tab, so "Spend" deep-links
  // there — NOT the Activity tab, which is the data-access/audit log.
  const managementActions: CommandAction[] = [
    {
      id: "palette-advanced-search",
      label: "Advanced search",
      icon: SlidersHorizontal,
      section: "Actions",
      keywords: [
        "advanced search",
        "search history",
        "filter",
        "filters",
        "find",
        "model",
        "cost",
        "date",
        "project",
      ],
      // Switches the palette into its in-place filter mode (the folded history
      // search) — handled in the palette, so `run` is a no-op fallback.
      entersFilterMode: true,
      run: () => undefined,
    },
    {
      id: "palette-memory",
      label: "Memory",
      icon: Brain,
      section: "Settings",
      keywords: ["memory", "facts", "remember", "knowledge"],
      run: () => openSettings("memory"),
    },
    {
      id: "palette-templates",
      label: "Templates",
      icon: FileText,
      section: "Settings",
      keywords: ["templates", "prompt", "prompts", "snippets"],
      run: () => openSettings("templates"),
    },
    {
      id: "palette-models",
      label: "Models",
      icon: Boxes,
      section: "Settings",
      keywords: ["models", "model directory", "tiers", "providers"],
      run: () => openSettings("models"),
    },
    {
      id: "palette-activity",
      label: "Activity",
      icon: ActivityIcon,
      section: "Settings",
      keywords: ["activity", "data access", "events", "audit", "log"],
      run: () => openSettings("activity"),
    },
    {
      id: "palette-spend",
      label: "Spend",
      icon: DollarSign,
      section: "Settings",
      keywords: ["spend", "usage", "cost", "billing", "budget", "analytics"],
      run: () => openSettings("general"),
    },
    {
      id: "palette-compare",
      label: compareMode ? "Exit compare" : "Compare models",
      icon: Columns2,
      section: "Actions",
      keywords: ["compare", "compare models", "side by side", "two models", "ab"],
      run: handleToggleCompare,
    },
    {
      id: "palette-new-project",
      label: "New project",
      icon: FolderPlus,
      section: "Actions",
      keywords: ["new project", "create project", "collection", "folder"],
      run: handlePaletteNewProject,
    },
    {
      id: "palette-new-tag",
      label: "New tag",
      icon: TagIcon,
      section: "Actions",
      keywords: ["new tag", "create tag", "label"],
      run: handlePaletteNewTag,
    },
  ];

  const paletteActions: CommandAction[] = [
    ...shortcutBoundActions,
    ...managementActions,
  ];

  // Sections rendered by the shortcuts dialog (Hidden entries surface here
  // too so power users see Cmd+K listed). Ordered to match the PRD §5.5 table.
  // Each row carries its id + effective keystroke so the dialog can render
  // (and, in editable mode, rebind) it.
  const shortcutSections: ShortcutSection[] = SHORTCUT_DIALOG_SECTIONS.map(
    (section) => ({
      heading: section.heading,
      items: section.ids.map((id) => ({
        id,
        label: LABEL_BY_ID[id],
        shortcut: effectiveBindings[id],
        isOverridden: shortcutOverrides[id] != null,
      })),
    }),
  );

  // Persist a new override map through the SAME optimistic preferences flow as
  // every other setting (`handlePreferencesChange` does setBootstrap + PUT +
  // rollback-on-error). The rebind dialog hands us the already-guarded map;
  // `serializeShortcuts` canonicalizes it — dropping any override that equals
  // its default — so the stored column stays minimal and self-healing.
  const handleShortcutsChange = (next: KeyboardShortcuts): void => {
    if (!bootstrap) return;
    handlePreferencesChange({
      ...bootstrap.preferences,
      keyboardShortcuts: serializeShortcuts(next, DEFAULT_BINDINGS),
    });
  };

  // --- Render guards ------------------------------------------------------
  // Bootstrap is the gate: nothing renders the main shell until we have the
  // account + preferences + tier registry. Both states are intentionally tiny
  // — there's no FE auth surface, so the user can't recover from a failure
  // other than retrying.

  if (bootstrapError) {
    return (
      <div className="flex h-full min-h-svh items-center justify-center p-6">
        <div className="max-w-sm space-y-4 text-center">
          <h1 className="text-lg font-semibold">{bootstrapError.title}</h1>
          <p className="text-sm text-muted-foreground">{bootstrapError.body}</p>
          <Button
            type="button"
            onClick={() => {
              // Abort any genuinely in-flight bootstrap and clear the latch so
              // the re-run actually fetches instead of short-circuiting on a
              // stale `inFlight === true`. (P1-5)
              bootstrapControllerRef.current?.abort();
              bootstrapControllerRef.current = null;
              bootstrapInFlightRef.current = false;
              setBootstrapError(null);
              setBootstrapAttempt((n) => n + 1);
            }}
            className="h-11 rounded-full px-5"
          >
            Try again
          </Button>
        </div>
      </div>
    );
  }

  if (!bootstrap || !account || !preferences || !usage) {
    return (
      <div
        role="status"
        aria-busy="true"
        className="flex h-full min-h-svh items-center justify-center"
      >
        <LoaderCircle
          aria-hidden
          className="size-6 text-muted-foreground motion-safe:animate-spin"
        />
        <span className="sr-only">Loading Olune…</span>
      </div>
    );
  }

  const suggestions = bootstrap.suggestions;
  // Delete-account requires the user to type their email (or "DELETE" when
  // anonymous), matching the BE's confirmation contract.
  const deleteConfirmExpected = account.email || "DELETE";
  const deleteConfirmMatches =
    deleteConfirmText.trim() === deleteConfirmExpected;

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            conversations={conversations}
            activeId={activeConversationId}
            account={account}
            search={conversationSearch}
            searchResults={visibleConversationSearchResults}
            searchPending={conversationSearchPending}
            onSearchChange={setConversationSearch}
            onOpenAdvancedSearch={() => {
              setPaletteFilterMode(true);
              setPaletteOpen(true);
            }}
            onSelect={handleSelectConversation}
            onNewChat={handleNewChat}
            onRenameConversation={handleRenameConversation}
            onDeleteConversation={handleDeleteConversation}
            onTogglePinConversation={handleTogglePinConversation}
            onSetConversationRetention={handleSetConversationRetention}
            onCopyConversation={handleCopyConversationById}
            onDownloadConversation={handleDownloadConversationById}
            onOpenSettings={handleOpenSettings}
            projects={projects}
            onAssignConversationToProject={handleAssignConversationToProject}
            onCreateProject={handleCreateProject}
            onRenameProject={handleRenameProject}
            onDeleteProject={handleDeleteProject}
            onManageProjects={handleOpenSettings}
            tags={tags}
            activeTagId={activeTagId}
            onSetTagFilter={handleSetTagFilter}
            onCreateTag={handleCreateTag}
            onRenameTag={handleRenameTag}
            onDeleteTag={handleDeleteTag}
            onAssignConversationTags={handleAssignConversationTags}
            onArchiveConversation={handleArchiveConversation}
            onBulkArchive={handleBulkArchive}
            onBulkDelete={handleBulkDelete}
            onBulkAddTag={handleBulkAddTag}
            onBulkRemoveTag={handleBulkRemoveTag}
            onSignIn={() => setAuthOpen(true)}
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
          {/* Page heading for the chat view — visually hidden so the design is
              unchanged, but the document/landmark gets an <h1> for screen
              readers. Carries the active conversation title with a sensible
              default before one exists / while untitled. (A11Y-5) */}
          <h1 className="sr-only">{activeConversationTitle ?? "New chat"}</h1>
          {/* First-run hero atmosphere: the --hero-gradient backdrop (brand
              wash falling from the top edge + counter-bloom rising behind the
              composer) with the radial --welcome-ambient greeting halo layered
              above it, per the token contract in globals.css. Welcome-only,
              decorative, vignetted by the z-30 chrome strips. Same fade as the
              old single-halo layer: in on mount, out at the welcome→thread
              exit seam; static at rest. Both tokens zero under
              prefers-contrast, and motion-reduce collapses the fade. */}
          {showWelcome ? (
            <div
              aria-hidden
              className={cn(
                "pointer-events-none absolute inset-0 [background:var(--welcome-ambient),var(--hero-gradient)] transition-opacity duration-700 ease-out starting:opacity-0 motion-reduce:transition-none",
                welcomeExiting ? "opacity-0" : "opacity-100",
              )}
            />
          ) : null}
          {/* Top chrome strip — positions the floating buttons (and the
              temporary-chat banner when on) at the top with safe-area
              reservation. The strip now FROSTS the content beneath it rather
              than wiping it with an opaque fade: a masked backdrop-blur layer
              (below) carries the separation, so messages scrolling under the
              notch read as glass-occluded rather than dissolving into a flat
              band — the headline iOS-26 fidelity fix. The color gradient is
              kept but much LIGHTER (from-background/70, no opaque stop) purely
              to preserve status-bar-text legibility at the very top edge; the
              blur does the heavy lifting now. */}
          <div className="pointer-events-none absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-background/70 via-background/30 to-background/0 pt-[env(safe-area-inset-top)] pr-[env(safe-area-inset-right)] pb-6 pl-[env(safe-area-inset-left)] md:pb-12">
            {/* Refractive blur layer. Absolutely fills the strip and blurs the
                messages behind it, then fades the blur OUT toward the bottom
                with a linear mask so the frost dies exactly where the color
                gradient does — no hard blur seam over live message text.
                pointer-events-none so taps fall through to messages wherever
                the strip is visually transparent. The blur lives in the
                `chrome-frost` utility (globals.css) precisely so it can be
                gated under prefers-reduced-transparency / no-backdrop-filter —
                there the frost drops to nothing and the light color gradient
                above is the fallback separation. The mask direction is
                strip-specific, so it stays inline. */}
            <div
              aria-hidden
              className="chrome-frost pointer-events-none absolute inset-0 -z-10"
              style={{
                maskImage: "linear-gradient(to bottom, black, transparent)",
                WebkitMaskImage: "linear-gradient(to bottom, black, transparent)",
              }}
            />
            <div className="pointer-events-auto">
              <AppHeader
                sidebarOpen={sidebarOpen}
                onOpenMobileNav={() => setMobileNavOpen(true)}
                onOpenSidebar={() => setSidebarOpen(true)}
                onNewChat={handleNewChat}
                isTemporary={isTemporary}
                onToggleTemporary={handleToggleTemporary}
                onCopyConversation={handleCopyConversation}
                canCopyConversation={messages.length > 0}
                onDownloadConversation={handleDownloadConversation}
                canDownloadConversation={messages.length > 0}
                onPrintConversation={handlePrintConversation}
                onDownloadDocx={handleDownloadDocx}
                onShareConversation={handleOpenShare}
                canShareConversation={canShareActiveConversation}
                centerSlot={
                  // Welcome-only centered wordmark — the brand moment lives on
                  // the first-run surface (the sidebar wordmark stays demoted
                  // per anti-pattern G). Serif to rhyme with the hero greeting;
                  // fades with the same 200ms welcome-exit seam, and aria-hidden
                  // because the sr-only <h1> already names the surface.
                  showWelcome ? (
                    <span
                      aria-hidden
                      className={cn(
                        "font-heading text-xl tracking-tight text-foreground/90 transition-opacity duration-200 ease-[var(--ease-welcome)] starting:opacity-0 motion-reduce:transition-none",
                        welcomeExiting ? "opacity-0" : "opacity-100",
                      )}
                    >
                      Olune
                    </span>
                  ) : undefined
                }
              />
              {isTemporary && !degradedActive ? (
                <TemporaryChatBanner onTurnOff={handleToggleTemporary} />
              ) : null}
              <DegradedStatusBanner onActiveChange={setDegradedActive} />
            </div>
          </div>

          {/* Message area — compare mode takes over the whole surface with its
              own 2-up scroll wrapper. Otherwise: WelcomeScreen gets a single
              scroll wrapper that clears both strips, and MessageList owns its
              scroll (its internal `<ol>` has matching pt/pb that clears the
              chrome). */}
          {compareMode && compareTierA && compareTierB ? (
            <div
              className={cn(
                "relative min-h-0 flex-1 overflow-y-auto pr-[env(safe-area-inset-right)] pb-[calc(var(--bottom-inset)+12rem)] pl-[env(safe-area-inset-left)]",
                CHAT_CHROME_PAD_CLASS,
              )}
              style={topChromePaddingStyle("compare", {
                isTemporary,
                statusBannerActive: degradedActive,
              })}
            >
              <CompareView
                tiers={[compareTierA, compareTierB]}
                userMessage={compareUserMessage}
                turn={compareTurn}
                defaultReasoningOpen={preferences.autoExpandReasoning}
                handleRef={compareViewRef}
                onStreamingChange={setCompareStreaming}
              />
            </div>
          ) : showWelcome ? (
            // Welcome state is the canonical Ma surface (Decision 11; Spacing §Ma).
            // Padding on each side equals the chrome floor it must clear, so the
            // greeting sits at the true visual center of the uncovered area —
            // not biased toward either the header or the composer.
            <div
              className={cn(
                "relative min-h-0 flex-1 overflow-y-auto pr-[env(safe-area-inset-right)] pb-[calc(var(--bottom-inset)+10rem)] pl-[env(safe-area-inset-left)] md:pb-[calc(var(--bottom-inset)+12rem)]",
                CHAT_CHROME_PAD_CLASS,
              )}
              style={topChromePaddingStyle("welcome", {
                isTemporary,
                statusBannerActive: degradedActive,
              })}
            >
              <WelcomeScreen
                userName={firstName}
                exiting={welcomeExiting}
                onPromptSelect={handlePromptSelect}
                suggestions={suggestions}
                onConnect={() => openSettings()}
                compact={conversations.length > 0}
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
              <MessageList
                isTemporary={isTemporary}
                statusBannerActive={degradedActive}
              >
                {messages.map((m) => {
                  const canBranchMessage =
                    !!activeConversationId &&
                    !isTemporary &&
                    !isStreaming &&
                    !m.id.startsWith("local-");
                  return m.role === "user" ? (
                    <UserMessage
                      key={m.id}
                      message={m}
                      canEdit={!isStreaming && !m.id.startsWith("local-")}
                      canBranch={canBranchMessage}
                      isBranching={branchingMessageId === m.id}
                      onEdit={(newText) => handleEditUserMessage(m.id, newText)}
                      onBranch={
                        canBranchMessage
                          ? () => handleBranchFromMessage(m.id)
                          : undefined
                      }
                    />
                  ) : (
                    <AssistantMessage
                      key={m.id}
                      message={m}
                      status={m.status ?? "done"}
                      canBranch={canBranchMessage}
                      isBranching={branchingMessageId === m.id}
                      canRegenerate={
                        !isStreaming &&
                        m.id === lastAssistantId &&
                        ((m.status ?? "done") === "done" || m.status === "stopped")
                      }
                      canContinue={
                        !isStreaming &&
                        m.id === lastAssistantId &&
                        m.status === "stopped"
                      }
                      isAwaitingApproval={
                        !isStreaming &&
                        m.id === lastAssistantId &&
                        m.status === "awaiting_approval"
                      }
                      onBranch={
                        canBranchMessage
                          ? () => handleBranchFromMessage(m.id)
                          : undefined
                      }
                      onRegenerate={handleRegenerate}
                      onRegenerateWith={handleRegenerateWith}
                      regenerateOptions={{
                        tiers: modelTiers,
                        providerOptions,
                        selectedTierId,
                      }}
                      onContinue={handleContinue}
                      onToolDecision={(d) => handleToolDecision(m.id, d)}
                      onFeedback={(f) => setFeedback(m.id, f)}
                      onFollowUp={handlePromptSelect}
                      showFollowUps={
                        !isStreaming && m.id === lastAssistantId
                      }
                      onAttributionOpen={handleAttributionOpen}
                      onMemoryOpen={() => openSettings("memory")}
                      defaultReasoningOpen={preferences.autoExpandReasoning}
                      error={m.error}
                    />
                  );
                })}

                {pendingMessage ? (
                  <AssistantMessage
                    message={pendingMessage}
                    status={state.status}
                    reasoningStreaming={state.reasoningStreaming}
                    // Agentic mode: live per-worker activity + run-cost meter
                    // for the streaming bubble. Both are empty/null on every
                    // non-agentic turn.
                    liveSubagents={state.subagents}
                    runCost={state.runCost}
                  />
                ) : null}
              </MessageList>
            </div>
          )}

          {/* Bottom chrome strip — mirror of the top: a masked backdrop-blur
              frosts the messages scrolling beneath the composer, and a LIGHT
              color gradient (to-background/70 at the bottom edge) keeps the
              composer capsule's lower edge legible against busy content. The
              blur mask fades to TOP (the inverse of the top strip) so the
              frost dies upward into the live thread. The frost uses the same
              `chrome-frost` utility as the top strip, so it shares the
              reduced-transparency / no-backdrop-filter gating. */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-background/70 via-background/30 to-background/0 pt-6 pr-[env(safe-area-inset-right)] pb-[var(--bottom-inset)] pl-[env(safe-area-inset-left)]">
            <div
              aria-hidden
              className="chrome-frost pointer-events-none absolute inset-0 -z-10"
              style={{
                maskImage: "linear-gradient(to top, black, transparent)",
                WebkitMaskImage: "linear-gradient(to top, black, transparent)",
              }}
            />
            <div className="pointer-events-auto">
              {compareMode ? (
                <CompareTierBar
                  tiers={compareModelTiers}
                  compareTierIds={compareTierIds}
                  onSelect={handleSelectCompareTier}
                />
              ) : null}
              <Composer
                ref={composerRef}
                isStreaming={isBusy}
                onSend={handleSend}
                onStop={handleStop}
                // Offline draft persistence is keyed to the active conversation
                // (null ⇒ the new-chat slot) so an in-progress message survives
                // reloads and conversation switches (T02). Temporary chats are
                // intentionally not persisted — they're off-the-record.
                draftKey={activeConversationId}
                persistDrafts={!isTemporary && !compareMode}
                sendOnEnter={preferences.sendOnEnter}
                // Attachments aren't offered in compare mode — the compare
                // toggle takes the contextual slot and a 2-up transient view
                // doesn't carry per-column attachments in MVP.
                supportsAttachments={
                  !compareMode && selectedTierSupportsAttachments
                }
                supportsVision={selectedTierSupportsVision}
                // Pre-send estimate uses the provider-effective selected tier;
                // suppressed in compare mode (two tiers, no single estimate).
                estimateTier={compareMode ? undefined : selectedModelTier}
                // The model/mode picker now lives in the composer toolbar
                // (Lovable-style) — the same component instance the header
                // used to host, so every testid/aria contract is unchanged.
                modelPicker={
                  <ModelModePicker
                    tiers={modelTiers}
                    selectedTierId={selectedTierId}
                    onSelectTier={handleSelectTier}
                    providerOptions={providerOptions}
                    selectedProviderId={effectiveProviderId}
                    onSelectProvider={handleSelectProvider}
                    efforts={REASONING_EFFORTS}
                    selectedEffortId={selectedReasoningEffortId}
                    onSelectEffort={setSelectedReasoningEffortId}
                    effortSupported={effortSupported}
                    searchEnabled={effectiveSearchEnabled}
                    onToggleSearch={setSearchEnabled}
                    jsonModeEnabled={jsonModeEnabled}
                    onToggleJsonMode={setJsonModeEnabled}
                    showDeepResearch={agenticEnabled}
                    deepResearchEnabled={effectiveDeepResearch}
                    onToggleDeepResearch={setDeepResearchEnabled}
                  />
                }
                // Resting hero glow on the first-run welcome surface only;
                // fades at the welcome→thread exit seam alongside the
                // ambient halo.
                heroGlow={showWelcome && !welcomeExiting}
              />
              <AiDisclosure />
            </div>
          </div>
        </div>
      </AppShell>

      <SettingsDialog
        open={settingsOpen}
        onOpenChange={handleSettingsOpenChange}
        initialTab={settingsInitialTab}
        preferences={preferences}
        onPreferencesChange={handlePreferencesChange}
        account={account}
        onAccountChange={handleAccountChange}
        usage={usage}
        onSaveBudget={handleSaveBudget}
        onSignOut={handleSignOut}
        onRequestSignIn={() => {
          setSettingsOpen(false);
          setAuthOpen(true);
        }}
        onExportData={handleExportData}
        onDeleteAccount={() => {
          setSettingsOpen(false);
          setPendingDeleteAccount(true);
        }}
        projects={projects}
        onUpdateProject={handleUpdateProject}
        // Folded-in hub surfaces (formerly sibling dialogs). The Settings hub
        // now hosts Memory / Templates / Models / Shortcuts / Activity as tabs,
        // so these props feed the in-place bodies instead of opening a sibling.
        memoryEnabled={bootstrap?.preferences.memoryEnabled ?? false}
        onMemoryEnabledChange={(next) => {
          // Reuse the optimistic preferences flow (setBootstrap + PUT +
          // rollback-on-error), exactly like the budget cap, so the toggle
          // rides the existing wire path.
          if (!bootstrap) return;
          handlePreferencesChange({
            ...bootstrap.preferences,
            memoryEnabled: next,
          });
        }}
        onActivitySwitchRoute={() => {
          // Reuse the composer's existing model picker: close the hub and open
          // the picker trigger so the user can switch their route.
          setSettingsOpen(false);
          window.requestAnimationFrame(() => {
            const trigger = document.querySelector<HTMLElement>(
              '[data-testid="model-mode-trigger"]',
            );
            trigger?.focus();
            trigger?.click();
          });
        }}
        shortcuts={shortcutSections}
        shortcutsEditable={false}
        effectiveBindings={effectiveBindings}
        shortcutLabelFor={(id) => LABEL_BY_ID[id]}
        onRebindShortcut={(id, combo) => {
          handleShortcutsChange(setOverride(shortcutOverrides, id, combo));
        }}
        onResetShortcut={(id) => {
          handleShortcutsChange(clearOverride(shortcutOverrides, id));
        }}
        onResetAllShortcuts={() => {
          handleShortcutsChange(resetAllOverrides());
        }}
      />

      <AuthDialog
        open={authOpen}
        onOpenChange={setAuthOpen}
        onSuccess={handleAuthSuccess}
      />

      <ShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        conversationId={activeConversationId}
        conversationTitle={activeConversationTitle}
      />

      <CommandPalette
        open={paletteOpen}
        onOpenChange={(next) => {
          setPaletteOpen(next);
          // Reset the filter-mode intent on close so the next plain summon opens
          // in the default listbox.
          if (!next) setPaletteFilterMode(false);
        }}
        actions={paletteActions}
        conversations={conversations}
        activeId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        // Filter-mode (folded advanced search) data sources.
        projects={projects}
        tags={tags}
        openInFilterMode={paletteFilterMode}
      />

      {/* Quick-create surface for the palette's "New project" / "New tag"
          actions. Uses the shared Base UI Dialog so focus trap, Esc-to-close,
          focus-restore to the invoker, and the reduced-motion transition are all
          inherited (no bespoke a11y plumbing). Submit reuses the existing
          create handlers — no logic duplicated. */}
      <Dialog
        open={paletteCreate !== null}
        onOpenChange={(next) => {
          if (!next) {
            setPaletteCreate(null);
            setPaletteCreateDraft("");
          }
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>
              {paletteCreate === "tag" ? "New tag" : "New project"}
            </DialogTitle>
            <DialogDescription>
              {paletteCreate === "tag"
                ? "Name the tag. You can apply it to conversations from the sidebar."
                : "Name the project. You can file conversations into it from the sidebar."}
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handlePaletteCreateSubmit();
            }}
          >
            <input
              type="text"
              autoComplete="off"
              autoFocus
              value={paletteCreateDraft}
              onChange={(e) => setPaletteCreateDraft(e.target.value)}
              data-testid="palette-create-name-input"
              aria-label={
                paletteCreate === "tag" ? "Tag name" : "Project name"
              }
              placeholder={paletteCreate === "tag" ? "Tag name" : "Project name"}
              className="block h-11 w-full rounded-2xl bg-muted/50 px-3 text-sm text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] sm:h-9"
            />
            <DialogFooter className="mt-4">
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setPaletteCreate(null);
                  setPaletteCreateDraft("");
                }}
                className="rounded-full"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={paletteCreateDraft.trim().length === 0}
                data-testid="palette-create-submit"
                className="rounded-full"
              >
                Create
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={pendingDeleteConversationId !== null}
        onOpenChange={(next) => {
          if (!next) setPendingDeleteConversationId(null);
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
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

      <Dialog
        open={pendingDeleteAccount}
        onOpenChange={(open) => {
          setPendingDeleteAccount(open);
          if (!open) setDeleteConfirmText("");
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Delete account?</DialogTitle>
            <DialogDescription>
              This permanently deletes your account and all your conversations.
              This can&apos;t be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Type{" "}
              <span className="font-medium text-foreground">
                {deleteConfirmExpected}
              </span>{" "}
              to confirm.
            </p>
            <input
              type="text"
              autoComplete="off"
              autoFocus
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              data-testid="delete-account-confirm-input"
              aria-label={`Type ${deleteConfirmExpected} to confirm account deletion`}
              className="block h-11 w-full rounded-2xl bg-muted/50 px-3 text-sm text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] sm:h-9"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPendingDeleteAccount(false)}
              className="rounded-full"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={!deleteConfirmMatches}
              data-testid="confirm-delete-account"
              onClick={() => {
                const value = deleteConfirmText.trim();
                setPendingDeleteAccount(false);
                setDeleteConfirmText("");
                handleDeleteAccount(value);
              }}
              className="rounded-full"
            >
              Delete account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <LiveRegion message={liveMessage} />
    </>
  );
}
