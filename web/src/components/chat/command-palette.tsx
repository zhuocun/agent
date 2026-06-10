"use client";

import { useEffect, useId, useMemo, useRef, useState, type JSX } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import {
  ChevronLeft,
  LoaderCircle,
  MessageSquare,
  Search,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { searchConversations, searchHistory } from "@/lib/apiClient";
import { useSwipeDismiss } from "@/lib/use-swipe-dismiss";
import { useVisualViewport } from "@/lib/use-visual-viewport";
import { KeyCaps } from "@/components/chat/key-caps";
import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";
import type {
  ConversationSummary,
  ModelTierId,
  Project,
  SearchFilters,
} from "@/lib/types";

// A palette action — one of the global handlers exposed to the keyboard layer
// AND surfaced as a row inside the palette. `shortcut` is the descriptor used
// to render the right-aligned key-cap hint.
export interface CommandAction {
  id: string;
  label: string;
  icon?: LucideIcon;
  shortcut?: ShortcutKeys;
  section: "Actions" | "Settings";
  // Extra search terms (synonyms / destinations) so type-to-find matches an
  // action even when the typed word isn't in its visible label — e.g. "usage"
  // or "billing" finding "Spend", "search" finding "Advanced search". Never
  // rendered; only folded into the fuzzy match below.
  keywords?: string[];
  // When true, selecting the row switches the palette INTO its in-place filter
  // mode (the folded advanced history search) instead of closing the palette and
  // invoking `run`. Used by the "Advanced search" row so the action spine and the
  // filter surface live in one summon. `run` is unused for these rows.
  entersFilterMode?: boolean;
  run: () => void;
}

// A tag the filter mode can narrow by. Kept structural (only `{ id, name }`
// matters here) so the palette doesn't depend on the org-v2 ORM type.
export interface PaletteFilterTag {
  id: string;
  name: string;
}

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: CommandAction[];
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelectConversation: (id: string) => void;
  // Filter-mode data (the folded-in advanced history search). Optional so the
  // palette degrades to action+conversation search if a host doesn't wire them.
  projects?: Project[];
  tags?: PaletteFilterTag[];
  // When the palette opens with this true, it lands directly in filter mode
  // (the folded advanced history search) instead of the action/conversation
  // listbox. Lets the host summon the palette straight into "search history"
  // from the sidebar affordance or the search-history keyboard shortcut.
  openInFilterMode?: boolean;
}

// Served-model filter options mirror the `ModelTierId` union (the BE matches the
// matched message's `attribution.servedTierId`). Friendly labels only — never a
// raw model id. Carried verbatim from the former HistorySearchDialog.
const SERVED_MODEL_OPTIONS: { value: ModelTierId; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "fast", label: "Fast" },
  { value: "smart", label: "Smart" },
  { value: "pro", label: "Pro" },
];

// Filter-control styling — copied from the former dialog so the inputs read as
// part of the same surface family.
const FILTER_INPUT_CLASS =
  "w-full min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2 text-sm leading-5 text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25";
const FILTER_SELECT_CLASS =
  "h-9 w-full truncate rounded-xl border border-border/70 bg-background/70 px-3 text-sm text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/25";

// Date input <-> ISO. The native date input gives `YYYY-MM-DD`; the BE parses
// ISO-8601. `dateTo` widens to end-of-day so an inclusive "to" matches any time
// on that calendar day.
function toIsoStart(date: string): string | undefined {
  return date ? new Date(`${date}T00:00:00`).toISOString() : undefined;
}
function toIsoEnd(date: string): string | undefined {
  return date ? new Date(`${date}T23:59:59.999`).toISOString() : undefined;
}
function parseCost(value: string): number | undefined {
  if (value.trim() === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

// Flat list item — either an action or a conversation. The list is rendered
// as a single ARIA listbox; the section labels are visual headings (not
// listbox children) and are skipped when computing keyboard indices.
type Item =
  | { kind: "action"; section: "Actions" | "Settings"; action: CommandAction; flatIndex: number }
  | { kind: "conversation"; conversation: ConversationSummary; isActive: boolean; flatIndex: number };
type RemoteConversationState = {
  query: string;
  results: ConversationSummary[];
};

// Cap for the "Recent" section when there's no query. Searching a non-empty
// query spans all conversations per PRD §4.9.
const RECENT_CAP = 5;

function buildItems(
  query: string,
  actions: CommandAction[],
  conversations: ConversationSummary[],
  activeId: string | null,
  remoteConversations: ConversationSummary[] | null,
): { sections: { heading: string; items: Item[] }[]; flat: Item[] } {
  const q = query.trim().toLowerCase();
  const match = (s: string): boolean => (q ? s.toLowerCase().includes(q) : true);

  const actionItems = actions.filter(
    (a) => match(a.label) || (a.keywords ?? []).some((k) => match(k)),
  );

  const useRemoteConversations = q.length > 0 && remoteConversations !== null;
  // Newest first. Sort a copy so the parent's array stays untouched. Remote
  // search results are already filtered by the backend and may match snippets
  // rather than titles, so preserve them as-is.
  const sortedConversations = useRemoteConversations
    ? remoteConversations
    : [...conversations].sort((a, b) =>
        a.updatedAt < b.updatedAt ? 1 : a.updatedAt > b.updatedAt ? -1 : 0,
      );
  const filteredConversations = useRemoteConversations
    ? sortedConversations
    : sortedConversations.filter(
        (c) => match(c.title) || match(c.matchSnippet ?? ""),
      );
  const visibleConversations = q
    ? filteredConversations
    : filteredConversations.slice(0, RECENT_CAP);

  // Assign a stable flatIndex while building so render-time iteration never
  // has to mutate a running counter (concurrent React can restart a render).
  let cursor = 0;
  const actionsSection = actionItems
    .filter((a) => a.section === "Actions")
    .map<Item>((action) => ({
      kind: "action",
      section: "Actions",
      action,
      flatIndex: cursor++,
    }));
  const settingsSection = actionItems
    .filter((a) => a.section === "Settings")
    .map<Item>((action) => ({
      kind: "action",
      section: "Settings",
      action,
      flatIndex: cursor++,
    }));
  const recentSection = visibleConversations.map<Item>((c) => ({
    kind: "conversation",
    conversation: c,
    isActive: c.id === activeId,
    flatIndex: cursor++,
  }));

  const sections: { heading: string; items: Item[] }[] = [];
  if (actionsSection.length > 0) sections.push({ heading: "Actions", items: actionsSection });
  if (settingsSection.length > 0) sections.push({ heading: "Settings", items: settingsSection });
  if (recentSection.length > 0) sections.push({ heading: "Recent", items: recentSection });

  const flat = sections.flatMap((s) => s.items);
  return { sections, flat };
}

export function CommandPalette({
  open,
  onOpenChange,
  actions,
  conversations,
  activeId,
  onSelectConversation,
  projects = [],
  tags = [],
  openInFilterMode = false,
}: CommandPaletteProps): JSX.Element {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isMobile, setIsMobile] = useState(false);
  const [remoteConversationState, setRemoteConversationState] =
    useState<RemoteConversationState | null>(null);
  const [searchPending, setSearchPending] = useState(false);
  // Progressively-disclosed filter mode (the folded-in advanced history search).
  // Default false: the palette is the action/conversation listbox. When true the
  // body swaps to the transparency-native filter form + a results list of real
  // focusable buttons — a clean MODE SWITCH so the listbox `aria-activedescendant`
  // model and the form's native-focus model never coexist (only one is live at a
  // time, so neither a11y model regresses).
  const [filterMode, setFilterMode] = useState(false);
  const [servedModel, setServedModel] = useState<ModelTierId | "">("");
  const [costMin, setCostMin] = useState("");
  const [costMax, setCostMax] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [projectId, setProjectId] = useState("");
  const [tagId, setTagId] = useState("");
  const [filterResults, setFilterResults] = useState<ConversationSummary[]>([]);
  const [filterPending, setFilterPending] = useState(false);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [filterSearched, setFilterSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();
  const optionIdPrefix = useId();

  // Below sm: the palette presents as an iOS bottom sheet (swipe-to-dismiss);
  // at sm+ it stays the centered top-anchored modal. SSR-safe: starts false.
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(max-width: 639.98px)");
    const sync = () => setIsMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    const q = query.trim();
    // In filter mode a separate effect (below) drives the search via
    // `searchHistory` with the filter payload, so the plain conversation search
    // stands down to avoid a double-fetch.
    if (!open || filterMode || q.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSearchPending(false);
      return;
    }

    setSearchPending(true);
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void searchConversations(q, controller.signal)
        .then((results) => {
          if (!controller.signal.aborted) {
            setRemoteConversationState({ query: q, results });
            setSearchPending(false);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) setSearchPending(false);
        });
    }, 150);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, query, filterMode]);

  // Filter-mode search: the folded-in advanced history search. Debounced, runs
  // whenever the (open) palette is in filter mode with a non-empty query or its
  // filters change. Empty query clears results without hitting the BE (the `q`
  // param is required server-side). Mirrors the former HistorySearchDialog.
  const filters: SearchFilters = useMemo(
    () => ({
      servedModel: servedModel || undefined,
      costMin: parseCost(costMin),
      costMax: parseCost(costMax),
      dateFrom: toIsoStart(dateFrom),
      dateTo: toIsoEnd(dateTo),
      projectId: projectId || undefined,
      tagId: tagId || undefined,
    }),
    [servedModel, costMin, costMax, dateFrom, dateTo, projectId, tagId],
  );

  useEffect(() => {
    if (!open || !filterMode) return;
    const q = query.trim();
    if (q.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFilterResults([]);
      setFilterPending(false);
      setFilterSearched(false);
      return;
    }
    setFilterPending(true);
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void searchHistory(q, filters, controller.signal)
        .then((rows) => {
          if (controller.signal.aborted) return;
          setFilterResults(rows);
          setFilterError(null);
          setFilterPending(false);
          setFilterSearched(true);
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setFilterError("Couldn't run that search. Please try again.");
          setFilterPending(false);
          setFilterSearched(true);
        });
    }, 200);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, filterMode, query, filters]);

  const { sheetRef, handleProps, contentProps } = useSwipeDismiss({
    enabled: isMobile,
    onDismiss: () => handleOpenChangeRef.current(false),
  });

  // Taps on interactive controls inside the sheet (the header's filter/back
  // buttons, the filter form fields) must stay plain clicks. The swipe hook
  // pointer-captures the sheet on pointerdown, which retargets the eventual
  // `click` to the sheet and silently swallows the control's handler on
  // touch. Skipping the gesture for controls trades "swipe starting on a
  // button" for working taps — matching iOS, where a touch that lands on a
  // control acts on the control.
  const sheetContentProps: typeof contentProps = {
    ...contentProps,
    onPointerDown: (event) => {
      const target = event.target as HTMLElement;
      if (target.closest("button, input, select, textarea, a")) return;
      contentProps.onPointerDown(event);
    },
  };

  // The mobile sheet is bottom-pinned, so the iOS software keyboard (which does
  // NOT shrink dvh) slides up *over* the lower results. Lift the whole sheet by
  // the measured keyboard inset and trim that much off its max-height, so the
  // results list always ends above the keyboard rather than behind it. Desktop
  // (sm+) is unaffected: the sheet is top-anchored there and we only feed the
  // inset into the mobile-only inline style below.
  const { keyboardInset } = useVisualViewport();
  const mobileKeyboardStyle =
    isMobile && keyboardInset > 0
      ? {
          // bottom inset clears the keyboard; max-height subtracts it so the
          // 80dvh cap still leaves the input + results fully visible above it.
          bottom: keyboardInset,
          maxHeight: `calc(80dvh - ${keyboardInset}px)`,
        }
      : undefined;

  const activeRemoteConversations =
    open &&
    remoteConversationState !== null &&
    remoteConversationState.query === query.trim()
      ? remoteConversationState.results
      : null;

  const { sections, flat } = useMemo(
    () =>
      buildItems(
        query,
        actions,
        conversations,
        activeId,
        activeRemoteConversations,
      ),
    [query, actions, conversations, activeId, activeRemoteConversations],
  );

  const clampedIndex =
    flat.length === 0 ? 0 : Math.min(selectedIndex, flat.length - 1);

  const activeOptionId =
    flat.length > 0 ? `${optionIdPrefix}-${clampedIndex}` : undefined;

  // Reset the filter sub-state (controls + results). Shared by "exit filter
  // mode" and "palette close" so a re-entry always starts clean.
  const resetFilters = (): void => {
    setServedModel("");
    setCostMin("");
    setCostMax("");
    setDateFrom("");
    setDateTo("");
    setProjectId("");
    setTagId("");
    setFilterResults([]);
    setFilterPending(false);
    setFilterError(null);
    setFilterSearched(false);
  };

  // Closing the palette clears search + selection + filter mode — done here
  // (event-driven) rather than in an effect to avoid the cascading-render lint.
  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setQuery("");
      setSelectedIndex(0);
      setFilterMode(false);
      resetFilters();
    }
    onOpenChange(next);
  };

  // Enter filter mode: keep the typed query (so a started search carries over),
  // re-focus the input. Exit: drop the filters and return to the listbox.
  const enterFilterMode = (): void => {
    setFilterMode(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  };
  const exitFilterMode = (): void => {
    setFilterMode(false);
    resetFilters();
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  // When the host summons the palette with `openInFilterMode`, land directly in
  // filter mode on each fresh open (the consolidated "advanced history search"
  // entry point). Tracked on an open→close edge so re-renders while open don't
  // re-trigger and so a later normal open (openInFilterMode flipped off) starts
  // in the default listbox.
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (open && !wasOpenRef.current && openInFilterMode) {
      setQuery("");
      enterFilterMode();
    }
    wasOpenRef.current = open;
  }, [open, openInFilterMode]);

  const handleSelectFilterResult = (id: string): void => {
    handleOpenChange(false);
    requestAnimationFrame(() => onSelectConversation(id));
  };

  // Keep a stable ref so the swipe hook's onDismiss always calls the latest
  // handleOpenChange without re-subscribing the gesture listeners.
  const handleOpenChangeRef = useRef(handleOpenChange);
  useEffect(() => {
    handleOpenChangeRef.current = handleOpenChange;
  });

  const runItem = (item: Item): void => {
    if (item.kind === "action") {
      // "Advanced search" stays IN the palette: swap to filter mode rather than
      // closing + dispatching, so the listbox→filter-form transition is the
      // single in-place disclosure (one surface in motion).
      if (item.action.entersFilterMode) {
        setQuery("");
        enterFilterMode();
        return;
      }
      handleOpenChange(false);
      // Defer execution until after Base UI's close-on-select finishes so a
      // newly-opened dialog (e.g. settings) doesn't race the palette's exit
      // animation and steal focus mid-close.
      requestAnimationFrame(() => item.action.run());
    } else {
      handleOpenChange(false);
      requestAnimationFrame(() => onSelectConversation(item.conversation.id));
    }
  };

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    // In filter mode the body is a native form (selects/date inputs/focusable
    // result buttons), not a listbox, so the combobox arrow/Enter handling stands
    // down — Tab + native focus drive it instead.
    if (filterMode) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (flat.length === 0) return;
      setSelectedIndex((clampedIndex + 1) % flat.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (flat.length === 0) return;
      setSelectedIndex((clampedIndex - 1 + flat.length) % flat.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = flat[clampedIndex];
      if (item) runItem(item);
    }
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={handleOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          data-slot="dialog-backdrop"
          className="fixed inset-0 z-50 bg-foreground/45 backdrop-blur-sm transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0"
        />
        <DialogPrimitive.Popup
          ref={sheetRef}
          // In filter mode the popup IS the advanced-search surface, so carry the
          // former dialog's testid here (the e2e specs scope filter assertions to
          // `search-dialog`). Default mode leaves it off so palette assertions are
          // unaffected.
          data-testid={filterMode ? "search-dialog" : undefined}
          data-slot="dialog-content"
          // Override glass-regular's blur with the denser dialog blur (same
          // trick as DialogContent so the popup reads as the canonical "modal"
          // glass surface).
          style={{
            backdropFilter:
              "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
            WebkitBackdropFilter:
              "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
            // Keyboard-safe lift on mobile (no-op on desktop / no keyboard).
            ...mobileKeyboardStyle,
          }}
          {...sheetContentProps}
          className={cn(
            // Mobile (default): iOS bottom sheet — full-width, bottom-pinned,
            // rounded top, slides up with iOS sheet easing, swipe-to-dismiss.
            "glass-strong fixed inset-x-0 bottom-0 z-50 flex max-h-[80dvh] w-full flex-col gap-0 overflow-hidden rounded-t-3xl rounded-b-none p-0 text-foreground",
            "transition-[transform,opacity] duration-[400ms] ease-[var(--ease-ios-sheet)] max-sm:data-[ending-style]:translate-y-full max-sm:data-[starting-style]:translate-y-full",
            // Desktop (sm+): centered top-anchored modal with scale+fade. The
            // -translate-x keeps composing with scale during the anim.
            "sm:inset-x-auto sm:bottom-auto sm:top-[20dvh] sm:left-1/2 sm:max-h-[60dvh] sm:max-w-xl sm:-translate-x-1/2 sm:rounded-3xl sm:transition-[transform,opacity] sm:duration-200 sm:data-[ending-style]:scale-95 sm:data-[ending-style]:opacity-0 sm:data-[starting-style]:scale-95 sm:data-[starting-style]:opacity-0"
          )}
        >
          {/* Grabber: drag affordance + swipe-to-dismiss handle, mobile only. */}
          <div
            aria-hidden
            {...handleProps}
            className="mx-auto mt-2.5 h-1.5 w-9 shrink-0 cursor-grab touch-none rounded-full bg-foreground/25 sm:hidden"
          />
          <DialogPrimitive.Title className="sr-only">
            {filterMode ? "Search history" : "Command palette"}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            {filterMode
              ? "Search your conversations and filter by model, cost, date, or project. Escape to close."
              : "Search actions and conversations. Use arrow keys to navigate, Enter to select, Escape to close."}
          </DialogPrimitive.Description>

          <div className="relative flex shrink-0 items-center border-b border-foreground/10 px-5">
            {filterMode ? (
              <button
                type="button"
                onClick={exitFilterMode}
                aria-label="Back to commands"
                className="-ml-1.5 mr-1 flex size-11 shrink-0 items-center justify-center rounded-full text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)] md:size-7"
              >
                <ChevronLeft aria-hidden className="size-4" />
              </button>
            ) : (
              <Search
                aria-hidden
                className="pointer-events-none size-4 shrink-0 text-muted-foreground"
              />
            )}
            <input
              ref={inputRef}
              type="text"
              // Combobox/listbox ARIA only applies to the default (listbox) mode.
              // In filter mode the input is a plain search field over a native
              // form, so the combobox wiring is dropped to keep the two focus
              // models from overlapping.
              role={filterMode ? undefined : "combobox"}
              aria-haspopup={filterMode ? undefined : "listbox"}
              aria-expanded={filterMode ? undefined : open}
              aria-controls={filterMode ? undefined : listboxId}
              aria-activedescendant={filterMode ? undefined : activeOptionId}
              aria-autocomplete={filterMode ? undefined : "list"}
              aria-label={filterMode ? "Search query" : undefined}
              data-testid={filterMode ? "search-query-input" : undefined}
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              onKeyDown={onInputKeyDown}
              placeholder={
                filterMode
                  ? "Search conversations…"
                  : "Search actions & chats…"
              }
              className="block w-full bg-transparent py-4 pl-3 pr-2 text-lg text-foreground outline-none placeholder:text-muted-foreground"
            />
            {(filterMode ? filterPending : searchPending) ? (
              <LoaderCircle
                aria-hidden
                className="ml-2 size-4 shrink-0 text-muted-foreground motion-safe:animate-spin"
              />
            ) : null}
            {!filterMode ? (
              <button
                type="button"
                onClick={enterFilterMode}
                aria-label="Advanced search filters"
                data-testid="palette-filter-toggle"
                className="ml-2 flex size-11 shrink-0 items-center justify-center rounded-full text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)] md:size-7"
              >
                <SlidersHorizontal aria-hidden className="size-4" />
              </button>
            ) : null}
          </div>

          <div
            className="min-h-0 flex-1 space-y-0.5 overflow-y-auto py-2"
            aria-busy={(filterMode ? filterPending : searchPending) || undefined}
          >
            {filterMode ? (
              <div className="space-y-4 px-5 py-2">
                {/* Filters — native form controls (real focus, Tab order). */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label className="space-y-1 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">
                      Model
                    </span>
                    <select
                      value={servedModel}
                      onChange={(e) =>
                        setServedModel(e.currentTarget.value as ModelTierId | "")
                      }
                      className={FILTER_SELECT_CLASS}
                      data-testid="search-filter-model"
                    >
                      <option value="">Any model</option>
                      {SERVED_MODEL_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="space-y-1 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">
                      Project
                    </span>
                    <select
                      value={projectId}
                      onChange={(e) => setProjectId(e.currentTarget.value)}
                      className={FILTER_SELECT_CLASS}
                      data-testid="search-filter-project"
                    >
                      <option value="">Any project</option>
                      {projects.map((project) => (
                        <option key={project.id} value={project.id}>
                          {project.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div className="space-y-1 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">
                      Cost (USD)
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        inputMode="decimal"
                        value={costMin}
                        onChange={(e) => setCostMin(e.currentTarget.value)}
                        placeholder="Min"
                        aria-label="Minimum cost"
                        className={FILTER_INPUT_CLASS}
                        data-testid="search-filter-cost-min"
                      />
                      <span aria-hidden className="text-muted-foreground">
                        –
                      </span>
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        inputMode="decimal"
                        value={costMax}
                        onChange={(e) => setCostMax(e.currentTarget.value)}
                        placeholder="Max"
                        aria-label="Maximum cost"
                        className={FILTER_INPUT_CLASS}
                        data-testid="search-filter-cost-max"
                      />
                    </div>
                  </div>

                  <div className="space-y-1 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">
                      Date
                    </span>
                    <div className="flex items-center gap-2">
                      <input
                        type="date"
                        value={dateFrom}
                        onChange={(e) => setDateFrom(e.currentTarget.value)}
                        aria-label="From date"
                        className={FILTER_INPUT_CLASS}
                        data-testid="search-filter-date-from"
                      />
                      <span aria-hidden className="text-muted-foreground">
                        –
                      </span>
                      <input
                        type="date"
                        value={dateTo}
                        onChange={(e) => setDateTo(e.currentTarget.value)}
                        aria-label="To date"
                        className={FILTER_INPUT_CLASS}
                        data-testid="search-filter-date-to"
                      />
                    </div>
                  </div>

                  {tags.length > 0 ? (
                    <label className="space-y-1 text-sm">
                      <span className="text-xs font-medium text-muted-foreground">
                        Tag
                      </span>
                      <select
                        value={tagId}
                        onChange={(e) => setTagId(e.currentTarget.value)}
                        className={FILTER_SELECT_CLASS}
                        data-testid="search-filter-tag"
                      >
                        <option value="">Any tag</option>
                        {tags.map((tag) => (
                          <option key={tag.id} value={tag.id}>
                            {tag.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : null}
                </div>

                {filterError ? (
                  <p role="alert" className="text-sm text-destructive">
                    {filterError}
                  </p>
                ) : null}

                {/* Results */}
                <section aria-busy={filterPending || undefined}>
                  {filterPending ? (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                      <LoaderCircle
                        aria-hidden
                        className="size-4 motion-safe:animate-spin"
                      />
                      Searching…
                    </p>
                  ) : filterSearched &&
                    filterError === null &&
                    filterResults.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No matches — try a different term or loosen the filters.
                    </p>
                  ) : filterResults.length > 0 ? (
                    <ul className="space-y-2" data-testid="search-results">
                      {filterResults.map((result) => {
                        const snippet = result.matchSnippet?.trim();
                        return (
                          <li key={result.id}>
                            <button
                              type="button"
                              onClick={() => handleSelectFilterResult(result.id)}
                              className="glass-clear flex w-full items-start gap-3 rounded-2xl px-3.5 py-3 text-left outline-none transition-colors hover:bg-foreground/[0.04] focus-visible:shadow-[var(--focus-ring)]"
                              data-testid="search-result"
                              data-conversation-id={result.id}
                            >
                              <MessageSquare
                                aria-hidden
                                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                              />
                              <span className="min-w-0 flex-1 space-y-1">
                                <span className="block truncate text-sm font-medium">
                                  {result.title}
                                </span>
                                {snippet ? (
                                  <span className="block truncate text-xs text-muted-foreground">
                                    {snippet}
                                  </span>
                                ) : null}
                                {result.servedModelLabel ||
                                result.costUsd != null ||
                                result.matchedAt ? (
                                  <span className="flex flex-wrap items-center gap-1.5 pt-0.5">
                                    {result.servedModelLabel ? (
                                      <Badge variant="secondary">
                                        {result.servedModelLabel}
                                      </Badge>
                                    ) : null}
                                    {result.costUsd != null ? (
                                      <Badge variant="outline">
                                        ${result.costUsd.toFixed(4)}
                                      </Badge>
                                    ) : null}
                                    {result.matchedAt ? (
                                      <span className="text-2xs text-muted-foreground">
                                        {new Date(
                                          result.matchedAt,
                                        ).toLocaleDateString()}
                                      </span>
                                    ) : null}
                                  </span>
                                ) : null}
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Type to search your conversation history.
                    </p>
                  )}
                </section>
              </div>
            ) : flat.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">
                {searchPending
                  ? "Searching…"
                  : "No results — try a different term"}
              </div>
            ) : (
              <ul role="listbox" id={listboxId} aria-label="Commands">
                {sections.map((section) => (
                  <li key={section.heading} className="py-1">
                    <div
                      role="presentation"
                      className="px-5 pb-1 pt-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase"
                    >
                      {section.heading}
                    </div>
                    <ul role="presentation">
                      {section.items.map((item) => {
                        const isSelected = item.flatIndex === clampedIndex;
                        const id = `${optionIdPrefix}-${item.flatIndex}`;
                        if (item.kind === "action") {
                          const Icon = item.action.icon;
                          return (
                            <li
                              key={item.action.id}
                              id={id}
                              role="option"
                              aria-selected={isSelected}
                              onMouseEnter={() => setSelectedIndex(item.flatIndex)}
                              onMouseDown={(e) => {
                                // mousedown to beat the input's blur, which
                                // would otherwise unmount the row before the
                                // click resolved.
                                e.preventDefault();
                                runItem(item);
                              }}
                              className={cn(
                                // min-h-11: 44pt touch floor on the mobile
                                // sheet (harmless on desktop). Selection uses a
                                // quiet translucent tint to match the model/tier
                                // pickers' selected-row treatment — the solid
                                // `bg-accent` fill read too loud against glass.
                                "mx-2 flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 py-3 text-sm text-foreground",
                                isSelected && "bg-foreground/[0.06]",
                              )}
                            >
                              {Icon ? (
                                <Icon
                                  aria-hidden
                                  className="size-4 shrink-0 text-muted-foreground"
                                />
                              ) : (
                                <span aria-hidden className="size-4 shrink-0" />
                              )}
                              <span className="min-w-0 flex-1 truncate">
                                {item.action.label}
                              </span>
                              {item.action.shortcut ? (
                                <KeyCaps
                                  shortcut={item.action.shortcut}
                                  variant="compact"
                                  className="ml-3"
                                />
                              ) : null}
                            </li>
                          );
                        }
                        const matchSnippet = item.conversation.matchSnippet?.trim();
                        return (
                          <li
                            key={item.conversation.id}
                            id={id}
                            role="option"
                            aria-selected={isSelected}
                            onMouseEnter={() => setSelectedIndex(item.flatIndex)}
                            onMouseDown={(e) => {
                              e.preventDefault();
                              runItem(item);
                            }}
                            className={cn(
                              // min-h-11: 44pt touch floor; quiet selection
                              // tint consistent with the action rows above.
                              "mx-2 flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground",
                              isSelected && "bg-foreground/[0.06]",
                            )}
                          >
                            <MessageSquare
                              aria-hidden
                              className="size-4 shrink-0 text-muted-foreground"
                            />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate">
                                {item.conversation.title}
                              </span>
                              {matchSnippet ? (
                                <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                                  {matchSnippet}
                                </span>
                              ) : null}
                            </span>
                            {item.isActive ? (
                              <span className="ml-3 shrink-0 text-xs text-muted-foreground">
                                Open
                              </span>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="hidden shrink-0 border-t border-foreground/10 px-5 py-2 text-2xs text-muted-foreground sm:block">
            {filterMode ? (
              <>
                <span className="font-mono">Tab</span> to move between filters ·{" "}
                <span className="font-mono">Esc</span> to close
              </>
            ) : (
              <>
                <span className="font-mono">↑↓</span> to navigate ·{" "}
                <span className="font-mono">↵</span> to select ·{" "}
                <span className="font-mono">Esc</span> to close
              </>
            )}
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
