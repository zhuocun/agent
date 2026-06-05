"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import {
  ClipboardCopy,
  Code2,
  KeyRound,
  LoaderCircle,
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
import { cn } from "@/lib/utils";
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
  branchConversation,
  createConversation,
  deleteAccount,
  deleteConversation,
  fetchAccountExport,
  fetchBootstrap,
  fetchConversation,
  patchConversation,
  postFeedback,
  postAuthSignout,
  putPreferences,
  searchConversations,
  type BootstrapResponse,
} from "@/lib/apiClient";
import { REASONING_EFFORTS } from "@/lib/reasoning-efforts";
import { reportTelemetry } from "@/lib/telemetry";
import { isAnonymousAccount } from "@/lib/types";
import type {
  AccountInfo,
  AttachmentPart,
  ChatMessage,
  ConversationSummary,
  Feedback,
  MessagePart,
  ModelTier,
  ModelTierId,
  ProviderTierOption,
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
  const [authOpen, setAuthOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [isTemporary, setIsTemporary] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [conversationSearch, setConversationSearch] = useState("");
  const [conversationSearchState, setConversationSearchState] =
    useState<ConversationSearchState | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsDialogOpen, setShortcutsDialogOpen] = useState(false);
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
        // Only clear the latch if a newer attempt hasn't already replaced this
        // controller (the retry handler aborts + supersedes synchronously). (P1-5)
        if (bootstrapControllerRef.current === controller) {
          bootstrapInFlightRef.current = false;
          bootstrapControllerRef.current = null;
        }
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
    // A bare greeting ("Good afternoon") is warmer than naming a stranger, so
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
      result.sources.length === 0
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
    // Sources part follows the answer text (contract ordering). Emit it whenever
    // web search was effective — even with zero sources — so the ungrounded
    // marker ("Answered without live sources") survives the commit; grounded ⇔
    // non-empty items.
    if (result.sources.length > 0 || result.sourcesRequested) {
      parts.push({
        type: "sources",
        items: result.sources,
        requested: result.sourcesRequested,
      });
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

    if (result.status === "done") setLiveMessage("Response ready");
    else if (result.status === "stopped") setLiveMessage("Generation stopped");
    else if (result.status === "awaiting_approval")
      // HITL pause: the turn committed in place (with its tool parts) and the
      // bubble now shows the approve/deny card. Not "ready" — it's waiting on us.
      setLiveMessage("Action needs your approval");
    else setLiveMessage("Generation failed");

    setPendingId(null);
    assistantIdRef.current = null;
    pendingUserIdRef.current = null;
  }, []);

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
    }): Promise<void> => {
      abortBeforeStartRef.current = false;
      let conversationId = activeConversationId;
      if (!conversationId) {
        try {
          const created = await createConversation({
            selectedTierId: args.tierId,
            isTemporary,
            providerId: args.providerId,
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
    // Sources render AFTER the answer text (contract: sources part follows the
    // answer). They stream in once the search resolves. When web search was
    // effective but resolved nothing, the empty + requested part drives the
    // live ungrounded marker.
    if (state.sources.length > 0 || state.sourcesRequested) {
      parts.push({
        type: "sources",
        items: state.sources,
        requested: state.sourcesRequested,
      });
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
    const resumeId = localId();
    assistantIdRef.current = resumeId;
    pendingUserIdRef.current = null;
    tierAtSendRef.current = selectedTierId;
    providerAtSendRef.current = effectiveProviderId;
    searchAtSendRef.current = effectiveSearchEnabled;
    effortAtSendRef.current = effectiveReasoningEffort;
    jsonModeAtSendRef.current = jsonModeEnabled;
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

  const openSettings = () => {
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
            className="rounded-full"
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
            onSelect={handleSelectConversation}
            onNewChat={handleNewChat}
            onRenameConversation={handleRenameConversation}
            onDeleteConversation={handleDeleteConversation}
            onTogglePinConversation={handleTogglePinConversation}
            onCopyConversation={handleCopyConversationById}
            onDownloadConversation={handleDownloadConversationById}
            onOpenSettings={handleOpenSettings}
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
          {/* First-run welcome ambient halo: a soft, single-hue brand bloom
              behind the greeting. Welcome-only, decorative, vignetted by the
              z-30 chrome strips. Fades in on mount, out at the welcome→thread
              exit seam; static at rest. */}
          {showWelcome ? (
            <div
              aria-hidden
              className={cn(
                "pointer-events-none absolute inset-0 [background:var(--welcome-ambient)] transition-opacity duration-700 ease-out starting:opacity-0 motion-reduce:transition-none",
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
                onOpenSettings={handleOpenSettings}
                isTemporary={isTemporary}
                onToggleTemporary={handleToggleTemporary}
                onCopyConversation={handleCopyConversation}
                canCopyConversation={messages.length > 0}
                onDownloadConversation={handleDownloadConversation}
                canDownloadConversation={messages.length > 0}
                onShareConversation={handleOpenShare}
                canShareConversation={canShareActiveConversation}
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
              />
              {isTemporary ? (
                <TemporaryChatBanner onTurnOff={handleToggleTemporary} />
              ) : null}
            </div>
          </div>

          {/* Message area — compare mode takes over the whole surface with its
              own 2-up scroll wrapper. Otherwise: WelcomeScreen gets a single
              scroll wrapper that clears both strips, and MessageList owns its
              scroll (its internal `<ol>` has matching pt/pb that clears the
              chrome). */}
          {compareMode && compareTierA && compareTierB ? (
            <div className="relative min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+5.5rem)] pr-[env(safe-area-inset-right)] pb-[calc(var(--bottom-inset)+9rem)] pl-[env(safe-area-inset-left)] md:pt-[calc(env(safe-area-inset-top)+7rem)]">
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
              className={
                isTemporary
                  ? "relative min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+7rem)] pr-[env(safe-area-inset-right)] pb-[calc(var(--bottom-inset)+7rem)] pl-[env(safe-area-inset-left)] md:pt-[calc(env(safe-area-inset-top)+9rem)] md:pb-[calc(var(--bottom-inset)+9rem)]"
                  : "relative min-h-0 flex-1 overflow-y-auto pt-[calc(env(safe-area-inset-top)+5.5rem)] pr-[env(safe-area-inset-right)] pb-[calc(var(--bottom-inset)+7rem)] pl-[env(safe-area-inset-left)] md:pt-[calc(env(safe-area-inset-top)+7rem)] md:pb-[calc(var(--bottom-inset)+9rem)]"
              }
            >
              <WelcomeScreen
                userName={firstName}
                exiting={welcomeExiting}
                onPromptSelect={handlePromptSelect}
                suggestions={suggestions}
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
              <MessageList isTemporary={isTemporary}>
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
                      onAttributionOpen={handleAttributionOpen}
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
                sendOnEnter={preferences.sendOnEnter}
                // Attachments aren't offered in compare mode — the compare
                // toggle takes the contextual slot and a 2-up transient view
                // doesn't carry per-column attachments in MVP.
                supportsAttachments={
                  !compareMode && selectedTierSupportsAttachments
                }
                supportsVision={selectedTierSupportsVision}
                compareEnabled={compareMode}
                onToggleCompare={handleToggleCompare}
                // Pre-send estimate uses the provider-effective selected tier;
                // suppressed in compare mode (two tiers, no single estimate).
                estimateTier={compareMode ? undefined : selectedModelTier}
              />
              <AiDisclosure />
            </div>
          </div>
        </div>
      </AppShell>

      <SettingsDialog
        open={settingsOpen}
        onOpenChange={handleSettingsOpenChange}
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
