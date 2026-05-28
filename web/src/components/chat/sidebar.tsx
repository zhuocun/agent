"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import {
  Key,
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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { AccountInfo, ConversationSummary } from "@/lib/types";

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
  onOpenSettings: () => void;
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
  onRequestDelete,
}: {
  conversation: ConversationSummary;
  active: boolean;
  activeRowRef?: React.RefObject<HTMLDivElement | null>;
  onSelect: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onTogglePin: (id: string) => void;
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

  const handleRowClick = () => {
    onSelect(conversation.id);
  };

  const stopBubble = (e: ReactMouseEvent) => {
    e.stopPropagation();
  };

  return (
    <div
      ref={active ? activeRowRef : undefined}
      className={cn(
        "group/conv relative flex min-h-10 w-full items-center rounded-2xl pr-1 text-left text-sm transition-colors",
        active
          ? "bg-muted text-foreground"
          : "text-sidebar-foreground hover:bg-muted/60",
      )}
    >
      {isRenaming ? (
        // Inline-rename mode renders as a sibling subtree, NOT nested in the
        // click-to-select button. <button> cannot contain interactive
        // descendants (invalid HTML; some browsers prevent the input from
        // receiving keyboard focus and click-through can occur). Mirrors the
        // edit pattern in user-message.tsx.
        <div className="flex min-h-10 min-w-0 flex-1 items-center gap-2 rounded-2xl px-3 py-2">
          {conversation.pinned ? (
            <Pin className="size-3 shrink-0 text-muted-foreground" aria-hidden />
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
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none focus-visible:shadow-[var(--focus-ring)] rounded-sm"
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={handleRowClick}
          aria-label={`${conversation.title}${conversation.pinned ? ", pinned" : ""}`}
          aria-current={active ? "true" : undefined}
          className="flex min-h-10 min-w-0 flex-1 items-center gap-2 rounded-2xl px-3 py-2 text-left outline-none focus-visible:shadow-[var(--focus-ring)]"
        >
          {conversation.pinned ? (
            <Pin className="size-3 shrink-0 text-muted-foreground" aria-hidden />
          ) : null}
          <span className="min-w-0 flex-1 truncate">{conversation.title}</span>
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
                "size-7 shrink-0 rounded-full p-0 text-muted-foreground transition-opacity hover:text-foreground",
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
            label={conversation.pinned ? "Unpin" : "Pin"}
            onClick={() => onTogglePin(conversation.id)}
            className="gap-2"
          >
            {conversation.pinned ? (
              <PinOff className="size-4" aria-hidden />
            ) : (
              <Pin className="size-4" aria-hidden />
            )}
            <span>{conversation.pinned ? "Unpin" : "Pin"}</span>
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
  );
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
  onOpenSettings,
  onCollapse,
  className,
}: SidebarProps): React.JSX.Element {
  const trimmedSearch = search.trim();
  const isSearching = trimmedSearch.length > 0;
  const filteredConversations = isSearching
    ? conversations.filter((c) =>
        c.title.toLowerCase().includes(trimmedSearch.toLowerCase()),
      )
    : conversations;
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

  const renderRow = (conversation: ConversationSummary) => (
    <div role="listitem" key={conversation.id}>
      <ConversationRow
        conversation={conversation}
        active={conversation.id === activeId}
        activeRowRef={activeRowRef}
        onSelect={onSelect}
        onRename={onRenameConversation}
        onTogglePin={onTogglePinConversation}
        onRequestDelete={setPendingDelete}
      />
    </div>
  );

  return (
    <nav
      aria-label="Conversation history"
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
          className="flex min-h-10 w-full items-center gap-2 rounded-2xl px-3 py-2 text-left text-sm font-medium text-sidebar-foreground outline-none transition-colors hover:bg-muted/60 focus-visible:shadow-[var(--focus-ring)]"
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
            placeholder="Search"
            aria-label="Search conversations"
            className="block w-full rounded-full bg-muted/50 py-1.5 pl-8 pr-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus-visible:shadow-[var(--focus-ring)]"
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
                <div key={key} className="mb-1">
                  <div className="px-2 py-1 text-xs font-medium text-muted-foreground">
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
        <button
          type="button"
          onClick={onOpenSettings}
          aria-label="Open settings"
          className="flex w-full items-center gap-2 rounded-2xl p-2 text-left outline-none transition-colors hover:bg-muted/60 focus-visible:shadow-[var(--focus-ring)]"
        >
          <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground">
            {initials(account.name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{account.name}</div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <span className="truncate">{account.planLabel}</span>
              {account.byokEnabled ? (
                <Key className="size-3 shrink-0" aria-hidden />
              ) : null}
            </div>
          </div>
          <Settings className="ml-auto size-4 shrink-0 text-muted-foreground" aria-hidden />
        </button>
      </div>

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(next) => {
          if (!next) setPendingDelete(null);
        }}
      >
        <DialogContent className="max-w-sm">
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
              className="rounded-full"
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={confirmDelete}
              className="rounded-full"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </nav>
  );
}
