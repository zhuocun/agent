"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import {
  ClipboardCopy,
  Key,
  LogIn,
  LogOut,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Settings,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useSwipeActions } from "@/lib/use-swipe-actions";
import {
  isAnonymousAccount,
  type AccountInfo,
  type ConversationSummary,
} from "@/lib/types";

// Width of the swipe-revealed trailing action tray (two 64px action buttons).
const SWIPE_ACTIONS_WIDTH = 128;

export interface SidebarProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  account: AccountInfo;
  search: string;
  onSearchChange: (next: string) => void;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onRenameConversation: (id: string, newTitle: string) => void;
  onDeleteConversation: (id: string) => void;
  onTogglePinConversation: (id: string) => void;
  onCopyConversation: (id: string) => void;
  onOpenSettings: () => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onCollapse?: () => void; // desktop: hide the sidebar rail; omit the button if undefined
  className?: string;
}

// Recency buckets shown in the history list, in display order. "Pinned" is
// orthogonal to date (any pinned item lands here regardless of age).
const RECENCY_LABELS = {
  pinned: "Pinned",
  today: "Today",
  yesterday: "Yesterday",
  week: "Previous 7 days",
  month: "Previous 30 days",
  older: "Older",
} as const;

type RecencyKey = keyof typeof RECENCY_LABELS;

// Display order for the rendered sections (skip empty ones at render time).
const GROUP_ORDER: RecencyKey[] = [
  "pinned",
  "today",
  "yesterday",
  "week",
  "month",
  "older",
];

// Calendar-day index (days since the Unix epoch in local time) so that the
// difference between two timestamps reflects whole calendar days, not 24h spans.
function dayNumber(ms: number): number {
  const d = new Date(ms);
  return Math.floor(
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 86_400_000
  );
}

// Bucket conversations by calendar-day distance from a reference "now". The
// reference is the MAX updatedAt across the list so the demo groups sensibly
// regardless of the wall clock. Pinned items are pulled out first.
function groupConversations(
  conversations: ConversationSummary[]
): Map<RecencyKey, ConversationSummary[]> {
  const groups = new Map<RecencyKey, ConversationSummary[]>();
  if (conversations.length === 0) {
    return groups;
  }

  const referenceMs = Math.max(
    ...conversations.map((c) => Date.parse(c.updatedAt))
  );
  const referenceDay = dayNumber(referenceMs);

  const push = (key: RecencyKey, item: ConversationSummary) => {
    const existing = groups.get(key);
    if (existing) {
      existing.push(item);
    } else {
      groups.set(key, [item]);
    }
  };

  for (const conversation of conversations) {
    if (conversation.pinned) {
      push("pinned", conversation);
      continue;
    }

    const diff = referenceDay - dayNumber(Date.parse(conversation.updatedAt));
    if (diff <= 0) {
      push("today", conversation);
    } else if (diff === 1) {
      push("yesterday", conversation);
    } else if (diff <= 7) {
      push("week", conversation);
    } else if (diff <= 30) {
      push("month", conversation);
    } else {
      push("older", conversation);
    }
  }

  return groups;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "?";
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function ConversationRow({
  conversation,
  active,
  activeRowRef,
  onSelect,
  onRename,
  onTogglePin,
  onCopy,
  onRequestDelete,
}: {
  conversation: ConversationSummary;
  active: boolean;
  activeRowRef?: React.RefObject<HTMLDivElement | null>;
  onSelect: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onTogglePin: (id: string) => void;
  onCopy: (id: string) => void;
  onRequestDelete: (conversation: ConversationSummary) => void;
}): React.JSX.Element {
  const [isRenaming, setIsRenaming] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement>(null);
  // Blur fires on Escape (cancel), on Enter (submit-then-unmount synthetic
  // blur), and on click-away (submit). Track which exit path is in flight so
  // the blur handler doesn't double-fire after Enter and doesn't fight Escape.
  const cancelingRef = useRef(false);

  useEffect(() => {
    if (!isRenaming) return;
    // base-ui's <FloatingFocusManager returnFocus> restores focus to the
    // kebab trigger when the menu popup unmounts. Because the popup has an
    // exit animation, that restoration runs *after* React effects — so a
    // synchronous focus() here gets stolen back. Defer to a macrotask so the
    // input receives focus after base-ui has finished its focus dance.
    const id = window.setTimeout(() => {
      const input = inputRef.current;
      if (!input) return;
      input.focus();
      input.select();
    }, 0);
    return () => window.clearTimeout(id);
  }, [isRenaming]);

  const enterRename = () => {
    setDraft(conversation.title);
    cancelingRef.current = false;
    setIsRenaming(true);
  };

  const submitRename = () => {
    // Guard both Enter and click-away paths against re-entry: after Enter,
    // setIsRenaming(false) unmounts the input and the browser may dispatch a
    // synthetic blur that would otherwise re-enter submitRename via onBlur.
    if (cancelingRef.current) return;
    cancelingRef.current = true;
    setIsRenaming(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== conversation.title) {
      onRename(conversation.id, trimmed);
    }
  };

  const cancelRename = () => {
    cancelingRef.current = true;
    setIsRenaming(false);
    setDraft(conversation.title);
  };

  const onInputKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitRename();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancelRename();
    }
  };

  const onInputBlur = () => {
    if (cancelingRef.current) {
      cancelingRef.current = false;
      return;
    }
    submitRename();
  };

  const swipe = useSwipeActions({
    actionsWidth: SWIPE_ACTIONS_WIDTH,
    // Full swipe-left deletes directly (native-iOS style). The threshold is
    // proportional to the row's measured width (the hook's default ≈60%, floored
    // at 160px) rather than a fixed 200px — a fixed px fired too early on the
    // wide desktop rail and felt inconsistent across the phone sheet vs. rail.
    onFullSwipe: () => onRequestDelete(conversation),
    // Renaming takes over the row; don't let a drag fight the text caret.
    disabled: isRenaming,
  });

  const handleRowClick = () => {
    // A swipe that left the row open shouldn't also select on the tap-release;
    // first tap closes the tray (matches iOS), and the open tray swallows it.
    if (swipe.open) {
      swipe.close();
      return;
    }
    onSelect(conversation.id);
  };

  const stopBubble = (e: ReactMouseEvent) => {
    e.stopPropagation();
  };

  const pinAction = conversation.pinned ? "Unpin" : "Pin";

  // Reduced motion → snap instantly; otherwise ease the reveal/settle. While
  // actively dragging we never transition (the finger is the clock).
  const slideTransition =
    swipe.dragging || swipe.reducedMotion
      ? undefined
      : "transform 200ms cubic-bezier(0.22, 1, 0.36, 1)";

  return (
    <div
      ref={active ? activeRowRef : undefined}
      // E2E target: rows are keyed by id so a test can locate a row by the
      // conversation id it just minted via the API (titles can be autogenerated
      // strings and would race against the test).
      data-conversation-id={conversation.id}
      className={cn(
        "group/conv relative isolate flex min-h-11 w-full items-center overflow-hidden rounded-2xl text-left text-sm transition-colors",
        // Single-accent doctrine: the active row is signalled by a 2px brand
        // stripe at the leading edge; rest state stays on pure typography + Ma
        // (no background fill). Hover tint is intentionally barely-perceptible.
        active
          ? "text-foreground before:absolute before:inset-y-1 before:left-0 before:z-20 before:w-0.5 before:rounded-full before:bg-brand"
          : "text-sidebar-foreground",
      )}
    >
      {/* Swipe-revealed trailing action tray. Sits behind the sliding row
          content; becomes interactive only once the row is dragged/settled
          open. Pin/Unpin + destructive Delete, mirroring the kebab menu. */}
      <div
        aria-hidden={!swipe.open}
        className={cn(
          "absolute inset-y-0 right-0 z-0 flex items-stretch",
          swipe.open ? "" : "pointer-events-none",
        )}
        style={{
          width: SWIPE_ACTIONS_WIDTH,
          // Don't paint the tray while the row is fully closed. On iOS Safari a
          // parent with `overflow:hidden` + `border-radius` fails to clip a
          // GPU-composited sibling (the sliding layer uses `translate3d`), so a
          // ~1px sliver of this red Delete action leaks past the rounded corners
          // as stray arcs at rest. Chromium clips correctly, so it never shows
          // locally / in e2e. Removing the tray from paint when closed sidesteps
          // the leak entirely; it reappears the instant a swipe moves the row
          // (offset != 0) or it settles open.
          visibility:
            swipe.open || swipe.offset !== 0 ? "visible" : "hidden",
        }}
      >
        <button
          type="button"
          tabIndex={swipe.open ? 0 : -1}
          aria-label={pinAction}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin(conversation.id);
            swipe.close();
          }}
          className="flex w-16 select-none flex-col items-center justify-center gap-1 bg-muted text-xs font-medium text-foreground transition-transform duration-100 touch-manipulation active:scale-[0.97]"
        >
          {conversation.pinned ? (
            <PinOff className="size-4" aria-hidden />
          ) : (
            <Pin className="size-4" aria-hidden />
          )}
          <span>{pinAction}</span>
        </button>
        <button
          type="button"
          tabIndex={swipe.open ? 0 : -1}
          aria-label="Delete"
          onClick={(e) => {
            e.stopPropagation();
            onRequestDelete(conversation);
            swipe.close();
          }}
          className="flex w-16 select-none flex-col items-center justify-center gap-1 bg-destructive text-xs font-medium text-white transition-transform duration-100 touch-manipulation active:scale-[0.97]"
        >
          <Trash2 className="size-4" aria-hidden />
          <span>Delete</span>
        </button>
      </div>

      {/* Sliding foreground layer: holds the row's tap target + kebab. The
          background carries the row's own surface color so the tray stays
          hidden until revealed. */}
      <div
        {...swipe.handlers}
        style={{
          transform: `translate3d(${swipe.offset}px, 0, 0)`,
          transition: slideTransition,
          touchAction: "pan-y",
        }}
        className={cn(
          // Opaque surface masks the trailing tray until it's revealed. The
          // hover tint rides on top via ::after so it can't expose the tray
          // (a translucent base would let the tray bleed through on hover).
          // No own border-radius: the parent row is `overflow-hidden
          // rounded-2xl`, so this opaque square layer fully masks the trailing
          // tray at rest (rounded corners of its own would expose the red
          // Delete action through the gaps), and the parent clip rounds both
          // this layer and the tray as it slides open.
          "relative z-10 flex min-h-11 w-full items-center bg-sidebar pr-1",
          !active &&
            "after:pointer-events-none after:absolute after:inset-0 after:bg-foreground/[0.03] after:opacity-0 after:transition-opacity hover:after:opacity-100",
        )}
      >
      {isRenaming ? (
        // Inline-rename mode renders as a sibling subtree, NOT nested in the
        // click-to-select button. <button> cannot contain interactive
        // descendants (invalid HTML; some browsers prevent the input from
        // receiving keyboard focus and click-through can occur). Mirrors the
        // edit pattern in user-message.tsx.
        <div className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-2xl px-3 py-2">
          {conversation.pinned ? (
            <Pin className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
          ) : null}
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onInputKeyDown}
            onBlur={onInputBlur}
            onClick={stopBubble}
            aria-label="Rename conversation"
            // E2E target: lets the conversation spec fill the rename input
            // without racing with the search box, which also has type="search".
            data-testid="sidebar-conversation-rename-input"
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] rounded-sm"
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={handleRowClick}
          aria-label={`${conversation.title}${conversation.pinned ? ", pinned" : ""}`}
          aria-current={active ? "page" : undefined}
          // E2E target: the row's row-click area lives next to a kebab
          // ("Conversation actions") button; this testid lets specs open the
          // conversation without relying on DOM order to disambiguate.
          data-testid="sidebar-conversation-link"
          // Press feedback matches the button slice's spring feel: a fast
          // scale-down on press, then a gentle spring-back on release. Lives on
          // the inner tap target (a child of the swipe sliding layer) so its
          // scale composes with — never fights — the layer's translate3d swipe.
          // Reduced motion drops the scale entirely (motion-reduce:scale-100).
          className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-2xl px-3 py-2 text-left outline-none transition-transform duration-[280ms] ease-ios-spring focus-visible:shadow-[var(--focus-ring)] active:scale-[0.97] active:duration-[70ms] active:ease-out motion-reduce:scale-100 motion-reduce:transition-none"
        >
          {conversation.pinned ? (
            <Pin className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
          ) : null}
          <span
            // E2E target: reads the rendered title text without depending on
            // the aria-label format (which appends ", pinned" for pinned rows).
            data-testid="sidebar-conversation-title"
            className="min-w-0 flex-1 truncate"
          >
            {conversation.title}
          </span>
        </button>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              type="button"
              variant="ghost"
              aria-label="Conversation actions"
              onClick={stopBubble}
              className={cn(
                "size-11 md:size-7 shrink-0 rounded-full p-0 text-muted-foreground transition-opacity hover:text-foreground",
                // Always visible on touch; reveal on hover/focus on desktop.
                "opacity-100 md:opacity-0 md:group-hover/conv:opacity-100 md:focus-within:opacity-100 md:aria-expanded:opacity-100",
              )}
            >
              <MoreHorizontal className="size-4" aria-hidden />
            </Button>
          }
        />
        <DropdownMenuContent align="end" className="w-40">
          <DropdownMenuItem
            label="Rename"
            onClick={enterRename}
            className="gap-2"
          >
            <Pencil className="size-4" aria-hidden />
            <span>Rename</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            label={pinAction}
            onClick={() => onTogglePin(conversation.id)}
            className="gap-2"
          >
            {conversation.pinned ? (
              <PinOff className="size-4" aria-hidden />
            ) : (
              <Pin className="size-4" aria-hidden />
            )}
            <span>{pinAction}</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            label="Copy conversation"
            onClick={() => onCopy(conversation.id)}
            className="gap-2"
          >
            <ClipboardCopy className="size-4" aria-hidden />
            <span>Copy conversation</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            label="Delete"
            variant="destructive"
            onClick={() => onRequestDelete(conversation)}
            className="gap-2"
          >
            <Trash2 className="size-4" aria-hidden />
            <span>Delete</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      </div>
    </div>
  );
}

// Per-id transition phase driving the row-wrapper enter/exit motion. "enter" is
// only ever assigned to rows added *after* the first commit (see the seen-set
// discipline in useListTransitions); rows present at mount get no phase so the
// initial list never animates in.
type RowPhase = "enter" | "exit";

// Exit collapse duration; the unmount fallback timer matches this so a missed
// transitionend (e.g. reduced motion, display:none ancestor) never leaks a row.
const ROW_EXIT_MS = 250;

// Wrapper that owns the per-row enter/exit choreography. The motion lives here
// — on the OUTER list item — never on ConversationRow's inner sliding layer,
// whose `transform: translate3d(...)` carries the swipe. Stacking enter/exit
// transforms onto that layer would fight the gesture, so we animate height +
// opacity (and a tiny translate for enter only) on this separate element.
//
//   - ENTER: a `starting:` @starting-style snapshot (opacity-0 + slight upward
//     offset) that the row transitions *out of* on first paint. Applied only
//     when phase === "enter", so the seen-set guard in useListTransitions keeps
//     it off rows present at mount.
//   - EXIT: collapse via grid-template-rows 1fr → 0fr (the only way to ease to
//     an auto height) + fade. We mount the exiting row open, then flip to the
//     collapsed state in a layout effect so the transition has two frames to
//     run, and fire `onExited` on transitionend. The hook arms a matching
//     timeout fallback, so reduced motion (transition:none → no transitionend)
//     and display:none ancestors still unmount the row.
function RowWrapper({
  phase,
  onExited,
  children,
}: {
  phase?: RowPhase;
  onExited: () => void;
  children: React.ReactNode;
}): React.JSX.Element {
  // For exit we start "open" (1fr) and collapse to "0fr" after the first paint
  // so the grid-rows transition actually animates instead of mounting collapsed.
  const [collapsed, setCollapsed] = useState(false);

  useLayoutEffect(() => {
    if (phase !== "exit") return;
    // Next frame: flip to collapsed so 1fr → 0fr animates. rAF (not a sync set)
    // guarantees the browser commits the open state first.
    const id = window.requestAnimationFrame(() => setCollapsed(true));
    return () => window.cancelAnimationFrame(id);
  }, [phase]);

  if (phase === "exit") {
    return (
      <div
        role="listitem"
        aria-hidden
        // `inert` (React 19 DOM attr) drops the collapsing row from the tab
        // order and blocks clicks — without it the still-live ConversationRow
        // controls stay focusable/clickable inside an aria-hidden subtree
        // during the ~250ms collapse (an a11y violation). pointer-events-none
        // is the belt-and-braces for browsers lagging on `inert`.
        inert
        // grid-rows collapse is the height half; the inner min-h-0 child lets
        // the 0fr track actually shrink. Reduced motion skips the ease (the
        // hook's fallback timer still unmounts), keeping the row from lingering.
        className={cn(
          "pointer-events-none grid transition-[grid-template-rows,opacity] duration-[250ms] ease-ios-smooth motion-reduce:transition-none",
          collapsed
            ? "grid-rows-[0fr] opacity-0"
            : "grid-rows-[1fr] opacity-100",
        )}
        // Fire on the grid-template-rows leg (opacity finishes first); any leg
        // is fine since both share the duration — onExited is idempotent.
        onTransitionEnd={(e) => {
          if (e.propertyName === "grid-template-rows") onExited();
        }}
      >
        <div className="min-h-0 overflow-hidden">{children}</div>
      </div>
    );
  }

  if (phase === "enter") {
    return (
      <div
        role="listitem"
        // starting: is the @starting-style snapshot the row eases out of on its
        // first paint (Tailwind v4 maps it to @starting-style). Guarded by the
        // "enter" phase so only genuinely-new rows animate. Reduced motion drops
        // the slide and just cross-fades from the starting opacity.
        className="transition-[opacity,transform] duration-[300ms] ease-ios-smooth starting:opacity-0 starting:-translate-y-1 motion-reduce:transition-opacity motion-reduce:translate-y-0"
      >
        {children}
      </div>
    );
  }

  return <div role="listitem">{children}</div>;
}

interface DisplayRow {
  conversation: ConversationSummary;
  phase?: RowPhase;
}

/**
 * Drives conversation-list enter/exit motion without a JS animation lib:
 *
 * - ENTER: a `seenRef` Set + a `mountedRef` gate. Rows present at first commit
 *   are seeded into `seen` so they never animate; only ids that first appear
 *   *after* mount get the "enter" phase (which arms a `starting:` @starting-style
 *   transition on the wrapper). Ids are committed to `seen` after paint.
 * - EXIT: React unmounts removed rows synchronously, so we keep a snapshot of
 *   each id's last props/position and re-inject removed rows in an "exit" phase
 *   until their collapse transition finishes (transitionend, with a timeout
 *   fallback). Works for both delete paths (the dialog and the full-swipe both
 *   route through the parent's prop removal), and never double-animates.
 *
 * Returns the merged render list (live rows + still-exiting rows in their last
 * position) plus an `onRowExited` callback the wrapper fires when its collapse
 * transition ends.
 */
function useListTransitions(conversations: ConversationSummary[]): {
  rows: DisplayRow[];
  onRowExited: (id: string) => void;
} {
  const mountedRef = useRef(false);
  const seenRef = useRef<Set<string>>(new Set());
  // Last render's conversations, by id and by index, used to detect removals
  // and to re-insert an exiting row at roughly its prior position.
  const prevOrderRef = useRef<string[]>([]);
  const prevByIdRef = useRef<Map<string, ConversationSummary>>(new Map());
  // Rows mid-exit: snapshot + the id they followed in the prior order so the
  // collapsing row stays put rather than jumping to the list end.
  const exitingRef = useRef<Map<string, { conversation: ConversationSummary; after: string | null }>>(
    new Map(),
  );
  const exitTimersRef = useRef<Map<string, number>>(new Map());
  // Bump to force a re-render when an exit finishes (refs alone won't repaint).
  const [, forceRender] = useState(0);

  // This hook intentionally derives its render output from refs synchronously
  // (the seen-set guard and the exit snapshots must be consistent *within* the
  // same render that emits the merged list — a post-paint effect would flash a
  // wrong frame). The only during-render ref write (the seenRef seeding) is
  // gated on !mountedRef.current and is idempotent; all post-mount ref writes
  // happen in effects. Reads stay id-keyed, so they are safe under StrictMode's
  // double render. Hence the scoped react-hooks/refs waiver below.
  /* eslint-disable react-hooks/refs */

  // Seed `seen` with the initial list so first paint never animates rows in.
  if (!mountedRef.current && seenRef.current.size === 0) {
    for (const c of conversations) seenRef.current.add(c.id);
  }

  const currentIds = new Set(conversations.map((c) => c.id));

  // Detect removals: ids that were rendered last commit but are gone now (and
  // aren't already exiting) become exiting snapshots. Skip before mount.
  if (mountedRef.current) {
    for (let i = 0; i < prevOrderRef.current.length; i++) {
      const id = prevOrderRef.current[i];
      if (currentIds.has(id) || exitingRef.current.has(id)) continue;
      const snapshot = prevByIdRef.current.get(id);
      if (!snapshot) continue;
      // Anchor to the nearest previous-order predecessor that's still LIVE
      // (in currentIds), skipping any predecessor also removed this commit —
      // anchoring to another exiting id would orphan this snapshot (no live
      // anchor emits it, so only the fallback timer would clear it). Falling
      // back to null emits it in the leading group, keeping the bulk-delete
      // case (row + its predecessor removed together) animating.
      let after: string | null = null;
      for (let j = i - 1; j >= 0; j--) {
        if (currentIds.has(prevOrderRef.current[j])) {
          after = prevOrderRef.current[j];
          break;
        }
      }
      exitingRef.current.set(id, { conversation: snapshot, after });
    }
  }

  const onRowExited = useCallback((id: string) => {
    const timer = exitTimersRef.current.get(id);
    if (timer != null) {
      window.clearTimeout(timer);
      exitTimersRef.current.delete(id);
    }
    if (exitingRef.current.delete(id)) {
      forceRender((n) => n + 1);
    }
  }, []);

  // Arm a fallback timer per exiting row in case transitionend never fires.
  useEffect(() => {
    for (const id of exitingRef.current.keys()) {
      if (exitTimersRef.current.has(id)) continue;
      const timer = window.setTimeout(() => onRowExited(id), ROW_EXIT_MS + 80);
      exitTimersRef.current.set(id, timer);
    }
  });

  // After paint: mark mounted, commit freshly-seen ids, snapshot this order.
  useEffect(() => {
    mountedRef.current = true;
    for (const c of conversations) seenRef.current.add(c.id);
    prevOrderRef.current = conversations.map((c) => c.id);
    prevByIdRef.current = new Map(conversations.map((c) => [c.id, c]));
  });

  // Clean up every pending timer on unmount.
  useEffect(() => {
    const timers = exitTimersRef.current;
    return () => {
      for (const t of timers.values()) window.clearTimeout(t);
      timers.clear();
    };
  }, []);

  // Build the merged list: live rows (tagged "enter" when genuinely new) with
  // exiting snapshots re-inserted after their anchor id.
  const rows: DisplayRow[] = [];
  const emitExitingAfter = (anchor: string | null) => {
    for (const entry of exitingRef.current.values()) {
      if (entry.after === anchor) {
        rows.push({ conversation: entry.conversation, phase: "exit" });
      }
    }
  };
  emitExitingAfter(null);
  for (const c of conversations) {
    const phase: RowPhase | undefined =
      mountedRef.current && !seenRef.current.has(c.id) ? "enter" : undefined;
    rows.push({ conversation: c, phase });
    emitExitingAfter(c.id);
  }

  /* eslint-enable react-hooks/refs */

  return { rows, onRowExited };
}

export function Sidebar({
  conversations,
  activeId,
  account,
  search,
  onSearchChange,
  onSelect,
  onNewChat,
  onRenameConversation,
  onDeleteConversation,
  onTogglePinConversation,
  onCopyConversation,
  onOpenSettings,
  onSignIn,
  onSignOut,
  onCollapse,
  className,
}: SidebarProps): React.JSX.Element {
  const anonymous = isAnonymousAccount(account);
  const trimmedSearch = search.trim();
  const isSearching = trimmedSearch.length > 0;

  // Merge in enter/exit transition bookkeeping. `displayConversations` is the
  // live list plus any rows still collapsing out; `phaseById` tags which of
  // those should animate in ("enter") or out ("exit").
  const { rows: displayRows, onRowExited } = useListTransitions(conversations);
  const displayConversations = displayRows.map((r) => r.conversation);
  const phaseById = new Map<string, RowPhase>();
  for (const r of displayRows) {
    if (r.phase) phaseById.set(r.conversation.id, r.phase);
  }

  // Exiting snapshots (phase === "exit") always survive the filter so a row
  // deleted while a search is active still animates out, even if its title no
  // longer matches the query — otherwise its RowWrapper never mounts and the
  // collapse falls back to the (silent) unmount timer.
  const filteredConversations = isSearching
    ? displayRows
        .filter(
          (r) =>
            r.phase === "exit" ||
            r.conversation.title
              .toLowerCase()
              .includes(trimmedSearch.toLowerCase()),
        )
        .map((r) => r.conversation)
    : displayConversations;
  const groups = isSearching
    ? new Map<RecencyKey, ConversationSummary[]>()
    : groupConversations(filteredConversations);

  const [pendingDelete, setPendingDelete] =
    useState<ConversationSummary | null>(null);

  const activeRowRef = useRef<HTMLDivElement | null>(null);
  // useLayoutEffect avoids a flash on mobile-drawer open: each drawer mount is a
  // fresh Sidebar instance, so the active row is pulled into view before paint.
  useLayoutEffect(() => {
    if (!activeId) return;
    const node = activeRowRef.current;
    if (!node) return;
    node.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeId]);

  const confirmDelete = () => {
    if (!pendingDelete) return;
    onDeleteConversation(pendingDelete.id);
    setPendingDelete(null);
  };

  const renderRow = (conversation: ConversationSummary) => {
    const phase = phaseById.get(conversation.id);
    return (
      <RowWrapper
        key={conversation.id}
        phase={phase}
        onExited={() => onRowExited(conversation.id)}
      >
        <ConversationRow
          conversation={conversation}
          active={conversation.id === activeId}
          activeRowRef={activeRowRef}
          onSelect={onSelect}
          onRename={onRenameConversation}
          onTogglePin={onTogglePinConversation}
          onCopy={onCopyConversation}
          onRequestDelete={setPendingDelete}
        />
      </RowWrapper>
    );
  };

  return (
    <nav
      aria-label="Sidebar"
      className={cn(
        "flex h-full flex-col bg-sidebar text-sidebar-foreground",
        className
      )}
    >
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center">
          <span className="text-sm font-semibold">Olune</span>
        </div>
        {onCollapse ? (
          <Button
            type="button"
            variant="ghost"
            aria-label="Collapse sidebar"
            onClick={onCollapse}
            className="size-9 rounded-full p-0 text-muted-foreground transition-colors hover:text-foreground"
          >
            <PanelLeftClose className="size-4" aria-hidden />
          </Button>
        ) : null}
      </div>

      <div className="px-2 pb-2">
        {/* iOS-style pill row matching the conversation list below — no border,
            no fill until hover, so the action reads as part of the same surface
            family rather than a heavy outlined affordance. */}
        <button
          type="button"
          onClick={onNewChat}
          // E2E target: the header also has a "New chat" affordance, and the
          // testid keeps us from picking the wrong one.
          data-testid="sidebar-new-chat"
          className="flex min-h-11 w-full select-none items-center gap-2 rounded-2xl px-3 py-2 text-left text-sm font-medium text-sidebar-foreground outline-none transition-[transform,background-color] duration-100 touch-manipulation hover:bg-muted/60 focus-visible:shadow-[var(--focus-ring)] active:scale-[0.97]"
        >
          <Plus className="size-4" aria-hidden />
          <span>New chat</span>
        </button>
      </div>

      <div className="px-2 pb-2">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search conversations"
            aria-label="Search conversations"
            className="block h-11 w-full rounded-full bg-muted/50 pl-8 pr-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus-visible:shadow-[var(--focus-ring)]"
          />
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="px-2 pb-2">
          {isSearching ? (
            filteredConversations.length === 0 ? (
              <div className="px-2 py-6 text-center text-sm text-muted-foreground">
                No conversations
              </div>
            ) : (
              <div role="list" aria-label="Search results">
                {filteredConversations.map(renderRow)}
              </div>
            )
          ) : (
            GROUP_ORDER.map((key) => {
              const items = groups.get(key);
              if (!items || items.length === 0) {
                return null;
              }
              return (
                // Ma: tripled inter-group gutter so the recency label gains
                // weight from surrounding silence, not from size or color.
                <div key={key} className="mb-6">
                  <div className="px-2 pb-2 pt-1 text-xs font-semibold text-muted-foreground">
                    {RECENCY_LABELS[key]}
                  </div>
                  <div role="list" aria-label={RECENCY_LABELS[key]}>
                    {items.map(renderRow)}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>

      <div className="mt-3 p-2 pt-3">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label="Account menu"
                className="flex w-full select-none items-center gap-2 rounded-2xl p-2 text-left outline-none transition-[transform,background-color] duration-100 touch-manipulation hover:bg-muted/60 focus-visible:shadow-[var(--focus-ring)] aria-expanded:bg-muted/60 active:not-aria-[haspopup]:scale-[0.97]"
              >
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground">
                  {initials(account.name)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">
                    {account.name}
                  </div>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <span className="truncate">{account.planLabel}</span>
                    {account.byokEnabled ? (
                      <Key className="size-3.5 shrink-0" aria-hidden />
                    ) : null}
                  </div>
                </div>
                <MoreHorizontal
                  className="ml-auto size-4 shrink-0 text-muted-foreground"
                  aria-hidden
                />
              </button>
            }
          />
          <DropdownMenuContent align="end" side="top" className="w-56">
            {anonymous ? (
              <DropdownMenuItem
                label="Sign in"
                onClick={onSignIn}
                className="gap-2"
              >
                <LogIn className="size-4" aria-hidden />
                <span>Sign in</span>
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem
              label="Settings"
              onClick={onOpenSettings}
              className="gap-2"
            >
              <Settings className="size-4" aria-hidden />
              <span>Settings</span>
            </DropdownMenuItem>
            {!anonymous ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  label="Sign out"
                  onClick={onSignOut}
                  className="gap-2"
                >
                  <LogOut className="size-4" aria-hidden />
                  <span>Sign out</span>
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(next) => {
          if (!next) setPendingDelete(null);
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
            <DialogDescription>
              {pendingDelete
                ? `This will delete "${pendingDelete.title}" permanently. This can't be undone.`
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPendingDelete(null)}
              className="h-11 rounded-full px-6"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmDelete}
              // Solid native-destructive fill (not the soft tint the variant
              // uses elsewhere) so the primary commit action reads clearly; 44px
              // iOS touch target.
              className="h-11 rounded-full bg-destructive px-6 text-white hover:bg-destructive/90 dark:bg-destructive dark:text-white dark:hover:bg-destructive/90"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </nav>
  );
}
