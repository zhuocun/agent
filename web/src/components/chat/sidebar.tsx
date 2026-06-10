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
  Archive,
  ArchiveRestore,
  Boxes,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Download,
  Folder,
  FolderPlus,
  Key,
  LogIn,
  LogOut,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Settings,
  SlidersHorizontal,
  Tag as TagIcon,
  Tags,
  Timer,
  Trash2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/context";
import { prefersReducedMotion } from "@/lib/motion";
import { useSwipeActions } from "@/lib/use-swipe-actions";
import {
  isAnonymousAccount,
  type AccountInfo,
  type ConversationSummary,
  type ProjectSummary,
  type Tag,
} from "@/lib/types";

// Width of the swipe-revealed trailing action tray (two 64px action buttons).
const SWIPE_ACTIONS_WIDTH = 128;

export interface SidebarProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  account: AccountInfo;
  search: string;
  searchResults?: ConversationSummary[] | null;
  searchPending?: boolean;
  onSearchChange: (next: string) => void;
  // Open the advanced history-search dialog (filters by model, cost, date,
  // project, tag). Optional so a stale embedding of <Sidebar/> still type-checks;
  // the affordance is hidden when it's not provided.
  onOpenAdvancedSearch?: () => void;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onRenameConversation: (id: string, newTitle: string) => void;
  onDeleteConversation: (id: string) => void;
  onTogglePinConversation: (id: string) => void;
  // Set (number) or clear (null) the per-conversation retention override (D31).
  onSetConversationRetention: (id: string, retentionDays: number | null) => void;
  onCopyConversation: (id: string) => void;
  onDownloadConversation: (id: string) => void;
  onOpenSettings: () => void;
  // Projects/Spaces (D20). `projects` is the caller's container set; the other
  // callbacks file/un-file a conversation and create/rename/delete a project.
  // `onManageProjects` opens the per-project settings panel (in the settings
  // dialog). All optional so a stale embedding of <Sidebar/> still type-checks.
  projects?: ProjectSummary[];
  onAssignConversationToProject?: (id: string, projectId: string | null) => void;
  onCreateProject?: (name: string) => void;
  onRenameProject?: (id: string, name: string) => void;
  onDeleteProject?: (id: string) => void;
  onManageProjects?: () => void;
  // Tags (Conversation Org v2). `tags` is the caller's label set; the callbacks
  // create/rename/delete a tag, set the active sidebar tag filter, replace a
  // single conversation's tag set, and archive/unarchive a conversation. All
  // optional so a stale embedding of <Sidebar/> still type-checks; the BULK
  // callbacks receive the explicit id list and run the optimistic mutation in
  // the parent. `activeTagId` reflects the current filter (null = all).
  tags?: Tag[];
  activeTagId?: string | null;
  onSetTagFilter?: (tagId: string | null) => void;
  onCreateTag?: (name: string) => void;
  onRenameTag?: (id: string, name: string) => void;
  onDeleteTag?: (id: string) => void;
  onAssignConversationTags?: (id: string, tagIds: string[]) => void;
  onArchiveConversation?: (id: string, archived: boolean) => void;
  onBulkArchive?: (ids: string[], archived: boolean) => void;
  onBulkDelete?: (ids: string[]) => void;
  onBulkAddTag?: (ids: string[], tagId: string) => void;
  onBulkRemoveTag?: (ids: string[], tagId: string) => void;
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

// Per-conversation retention options (D31) surfaced in the kebab submenu.
// `value` is the wire `retentionDays`: `null` clears the override so the
// conversation inherits the user's global retention; a number sets a durable
// per-conversation window. Mirrors the global retention choices (30 / 90) plus
// the "inherit" reset.
const RETENTION_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: "Use default" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
];

// Stable string key for a (nullable) retention value, so the radio group can
// round-trip `null` through base-ui's string-valued RadioGroup.
function retentionKey(value: number | null | undefined): string {
  return value == null ? "default" : String(value);
}

// "expires in ~N days" / "expires today" hint for a conversation whose override
// is set. Computed from `updatedAt + retentionDays` (retention is keyed on
// `updatedAt`, matching the BE purge). Returns null when no override is set or
// the timestamp is unparseable. Past-due collapses to "expires soon" rather
// than a negative count (the scheduled purge will remove it on the next sweep).
function expiresHint(
  retentionDays: number | null | undefined,
  updatedAt: string,
): string | null {
  if (retentionDays == null) return null;
  const updatedMs = Date.parse(updatedAt);
  if (Number.isNaN(updatedMs)) return null;
  const expiresMs = updatedMs + retentionDays * 86_400_000;
  const dayDiff = Math.ceil((expiresMs - Date.now()) / 86_400_000);
  if (dayDiff <= 0) return "expires soon";
  if (dayDiff === 1) return "expires in ~1 day";
  return `expires in ~${dayDiff} days`;
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
  projects,
  tags,
  selectionMode,
  selected,
  onToggleSelect,
  onSelect,
  onRename,
  onTogglePin,
  onSetRetention,
  onAssignProject,
  onAssignTags,
  onArchive,
  onCopy,
  onDownload,
  onRequestDelete,
  bulkEnabled,
  onEnterSelection,
}: {
  conversation: ConversationSummary;
  active: boolean;
  activeRowRef?: React.RefObject<HTMLDivElement | null>;
  projects: ProjectSummary[];
  tags: Tag[];
  // Multi-select: when `selectionMode` is on, a leading checkbox replaces the
  // pin glyph and a row tap toggles selection instead of opening the chat.
  selectionMode: boolean;
  selected: boolean;
  bulkEnabled?: boolean;
  onEnterSelection?: () => void;
  onToggleSelect: (id: string) => void;
  onSelect: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onTogglePin: (id: string) => void;
  onSetRetention: (id: string, retentionDays: number | null) => void;
  onAssignProject?: (id: string, projectId: string | null) => void;
  // Full-replace a conversation's tag set (Conversation Org v2).
  onAssignTags?: (id: string, tagIds: string[]) => void;
  onArchive?: (id: string, archived: boolean) => void;
  onCopy: (id: string) => void;
  onDownload: (id: string) => void;
  onRequestDelete: (conversation: ConversationSummary) => void;
}): React.JSX.Element {
  const [isRenaming, setIsRenaming] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  // M-flatten: the three low-frequency config controls (Retention, Assign to
  // project, Assign tags) used to live in a 3-level nested kebab submenu. They
  // now open a single shared Dialog (bottom sheet on mobile, centered modal on
  // desktop) with three flat iOS inset-grouped sections.
  const [organizeOpen, setOrganizeOpen] = useState(false);
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
    // In multi-select mode a row tap toggles its checkbox instead of opening
    // the conversation.
    if (selectionMode) {
      onToggleSelect(conversation.id);
      return;
    }
    onSelect(conversation.id);
  };

  const stopBubble = (e: ReactMouseEvent) => {
    e.stopPropagation();
  };

  const pinAction = conversation.pinned ? "Unpin" : "Pin";
  const archived = conversation.archived === true;
  // Resolve the conversation's assigned tag ids to the live tag objects so the
  // row renders chips with the current name/color even after a rename.
  const tagById = new Map(tags.map((t) => [t.id, t] as const));
  const assignedTags = (conversation.tagIds ?? [])
    .map((id) => tagById.get(id))
    .filter((t): t is Tag => t !== undefined);
  const assignedTagIds = new Set(conversation.tagIds ?? []);
  const matchSnippet = conversation.matchSnippet?.trim();
  // "expires in ~N days" hint for a per-conversation retention override (D31).
  // Suppressed while a search snippet is showing (the snippet wins the one line).
  const retentionExpiresHint = expiresHint(
    conversation.retentionDays,
    conversation.updatedAt,
  );

  // Reduced motion → snap instantly; otherwise ease the reveal/settle. While
  // actively dragging we never transition (the finger is the clock).
  const slideTransition =
    swipe.dragging || swipe.reducedMotion
      ? undefined
      : "transform 200ms var(--ease-ios-smooth)";

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
          className="flex w-16 select-none flex-col items-center justify-center gap-1 bg-destructive text-xs font-medium text-destructive-foreground transition-transform duration-100 touch-manipulation active:scale-[0.97]"
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
      {/* Multi-select checkbox renders as a SIBLING of the row button, never
          nested inside it — a <button> can't contain another interactive
          <button> (invalid HTML; the inner click gets swallowed). Mirrors the
          rename-input sibling pattern below. */}
      {selectionMode && !isRenaming ? (
        <span
          className="flex shrink-0 items-center pl-3"
          // The checkbox handles its own click; stop it from also reaching the
          // row's tap target.
          onClick={stopBubble}
        >
          <Checkbox
            checked={selected}
            onCheckedChange={() => onToggleSelect(conversation.id)}
            aria-label={`Select ${conversation.title}`}
            data-testid="sidebar-conversation-checkbox"
          />
        </span>
      ) : null}
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
            // text-base on mobile keeps iOS Safari from auto-zooming the page
            // when the input focuses (it zooms anything under 16px).
            className="min-w-0 flex-1 bg-transparent text-base text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] rounded-sm md:text-sm"
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
          <span className="min-w-0 flex-1">
            <span
              // E2E target: reads the rendered title text without depending on
              // the aria-label format (which appends ", pinned" for pinned rows).
              data-testid="sidebar-conversation-title"
              className="block truncate"
            >
              {conversation.title}
            </span>
            {assignedTags.length > 0 ? (
              <span
                className="mt-1 hidden flex-wrap gap-1 md:flex"
                data-testid="sidebar-conversation-tags"
              >
                {assignedTags.map((tag) => (
                  <Badge
                    key={tag.id}
                    variant="secondary"
                    data-testid="sidebar-conversation-tag-chip"
                    className="max-w-[10rem] truncate"
                    style={
                      tag.color
                        ? {
                            backgroundColor: `${tag.color}20`,
                            color: tag.color,
                          }
                        : undefined
                    }
                  >
                    {tag.name}
                  </Badge>
                ))}
              </span>
            ) : null}
            {matchSnippet ? (
              <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                {matchSnippet}
              </span>
            ) : retentionExpiresHint ? (
              <span
                // E2E + a11y target: the per-conversation retention countdown,
                // shown only when an override is set (D31).
                data-testid="sidebar-conversation-retention-hint"
                className="mt-0.5 flex items-center gap-1 truncate text-xs text-muted-foreground"
              >
                <Timer className="size-3 shrink-0" aria-hidden />
                {retentionExpiresHint}
              </span>
            ) : null}
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
                "size-11 shrink-0 rounded-full p-0 text-muted-foreground transition-opacity hover:text-foreground md:size-7",
                // Always visible on touch; reveal on hover/focus on desktop.
                "opacity-100 md:opacity-0 md:group-hover/conv:opacity-100 md:focus-within:opacity-100 md:aria-expanded:opacity-100",
              )}
            >
              <MoreHorizontal className="size-4" aria-hidden />
            </Button>
          }
        />
        <DropdownMenuContent align="end" className="w-40">
          {!selectionMode && bulkEnabled && onEnterSelection ? (
            <DropdownMenuItem
              label="Select"
              onClick={() => {
                onEnterSelection();
                onToggleSelect(conversation.id);
              }}
              className="gap-2 md:hidden"
              data-testid="sidebar-select-from-row"
            >
              <Check className="size-4" aria-hidden />
              <span>Select</span>
            </DropdownMenuItem>
          ) : null}
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
          {/* M-flatten: the three low-frequency config controls (Retention,
              Assign to project, Assign tags) used to live in a 3-level nested
              submenu. They now open a single shared Dialog with three flat
              iOS inset-grouped sections (rendered below the menu). The kebab
              keeps just a short frequent list (Rename / Pin / Organize… /
              Archive / Copy / Download / Delete). */}
          <DropdownMenuItem
            label="Organize…"
            onClick={() => setOrganizeOpen(true)}
            className="gap-2"
            data-testid="sidebar-conversation-organize"
          >
            <SlidersHorizontal className="size-4" aria-hidden />
            <span>Organize…</span>
          </DropdownMenuItem>
          {onArchive ? (
            <DropdownMenuItem
              label={archived ? "Unarchive" : "Archive"}
              onClick={() => onArchive(conversation.id, !archived)}
              className="gap-2"
              data-testid="sidebar-conversation-archive"
            >
              {archived ? (
                <ArchiveRestore className="size-4" aria-hidden />
              ) : (
                <Archive className="size-4" aria-hidden />
              )}
              <span>{archived ? "Unarchive" : "Archive"}</span>
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem
            label="Copy conversation"
            onClick={() => onCopy(conversation.id)}
            className="gap-2"
          >
            <ClipboardCopy className="size-4" aria-hidden />
            <span>Copy conversation</span>
          </DropdownMenuItem>
          <DropdownMenuItem
            label="Download Markdown"
            onClick={() => onDownload(conversation.id)}
            className="gap-2"
          >
            <Download className="size-4" aria-hidden />
            <span>Download Markdown</span>
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

      {/* Flat "Organize…" sheet: replaces the former 3-level nested submenus.
          Three iOS inset-grouped sections (Retention / Assign to project /
          Assign tags), each a `glass-clear` card with hairline-separated rows.
          The original e2e testids are preserved on the section group containers
          + the tag rows so the wire contract is unchanged. */}
      <Dialog open={organizeOpen} onOpenChange={setOrganizeOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Organize conversation</DialogTitle>
            <DialogDescription className="truncate">
              {conversation.title}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5">
            {/* Retention */}
            <section className="space-y-2">
              <h3 className="px-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                Retention
              </h3>
              <div
                role="radiogroup"
                aria-label="Retention"
                className="glass-clear overflow-hidden rounded-2xl"
                data-testid="sidebar-conversation-retention"
              >
                {RETENTION_OPTIONS.map((option, index) => {
                  const selected =
                    retentionKey(conversation.retentionDays) ===
                    retentionKey(option.value);
                  return (
                    <button
                      key={retentionKey(option.value)}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() =>
                        onSetRetention(conversation.id, option.value)
                      }
                      className={cn(
                        "flex min-h-11 w-full items-center gap-2 px-3.5 py-3 text-left text-sm outline-none transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04]",
                        index > 0 && "border-t border-border/60",
                      )}
                    >
                      <span className="min-w-0 flex-1">{option.label}</span>
                      {selected ? (
                        <Check
                          className="size-4 shrink-0 text-brand"
                          aria-hidden
                        />
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </section>

            {/* Assign to project */}
            {onAssignProject ? (
              <section className="space-y-2">
                <h3 className="px-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Assign to project
                </h3>
                <div
                  role="radiogroup"
                  aria-label="Assign to project"
                  className="glass-clear overflow-hidden rounded-2xl"
                  data-testid="sidebar-conversation-assign-project"
                >
                  {[{ id: "none", name: "No project" }, ...projects].map(
                    (project, index) => {
                      const value = project.id === "none" ? null : project.id;
                      const selected =
                        (conversation.projectId ?? null) === value;
                      return (
                        <button
                          key={project.id}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          onClick={() =>
                            onAssignProject(conversation.id, value)
                          }
                          className={cn(
                            "flex min-h-11 w-full items-center gap-2 px-3.5 py-3 text-left text-sm outline-none transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04]",
                            index > 0 && "border-t border-border/60",
                          )}
                        >
                          <span className="min-w-0 flex-1 truncate">
                            {project.name}
                          </span>
                          {selected ? (
                            <Check
                              className="size-4 shrink-0 text-brand"
                              aria-hidden
                            />
                          ) : null}
                        </button>
                      );
                    },
                  )}
                </div>
              </section>
            ) : null}

            {/* Assign tags */}
            {onAssignTags && tags.length > 0 ? (
              <section className="space-y-2">
                <h3 className="px-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Assign tags
                </h3>
                <div
                  className="glass-clear overflow-hidden rounded-2xl"
                  data-testid="sidebar-conversation-assign-tags"
                >
                  {tags.map((tag, index) => {
                    const isAssigned = assignedTagIds.has(tag.id);
                    return (
                      <button
                        key={tag.id}
                        type="button"
                        role="checkbox"
                        aria-checked={isAssigned}
                        // Toggle this tag in/out of the conversation's set, then
                        // send the FULL replacement set (the BE PATCH replaces).
                        onClick={() => {
                          const next = isAssigned
                            ? (conversation.tagIds ?? []).filter(
                                (id) => id !== tag.id,
                              )
                            : [...(conversation.tagIds ?? []), tag.id];
                          onAssignTags(conversation.id, next);
                        }}
                        className={cn(
                          "flex min-h-11 w-full items-center gap-2 px-3.5 py-3 text-left text-sm outline-none transition-colors hover:bg-foreground/[0.04] focus-visible:bg-foreground/[0.04]",
                          index > 0 && "border-t border-border/60",
                        )}
                        data-testid="sidebar-conversation-tag-option"
                      >
                        <span className="min-w-0 flex-1 truncate">
                          {tag.name}
                        </span>
                        {isAssigned ? (
                          <Check
                            className="size-4 shrink-0 text-brand"
                            aria-hidden
                          />
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
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
  searchResults,
  searchPending = false,
  onSearchChange,
  onOpenAdvancedSearch,
  onSelect,
  onNewChat,
  onRenameConversation,
  onDeleteConversation,
  onTogglePinConversation,
  onSetConversationRetention,
  onCopyConversation,
  onDownloadConversation,
  onOpenSettings,
  projects = [],
  onAssignConversationToProject,
  onCreateProject,
  onRenameProject,
  onDeleteProject,
  onManageProjects,
  tags = [],
  activeTagId = null,
  onSetTagFilter,
  onCreateTag,
  onRenameTag,
  onDeleteTag,
  onAssignConversationTags,
  onArchiveConversation,
  onBulkArchive,
  onBulkDelete,
  onBulkAddTag,
  onBulkRemoveTag,
  onSignIn,
  onSignOut,
  onCollapse,
  className,
}: SidebarProps): React.JSX.Element {
  const t = useT();
  const anonymous = isAnonymousAccount(account);
  const trimmedSearch = search.trim();
  const isSearching = trimmedSearch.length > 0;
  const hasRemoteSearchResults =
    isSearching && searchResults !== undefined && searchResults !== null;

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
    ? hasRemoteSearchResults
      ? searchResults
      : displayRows
        .filter(
          (r) =>
            r.phase === "exit" ||
            r.conversation.title
              .toLowerCase()
              .includes(trimmedSearch.toLowerCase()),
        )
        .map((r) => r.conversation)
    : displayConversations;
  // Tag filter (Conversation Org v2): when a tag is active, only conversations
  // carrying it survive (exiting snapshots always pass so a delete still
  // animates out). Search is orthogonal — when searching, the tag filter is
  // ignored so the query result is never silently narrowed.
  const knownTagIds = new Set(tags.map((t) => t.id));
  const activeTagFilter =
    activeTagId && knownTagIds.has(activeTagId) ? activeTagId : null;
  const tagFilteredRows =
    activeTagFilter && !isSearching
      ? displayRows.filter(
          (r) =>
            r.phase === "exit" ||
            (r.conversation.tagIds ?? []).includes(activeTagFilter),
        )
      : displayRows;
  const tagFilteredConversations = tagFilteredRows.map((r) => r.conversation);
  // The base list for the non-search render: tag-filtered live rows.
  const baseConversations = isSearching
    ? filteredConversations
    : tagFilteredConversations;
  // Conversations filed under a KNOWN project render in the Projects section, so
  // the recency groups exclude them to avoid double-listing. A conversation
  // whose `projectId` points at a project not in this list (e.g. a stale id)
  // still falls through to the recency groups so it never disappears. ARCHIVED
  // conversations are pulled out into their own collapsible section, so the
  // recency groups exclude them too (mirrors the project exclusion).
  const knownProjectIds = new Set(projects.map((p) => p.id));
  const archivedConversations = isSearching
    ? []
    : baseConversations.filter((c) => c.archived === true);
  const recencyConversations = isSearching
    ? filteredConversations
    : baseConversations.filter(
        (c) =>
          c.archived !== true &&
          !(c.projectId && knownProjectIds.has(c.projectId)),
      );
  const groups = isSearching
    ? new Map<RecencyKey, ConversationSummary[]>()
    : groupConversations(recencyConversations);

  const [pendingDelete, setPendingDelete] =
    useState<ConversationSummary | null>(null);
  // Projects/Spaces (D20): the inline create/rename dialog state, and the
  // pending project deletion confirmation. `projectDialog` is null when closed;
  // `{ mode: "create" }` opens a name prompt; `{ mode: "rename", id, name }`
  // pre-fills the existing name. The dialog is functional and consistent with
  // the conversation-delete confirmation already in this file.
  const [projectDialog, setProjectDialog] = useState<
    { mode: "create" } | { mode: "rename"; id: string; name: string } | null
  >(null);
  const [projectDraft, setProjectDraft] = useState("");
  const [pendingProjectDelete, setPendingProjectDelete] =
    useState<ProjectSummary | null>(null);

  // Group conversations by project for the Projects section. Only conversations
  // actually filed under each project appear; the per-project bucket reuses the
  // live (tag-filtered) rows so optimistic assigns/detaches reflect instantly.
  // Archived conversations are pulled out into the Archived section, so they're
  // excluded here too.
  const conversationsByProject = new Map<string, ConversationSummary[]>();
  for (const conversation of tagFilteredConversations) {
    if (conversation.archived === true) continue;
    const pid = conversation.projectId;
    if (!pid) continue;
    const bucket = conversationsByProject.get(pid);
    if (bucket) bucket.push(conversation);
    else conversationsByProject.set(pid, [conversation]);
  }

  const openCreateProject = () => {
    setProjectDraft("");
    setProjectDialog({ mode: "create" });
    setCollectionsOpen(true);
  };
  const openRenameProject = (project: ProjectSummary) => {
    setProjectDraft(project.name);
    setProjectDialog({ mode: "rename", id: project.id, name: project.name });
  };
  const submitProjectDialog = () => {
    const trimmed = projectDraft.trim();
    if (!trimmed || !projectDialog) {
      setProjectDialog(null);
      return;
    }
    if (projectDialog.mode === "create") {
      onCreateProject?.(trimmed);
    } else if (trimmed !== projectDialog.name) {
      onRenameProject?.(projectDialog.id, trimmed);
    }
    setProjectDialog(null);
  };
  const confirmProjectDelete = () => {
    if (!pendingProjectDelete) return;
    onDeleteProject?.(pendingProjectDelete.id);
    setPendingProjectDelete(null);
  };

  // Tags (Conversation Org v2): the inline create/rename dialog + the pending
  // tag deletion confirmation, mirroring the project dialogs above.
  const [tagDialog, setTagDialog] = useState<
    { mode: "create" } | { mode: "rename"; id: string; name: string } | null
  >(null);
  const [tagDraft, setTagDraft] = useState("");
  const [pendingTagDelete, setPendingTagDelete] = useState<Tag | null>(null);

  const openCreateTag = () => {
    setTagDraft("");
    setTagDialog({ mode: "create" });
    setCollectionsOpen(true);
  };
  const openRenameTag = (tag: Tag) => {
    setTagDraft(tag.name);
    setTagDialog({ mode: "rename", id: tag.id, name: tag.name });
  };
  const submitTagDialog = () => {
    const trimmed = tagDraft.trim();
    if (!trimmed || !tagDialog) {
      setTagDialog(null);
      return;
    }
    if (tagDialog.mode === "create") {
      onCreateTag?.(trimmed);
    } else if (trimmed !== tagDialog.name) {
      onRenameTag?.(tagDialog.id, trimmed);
    }
    setTagDialog(null);
  };
  const confirmTagDelete = () => {
    if (!pendingTagDelete) return;
    // Deleting the tag we're filtering by clears the filter so the list isn't
    // stuck showing nothing.
    if (activeTagId === pendingTagDelete.id) onSetTagFilter?.(null);
    onDeleteTag?.(pendingTagDelete.id);
    setPendingTagDelete(null);
  };

  // Archived section collapse (Conversation Org v2). Collapsed by default so the
  // main list stays focused; the header toggles it open.
  const [archivedOpen, setArchivedOpen] = useState(false);

  // M3: Collections finder. Projects (containers) and Tags (filters) used to be
  // two always-present labeled sections stacked above the recency list — two
  // parallel organization systems competing for the top of the rail. They now
  // collapse behind ONE quiet "Collections" disclosure that, at rest, leaves the
  // recency-grouped conversations as the figure. Expanding it progressively
  // discloses BOTH systems with their full existing CRUD + the per-tag filter.
  // Collapsed by default. We auto-open it the first time a CRUD dialog is
  // launched (create/rename) so the freshly-created project/tag is visible when
  // the dialog closes; an explicit user toggle thereafter is respected.
  const [collectionsOpen, setCollectionsOpen] = useState(false);
  const hasCollections =
    Boolean(onCreateProject) ||
    projects.length > 0 ||
    Boolean(onCreateTag) ||
    tags.length > 0;
  // The active tag filter must stay VISIBLE even when Collections is collapsed —
  // burying an in-effect filter behind a closed disclosure is a usability
  // regression (a frequent action whose state would otherwise be invisible). We
  // resolve its display name from the live tag set and surface a clearable chip
  // on the collapsed Collections row.
  const activeFilterTag = activeTagFilter
    ? tags.find((t) => t.id === activeTagFilter) ?? null
    : null;

  // Multi-select (Conversation Org v2). Selection state lives here in the
  // sidebar; the bulk action bar calls the parent's optimistic `onBulk*`
  // handlers with the explicit id list, then clears the selection. Entering
  // selection mode is implicit: the first selected id turns it on; clearing the
  // last (or pressing Cancel) turns it off.
  const [rawSelectedIds, setRawSelectedIds] = useState<Set<string>>(new Set());
  // Selection mode is entered EXPLICITLY via the "Select" toggle (so checkboxes
  // appear even before anything is picked — otherwise there'd be no way to start
  // a selection on desktop). It also stays on while anything is selected.
  const [selectionActive, setSelectionActive] = useState(false);
  const bulkEnabled = Boolean(
    onBulkArchive || onBulkDelete || onBulkAddTag || onBulkRemoveTag,
  );
  const bulkInteractable = bulkEnabled && !isSearching && !searchPending;
  // Derive the EFFECTIVE selection by intersecting with the live conversation
  // ids, so an id that vanished (e.g. after a bulk delete) can't keep selection
  // mode alive or skew the count — without a setState-in-effect (lint rule).
  const liveConversationIds = new Set(conversations.map((c) => c.id));
  const selectedIds = new Set(
    Array.from(rawSelectedIds).filter((id) => liveConversationIds.has(id)),
  );
  const selectionMode =
    bulkInteractable && (selectionActive || selectedIds.size > 0);
  const toggleSelect = useCallback((id: string) => {
    setRawSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const exitSelection = useCallback(() => {
    setRawSelectedIds(new Set());
    setSelectionActive(false);
  }, [setSelectionActive]);

  const selectedIdList = Array.from(selectedIds);
  const hasSelection = selectedIdList.length > 0;
  const runBulk = (fn?: (ids: string[]) => void) => {
    if (!fn || selectedIdList.length === 0) return;
    fn(selectedIdList);
    exitSelection();
  };

  const activeRowRef = useRef<HTMLDivElement | null>(null);
  // useLayoutEffect avoids a flash on mobile-drawer open: each drawer mount is a
  // fresh Sidebar instance, so the active row is pulled into view before paint.
  useLayoutEffect(() => {
    if (!activeId) return;
    const node = activeRowRef.current;
    if (!node) return;
    node.scrollIntoView({
      block: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
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
          projects={projects}
          tags={tags}
          selectionMode={selectionMode}
          selected={selectedIds.has(conversation.id)}
          onToggleSelect={toggleSelect}
          onSelect={onSelect}
          onRename={onRenameConversation}
          onTogglePin={onTogglePinConversation}
          onSetRetention={onSetConversationRetention}
          onAssignProject={onAssignConversationToProject}
          onAssignTags={onAssignConversationTags}
          onArchive={onArchiveConversation}
          onCopy={onCopyConversation}
          onDownload={onDownloadConversation}
          onRequestDelete={setPendingDelete}
          bulkEnabled={bulkInteractable}
          onEnterSelection={() => setSelectionActive(true)}
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
      <div className="flex h-16 shrink-0 items-center justify-between px-3">
        <div className="flex items-center">
          {/* Wordmark demoted to a quiet label (anti-pattern G: personality
              must not stand on the working surface for the life of the session).
              Distinctiveness lives in the empty/welcome state, not here — so the
              brand recedes to a small, muted, normal-weight cap-tracked label
              that reads as orientation, not as a logo asking to be looked at. */}
          <span className="text-xs font-normal uppercase tracking-wide text-muted-foreground">
            Olune
          </span>
        </div>
        {onCollapse ? (
          <Button
            type="button"
            variant="ghost"
            aria-label={t("sidebar.collapse")}
            onClick={onCollapse}
            className="size-11 rounded-full p-0 text-muted-foreground transition-colors hover:text-foreground md:size-9"
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
          <span>{t("sidebar.newChat")}</span>
        </button>
      </div>

      {/* Search + list-management toolbar region. The quick-search input and
          New-chat row above are primary and always paint; the low-frequency
          management affordances inside this region (Advanced search, Select)
          are desktop-only and hover/focus-revealed so the rail quiets at rest.
          On touch the mobile drawer stays minimal — Cmd+K covers advanced
          search and the per-row overflow menu covers selection. `group/toolbar`
          scopes the reveal to this region (not the whole sidebar). */}
      <div className="group/toolbar">
      <div className="px-2 pb-2">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <input
            type="search"
            value={search}
            onChange={(e) => {
              const nextSearch = e.target.value;
              if (nextSearch.trim().length > 0) exitSelection();
              onSearchChange(nextSearch);
            }}
            placeholder="Search conversations"
            aria-label="Search conversations"
            className={cn(
              // text-base on mobile keeps iOS Safari from auto-zooming on focus.
              "block h-11 w-full rounded-full bg-muted/50 pl-8 text-base text-foreground placeholder:text-muted-foreground outline-none focus-visible:shadow-[var(--focus-ring)] md:text-sm",
              search.length > 0 ? "pr-12" : "pr-3",
            )}
          />
          {search.length > 0 ? (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => onSearchChange("")}
              className="absolute right-0 top-1/2 inline-flex size-11 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none md:right-1 md:size-9"
            >
              <X aria-hidden className="size-3.5" />
            </button>
          ) : null}
        </div>
        {/* Advanced search opens the filter-rich dialog (model / cost / date /
            project / tag) — the inline box stays a quick title/snippet search. */}
        {onOpenAdvancedSearch ? (
          <button
            type="button"
            onClick={onOpenAdvancedSearch}
            data-testid="sidebar-advanced-search"
            className={cn(
              "mt-1 hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-muted-foreground outline-none transition-[color,opacity] motion-reduce:transition-none hover:text-foreground focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none md:inline-flex",
              // Desktop-only: hover/focus-reveal pattern keeps the rail quiet at
              // rest. Mobile users reach advanced search via Cmd+K instead.
              "md:opacity-0 md:group-hover/toolbar:opacity-100 md:focus-within:opacity-100 md:focus-visible:opacity-100",
            )}
          >
            <SlidersHorizontal aria-hidden className="size-3" />
            <span>Advanced search</span>
          </button>
        ) : null}
      </div>

      {/* Select toggle (Conversation Org v2). Entry point into multi-select; the
          per-row checkboxes only render once selection mode is on. Hidden while
          searching and once selection mode is already active (the bulk bar's
          Cancel exits). */}
      {bulkInteractable && !selectionMode ? (
        <div className="px-2 pb-2">
          <button
            type="button"
            onClick={() => setSelectionActive(true)}
            data-testid="sidebar-select-toggle"
            className={cn(
              "hidden min-h-9 w-full select-none items-center gap-2 rounded-2xl px-3 py-1.5 text-left text-xs font-medium text-muted-foreground outline-none transition-[color,background-color,opacity] motion-reduce:transition-none hover:bg-muted/60 hover:text-foreground focus-visible:shadow-[var(--focus-ring)] md:flex",
              // Desktop-only: hover/focus-reveal pattern keeps the rail quiet at
              // rest. Mobile users use the conversation row's overflow menu.
              "md:opacity-0 md:group-hover/toolbar:opacity-100 md:focus-within:opacity-100 md:focus-visible:opacity-100",
            )}
          >
            <Check className="size-3.5" aria-hidden />
            <span>Select</span>
          </button>
        </div>
      ) : null}
      </div>{/* /group/toolbar */}

      {/* Bulk action bar (Conversation Org v2). Shown in selection mode.
          Archive / unarchive / delete + an "Add tag" submenu over the user's
          tags; Cancel exits selection. */}
      {selectionMode ? (
        <div
          className="mx-2 mb-2 flex items-center gap-1 rounded-2xl bg-muted/60 px-2 py-1.5"
          data-testid="sidebar-bulk-bar"
        >
          <span
            className="px-1 text-xs font-medium text-foreground"
            data-testid="sidebar-bulk-count"
          >
            {selectedIds.size} selected
          </span>
          <div className="ml-auto flex items-center gap-0.5">
            {onBulkArchive ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label="Archive selected"
                  data-testid="sidebar-bulk-archive"
                  disabled={!hasSelection}
                  onClick={() => runBulk((ids) => onBulkArchive(ids, true))}
                  className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-8"
                >
                  <Archive className="size-4" aria-hidden />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label="Unarchive selected"
                  data-testid="sidebar-bulk-unarchive"
                  disabled={!hasSelection}
                  onClick={() => runBulk((ids) => onBulkArchive(ids, false))}
                  className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-8"
                >
                  <ArchiveRestore className="size-4" aria-hidden />
                </Button>
              </>
            ) : null}
            {(onBulkAddTag || onBulkRemoveTag) && tags.length > 0 ? (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      type="button"
                      variant="ghost"
                      aria-label="Tag selected"
                      data-testid="sidebar-bulk-tag"
                      disabled={!hasSelection}
                      className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-8"
                    >
                      <Tags className="size-4" aria-hidden />
                    </Button>
                  }
                />
                <DropdownMenuContent align="end" className="w-48">
                  {onBulkAddTag ? (
                    <DropdownMenuSub>
                      <DropdownMenuSubTrigger
                        className="gap-2"
                        data-testid="sidebar-bulk-add-tag"
                      >
                        <TagIcon className="size-4" aria-hidden />
                        <span>Add tag</span>
                      </DropdownMenuSubTrigger>
                      <DropdownMenuSubContent>
                        {tags.map((tag) => (
                          <DropdownMenuItem
                            key={tag.id}
                            label={tag.name}
                            onClick={() =>
                              runBulk((ids) => onBulkAddTag(ids, tag.id))
                            }
                            className="gap-2"
                          >
                            <span className="min-w-0 flex-1 truncate">
                              {tag.name}
                            </span>
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuSubContent>
                    </DropdownMenuSub>
                  ) : null}
                  {onBulkRemoveTag ? (
                    <DropdownMenuSub>
                      <DropdownMenuSubTrigger
                        className="gap-2"
                        data-testid="sidebar-bulk-remove-tag"
                      >
                        <TagIcon className="size-4" aria-hidden />
                        <span>Remove tag</span>
                      </DropdownMenuSubTrigger>
                      <DropdownMenuSubContent>
                        {tags.map((tag) => (
                          <DropdownMenuItem
                            key={tag.id}
                            label={tag.name}
                            onClick={() =>
                              runBulk((ids) => onBulkRemoveTag(ids, tag.id))
                            }
                            className="gap-2"
                          >
                            <span className="min-w-0 flex-1 truncate">
                              {tag.name}
                            </span>
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuSubContent>
                    </DropdownMenuSub>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            {onBulkDelete ? (
              <Button
                type="button"
                variant="ghost"
                aria-label="Delete selected"
                data-testid="sidebar-bulk-delete"
                disabled={!hasSelection}
                onClick={() => runBulk(onBulkDelete)}
                className="size-11 rounded-full p-0 text-destructive hover:text-destructive md:size-8"
              >
                <Trash2 className="size-4" aria-hidden />
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              aria-label="Cancel selection"
              data-testid="sidebar-bulk-cancel"
              onClick={exitSelection}
              className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-8"
            >
              <X className="size-4" aria-hidden />
            </Button>
          </div>
        </div>
      ) : null}

      <ScrollArea className="min-h-0 flex-1">
        <div
          className="px-2 pb-2"
          aria-busy={isSearching && searchPending ? true : undefined}
        >
          {isSearching ? (
            filteredConversations.length === 0 ? (
              <div className="px-2 py-6 text-center text-sm text-muted-foreground">
                {searchPending ? "Searching…" : "No matches"}
              </div>
            ) : (
              <div role="list" aria-label="Search results">
                {filteredConversations.map(renderRow)}
              </div>
            )
          ) : (
            <>
              {/* M3: Collections finder. ONE quiet disclosure replaces the two
                  always-present "Projects" + "Tags" sections. At rest the rail
                  shows only the recency list + this single collapsed entry; the
                  active tag filter (a FREQUENT action) stays visible as a
                  clearable chip on the collapsed row so an in-effect filter is
                  never buried. Expanding discloses BOTH organization systems
                  with their full CRUD and the per-tag filter, one interaction
                  deep. */}
              {displayConversations.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
                  <MessageSquare
                    aria-hidden
                    className="size-8 text-muted-foreground/50"
                  />
                  <p className="text-sm font-medium text-foreground/80">
                    No chats yet
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Type a message below to start
                  </p>
                </div>
              ) : null}
              {hasCollections ? (
                <div className="mb-6" data-testid="sidebar-collections">
                  <div className="group/collections-head flex items-center gap-1 px-2 pb-1 pt-1">
                    <button
                      type="button"
                      onClick={() => setCollectionsOpen((v) => !v)}
                      aria-expanded={collectionsOpen}
                      aria-controls="sidebar-collections-panel"
                      data-testid="sidebar-collections-toggle"
                      className="flex min-h-9 min-w-0 flex-1 items-center gap-1.5 rounded-lg px-1 py-1 text-left text-xs font-semibold text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)]"
                    >
                      {collectionsOpen ? (
                        <ChevronDown className="size-3.5 shrink-0" aria-hidden />
                      ) : (
                        <ChevronRight className="size-3.5 shrink-0" aria-hidden />
                      )}
                      <Boxes className="size-3.5 shrink-0" aria-hidden />
                      <span>Collections</span>
                      {/* Active-filter visibility while collapsed: the filtered
                          tag's name rides on the collapsed row so the user can
                          see (and the chip's × can clear) the in-effect filter
                          without expanding. Hidden when expanded — the live
                          per-tag toggle below carries the state then. */}
                      {!collectionsOpen && activeFilterTag ? (
                        <span
                          className="ml-1 inline-flex min-w-0 items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-2xs font-medium text-foreground"
                          data-testid="sidebar-collections-active-filter"
                        >
                          <TagIcon
                            className="size-3 shrink-0"
                            aria-hidden
                            style={
                              activeFilterTag.color
                                ? { color: activeFilterTag.color }
                                : undefined
                            }
                          />
                          <span className="min-w-0 max-w-[8rem] truncate">
                            {activeFilterTag.name}
                          </span>
                        </span>
                      ) : null}
                    </button>
                    {/* Clearing an active filter from the collapsed row stays a
                        ONE-interaction reach for the frequent un-filter case. */}
                    {!collectionsOpen && activeFilterTag ? (
                      <Button
                        type="button"
                        variant="ghost"
                        aria-label={`Clear ${activeFilterTag.name} filter`}
                        data-testid="sidebar-collections-clear-filter"
                        onClick={() => onSetTagFilter?.(null)}
                        className="size-11 shrink-0 rounded-full p-0 text-muted-foreground transition-colors hover:text-foreground md:size-7"
                      >
                        <X className="size-4" aria-hidden />
                      </Button>
                    ) : null}
                  </div>
                  {collectionsOpen ? (
                    <div id="sidebar-collections-panel">
                      {/* Projects/Spaces (D20). Each project is a labeled
                  container with its filed conversations and a kebab to manage
                  settings / rename / delete. */}
              {onCreateProject || projects.length > 0 ? (
                <div className="mb-4" data-testid="sidebar-projects">
                  <div className="group/proj-head flex items-center justify-between px-2 pb-1 pt-1">
                    <span className="text-xs font-semibold text-muted-foreground">
                      Projects
                    </span>
                    {onCreateProject ? (
                      <Button
                        type="button"
                        variant="ghost"
                        aria-label="New project"
                        data-testid="sidebar-new-project"
                        onClick={openCreateProject}
                        className={cn(
                          "size-11 rounded-full p-0 text-muted-foreground transition-[color,opacity] motion-reduce:transition-none hover:text-foreground md:size-7",
                          // Persistent on touch; hover/focus-revealed on desktop
                          // (reveals on hover of the section header row). Stays
                          // mounted (opacity only) so it's clickable + e2e-safe.
                          "opacity-100 md:opacity-0 md:group-hover/proj-head:opacity-100 md:focus-within:opacity-100 md:focus-visible:opacity-100",
                        )}
                      >
                        <FolderPlus className="size-4" aria-hidden />
                      </Button>
                    ) : null}
                  </div>
                  {projects.length === 0 ? (
                    <div className="px-2 py-2 text-xs text-muted-foreground">
                      No projects yet
                    </div>
                  ) : (
                    projects.map((project) => {
                      const filed =
                        conversationsByProject.get(project.id) ?? [];
                      return (
                        <div
                          key={project.id}
                          className="mb-2"
                          data-testid="sidebar-project"
                        >
                          <div className="group/proj flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-sidebar-foreground hover:bg-muted/60">
                            <Folder
                              className="size-4 shrink-0 text-muted-foreground"
                              aria-hidden
                            />
                            <span
                              className="min-w-0 flex-1 truncate font-medium"
                              data-testid="sidebar-project-name"
                            >
                              {project.name}
                            </span>
                            <span className="shrink-0 text-xs text-muted-foreground">
                              {filed.length}
                            </span>
                            <DropdownMenu>
                              <DropdownMenuTrigger
                                render={
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    aria-label="Project actions"
                                    onClick={(e) => e.stopPropagation()}
                                    className="size-11 shrink-0 rounded-full p-0 text-muted-foreground opacity-100 transition-opacity hover:text-foreground md:size-7 md:opacity-0 md:group-hover/proj:opacity-100 md:aria-expanded:opacity-100"
                                  >
                                    <MoreHorizontal
                                      className="size-4"
                                      aria-hidden
                                    />
                                  </Button>
                                }
                              />
                              <DropdownMenuContent align="end" className="w-44">
                                {onManageProjects ? (
                                  <DropdownMenuItem
                                    label="Project settings"
                                    onClick={onManageProjects}
                                    className="gap-2"
                                  >
                                    <Settings className="size-4" aria-hidden />
                                    <span>Project settings</span>
                                  </DropdownMenuItem>
                                ) : null}
                                {onRenameProject ? (
                                  <DropdownMenuItem
                                    label="Rename project"
                                    onClick={() => openRenameProject(project)}
                                    className="gap-2"
                                  >
                                    <Pencil className="size-4" aria-hidden />
                                    <span>Rename</span>
                                  </DropdownMenuItem>
                                ) : null}
                                {onDeleteProject ? (
                                  <DropdownMenuItem
                                    label="Delete project"
                                    variant="destructive"
                                    onClick={() =>
                                      setPendingProjectDelete(project)
                                    }
                                    className="gap-2"
                                  >
                                    <Trash2 className="size-4" aria-hidden />
                                    <span>Delete</span>
                                  </DropdownMenuItem>
                                ) : null}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                          {filed.length > 0 ? (
                            <div
                              role="list"
                              aria-label={`${project.name} conversations`}
                              className="ml-2 border-l border-border/60 pl-1"
                            >
                              {filed.map(renderRow)}
                            </div>
                          ) : null}
                        </div>
                      );
                    })
                  )}
                </div>
              ) : null}
              {/* Tags (Conversation Org v2). A labeled, filterable label set:
                  click a tag to filter the list to it; the kebab renames /
                  deletes it; the header "+" creates one. */}
              {onCreateTag || tags.length > 0 ? (
                <div className="mb-6" data-testid="sidebar-tags">
                  <div className="group/tags-head flex items-center justify-between px-2 pb-1 pt-1">
                    <span className="text-xs font-semibold text-muted-foreground">
                      Tags
                    </span>
                    {onCreateTag ? (
                      <Button
                        type="button"
                        variant="ghost"
                        aria-label="New tag"
                        data-testid="sidebar-new-tag"
                        onClick={openCreateTag}
                        className={cn(
                          "size-11 rounded-full p-0 text-muted-foreground transition-[color,opacity] motion-reduce:transition-none hover:text-foreground md:size-7",
                          // Persistent on touch; hover/focus-revealed on desktop
                          // (reveals on hover of the section header row). Stays
                          // mounted (opacity only) so it's clickable + e2e-safe.
                          "opacity-100 md:opacity-0 md:group-hover/tags-head:opacity-100 md:focus-within:opacity-100 md:focus-visible:opacity-100",
                        )}
                      >
                        <Plus className="size-4" aria-hidden />
                      </Button>
                    ) : null}
                  </div>
                  {tags.length === 0 ? (
                    <div className="px-2 py-2 text-xs text-muted-foreground">
                      No tags yet
                    </div>
                  ) : (
                    <div className="flex flex-col gap-0.5">
                      {tags.map((tag) => {
                        const isActiveFilter = activeTagFilter === tag.id;
                        return (
                          <div
                            key={tag.id}
                            className="group/tag flex items-center gap-1 rounded-lg px-1"
                            data-testid="sidebar-tag"
                          >
                            <button
                              type="button"
                              // Click toggles the filter: clicking the active
                              // tag clears it (shows all again).
                              onClick={() =>
                                onSetTagFilter?.(isActiveFilter ? null : tag.id)
                              }
                              aria-pressed={isActiveFilter}
                              data-testid="sidebar-tag-filter"
                              className={cn(
                                "flex min-h-9 min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1 text-left text-sm outline-none transition-colors hover:bg-muted/60 focus-visible:shadow-[var(--focus-ring)]",
                                isActiveFilter
                                  ? "text-foreground"
                                  : "text-sidebar-foreground",
                              )}
                            >
                              <TagIcon
                                className="size-3.5 shrink-0"
                                aria-hidden
                                style={
                                  tag.color ? { color: tag.color } : undefined
                                }
                              />
                              <span
                                className="min-w-0 flex-1 truncate"
                                data-testid="sidebar-tag-name"
                              >
                                {tag.name}
                              </span>
                              {isActiveFilter ? (
                                <Check
                                  className="size-3.5 shrink-0 text-brand"
                                  aria-hidden
                                />
                              ) : null}
                            </button>
                            {onRenameTag || onDeleteTag ? (
                              <DropdownMenu>
                                <DropdownMenuTrigger
                                  render={
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      aria-label="Tag actions"
                                      onClick={(e) => e.stopPropagation()}
                                      className="size-11 shrink-0 rounded-full p-0 text-muted-foreground opacity-100 transition-opacity hover:text-foreground md:size-7 md:opacity-0 md:group-hover/tag:opacity-100 md:aria-expanded:opacity-100"
                                    >
                                      <MoreHorizontal
                                        className="size-4"
                                        aria-hidden
                                      />
                                    </Button>
                                  }
                                />
                                <DropdownMenuContent
                                  align="end"
                                  className="w-40"
                                >
                                  {onRenameTag ? (
                                    <DropdownMenuItem
                                      label="Rename tag"
                                      onClick={() => openRenameTag(tag)}
                                      className="gap-2"
                                      data-testid="sidebar-tag-rename"
                                    >
                                      <Pencil className="size-4" aria-hidden />
                                      <span>Rename</span>
                                    </DropdownMenuItem>
                                  ) : null}
                                  {onDeleteTag ? (
                                    <DropdownMenuItem
                                      label="Delete tag"
                                      variant="destructive"
                                      onClick={() => setPendingTagDelete(tag)}
                                      className="gap-2"
                                      data-testid="sidebar-tag-delete"
                                    >
                                      <Trash2 className="size-4" aria-hidden />
                                      <span>Delete</span>
                                    </DropdownMenuItem>
                                  ) : null}
                                </DropdownMenuContent>
                              </DropdownMenu>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {/* Recency-grouped conversations stay the figure at rest: they
                  render OUTSIDE the Collections disclosure (as its sibling), so
                  collapsing Collections never hides the conversation list. */}
              {displayConversations.length === 0 ? null : recencyConversations.length === 0 &&
                archivedConversations.length === 0 ? (
                activeTagFilter ? (
                  <div className="px-2 py-6 text-center text-sm text-muted-foreground">
                    No conversations with this tag
                  </div>
                ) : null
              ) : (
                <>
                  {GROUP_ORDER.map((key) => {
                    const items = groups.get(key);
                    if (!items || items.length === 0) {
                      return null;
                    }
                    return (
                      // Ma: tripled inter-group gutter so the recency label
                      // gains weight from surrounding silence, not size/color.
                      <div key={key} className="mb-6">
                        <div className="px-2 pb-2 pt-1 text-xs font-semibold text-muted-foreground">
                          {RECENCY_LABELS[key]}
                        </div>
                        <div role="list" aria-label={RECENCY_LABELS[key]}>
                          {items.map(renderRow)}
                        </div>
                      </div>
                    );
                  })}
                  {/* Archived (Conversation Org v2): a collapsible section below
                      the recency groups. Excluded from the recency buckets. */}
                  {archivedConversations.length > 0 ? (
                    <div className="mb-6" data-testid="sidebar-archived">
                      <button
                        type="button"
                        onClick={() => setArchivedOpen((v) => !v)}
                        aria-expanded={archivedOpen}
                        data-testid="sidebar-archived-toggle"
                        className="flex w-full items-center gap-1 rounded-lg px-2 pb-2 pt-1 text-left text-xs font-semibold text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)]"
                      >
                        {archivedOpen ? (
                          <ChevronDown className="size-3.5" aria-hidden />
                        ) : (
                          <ChevronRight className="size-3.5" aria-hidden />
                        )}
                        <span>Archived</span>
                        <span className="ml-1 font-normal">
                          {archivedConversations.length}
                        </span>
                      </button>
                      {archivedOpen ? (
                        <div role="list" aria-label="Archived conversations">
                          {archivedConversations.map(renderRow)}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </>
              )}
            </>
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
                className="flex min-h-11 w-full select-none items-center gap-2 rounded-2xl p-2 text-left outline-none transition-[transform,background-color] duration-100 touch-manipulation hover:bg-muted/60 focus-visible:shadow-[var(--focus-ring)] aria-expanded:bg-muted/60 active:not-aria-[haspopup]:scale-[0.97]"
              >
                <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground">
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
            {onOpenAdvancedSearch ? (
              <DropdownMenuItem
                label="Advanced search"
                onClick={onOpenAdvancedSearch}
                className="gap-2 md:hidden"
                data-testid="sidebar-advanced-search-mobile"
              >
                <SlidersHorizontal className="size-4" aria-hidden />
                <span>Advanced search</span>
              </DropdownMenuItem>
            ) : null}
            {bulkEnabled && !selectionMode && !isSearching ? (
              <DropdownMenuItem
                label="Select conversations"
                onClick={() => setSelectionActive(true)}
                className="gap-2 md:hidden"
                data-testid="sidebar-select-mobile"
              >
                <Check className="size-4" aria-hidden />
                <span>Select conversations</span>
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
              className="h-11 rounded-full bg-destructive px-6 text-destructive-foreground hover:bg-destructive/90 dark:bg-destructive dark:text-destructive-foreground dark:hover:bg-destructive/90"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Project create / rename prompt (D20). */}
      <Dialog
        open={projectDialog !== null}
        onOpenChange={(next) => {
          if (!next) setProjectDialog(null);
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>
              {projectDialog?.mode === "rename" ? "Rename project" : "New project"}
            </DialogTitle>
            <DialogDescription>
              Projects group conversations and scope shared defaults.
            </DialogDescription>
          </DialogHeader>
          <input
            type="text"
            value={projectDraft}
            placeholder="Project name"
            aria-label="Project name"
            data-testid="sidebar-project-name-input"
            autoFocus
            maxLength={200}
            onChange={(event) => setProjectDraft(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submitProjectDialog();
              }
            }}
            // text-base on mobile keeps iOS Safari from auto-zooming on focus.
            className="h-9 w-full rounded-xl border border-border/70 bg-background/70 px-3 text-base text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25 md:text-sm"
          />
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setProjectDialog(null)}
              className="h-11 rounded-full px-6"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={submitProjectDialog}
              disabled={projectDraft.trim().length === 0}
              data-testid="sidebar-project-save"
              className="h-11 rounded-full px-6"
            >
              {projectDialog?.mode === "rename" ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Project delete confirmation (D20). Un-files conversations, never deletes
          them — the copy makes that explicit. */}
      <Dialog
        open={pendingProjectDelete !== null}
        onOpenChange={(next) => {
          if (!next) setPendingProjectDelete(null);
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Delete project?</DialogTitle>
            <DialogDescription>
              {pendingProjectDelete
                ? `This deletes "${pendingProjectDelete.name}". Its conversations are kept and moved out of the project.`
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPendingProjectDelete(null)}
              className="h-11 rounded-full px-6"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmProjectDelete}
              data-testid="sidebar-project-delete-confirm"
              className="h-11 rounded-full bg-destructive px-6 text-destructive-foreground hover:bg-destructive/90 dark:bg-destructive dark:text-destructive-foreground dark:hover:bg-destructive/90"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tag create / rename prompt (Conversation Org v2). */}
      <Dialog
        open={tagDialog !== null}
        onOpenChange={(next) => {
          if (!next) setTagDialog(null);
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>
              {tagDialog?.mode === "rename" ? "Rename tag" : "New tag"}
            </DialogTitle>
            <DialogDescription>
              Tags label conversations so you can filter the sidebar by them.
            </DialogDescription>
          </DialogHeader>
          <input
            type="text"
            value={tagDraft}
            placeholder="Tag name"
            aria-label="Tag name"
            data-testid="sidebar-tag-name-input"
            autoFocus
            maxLength={100}
            onChange={(event) => setTagDraft(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submitTagDialog();
              }
            }}
            // text-base on mobile keeps iOS Safari from auto-zooming on focus.
            className="h-9 w-full rounded-xl border border-border/70 bg-background/70 px-3 text-base text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/25 md:text-sm"
          />
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setTagDialog(null)}
              className="h-11 rounded-full px-6"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={submitTagDialog}
              disabled={tagDraft.trim().length === 0}
              data-testid="sidebar-tag-save"
              className="h-11 rounded-full px-6"
            >
              {tagDialog?.mode === "rename" ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tag delete confirmation (Conversation Org v2). Removes the label from
          every conversation; the conversations themselves are kept. */}
      <Dialog
        open={pendingTagDelete !== null}
        onOpenChange={(next) => {
          if (!next) setPendingTagDelete(null);
        }}
      >
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>Delete tag?</DialogTitle>
            <DialogDescription>
              {pendingTagDelete
                ? `This deletes "${pendingTagDelete.name}" and removes it from all conversations. The conversations are kept.`
                : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPendingTagDelete(null)}
              className="h-11 rounded-full px-6"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmTagDelete}
              data-testid="sidebar-tag-delete-confirm"
              className="h-11 rounded-full bg-destructive px-6 text-destructive-foreground hover:bg-destructive/90 dark:bg-destructive dark:text-destructive-foreground dark:hover:bg-destructive/90"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </nav>
  );
}
