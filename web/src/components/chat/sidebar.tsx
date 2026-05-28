"use client";

import { Key, PanelLeftClose, Pin, Plus, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { AccountInfo, ConversationSummary } from "@/lib/types";

export interface SidebarProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  account: AccountInfo;
  onSelect: (id: string) => void;
  onNewChat: () => void;
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

function ConversationButton({
  conversation,
  active,
  onSelect,
}: {
  conversation: ConversationSummary;
  active: boolean;
  onSelect: (id: string) => void;
}): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={() => onSelect(conversation.id)}
      aria-label={`${conversation.title}${conversation.pinned ? ", pinned" : ""}`}
      // iOS-style pill row: generous rounded-2xl, no border/underline/accent
      // bar, selected row uses bg-muted, hover uses bg-muted/60. The selected
      // state reads through the fill alone — quieter than the prior accent.
      className={cn(
        "flex min-h-10 w-full items-center gap-2 rounded-2xl px-3 py-2 text-left text-sm outline-none transition-colors focus-visible:shadow-[var(--focus-ring)]",
        active
          ? "bg-muted text-foreground"
          : "text-sidebar-foreground hover:bg-muted/60",
      )}
    >
      {conversation.pinned ? (
        <Pin className="size-3 shrink-0 text-muted-foreground" aria-hidden />
      ) : null}
      <span className="min-w-0 flex-1 truncate">{conversation.title}</span>
    </button>
  );
}

export function Sidebar({
  conversations,
  activeId,
  account,
  onSelect,
  onNewChat,
  onOpenSettings,
  onCollapse,
  className,
}: SidebarProps): React.JSX.Element {
  const groups = groupConversations(conversations);

  return (
    <nav
      aria-label="Conversation history"
      className={cn(
        "flex h-full flex-col bg-sidebar text-sidebar-foreground",
        className
      )}
    >
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-lg bg-brand text-sm font-bold text-brand-foreground">
            O
          </div>
          <span className="text-sm font-semibold">Olune</span>
        </div>
        {onCollapse ? (
          <Button
            type="button"
            variant="ghost"
            aria-label="Collapse sidebar"
            onClick={onCollapse}
            // Matches the floating chrome vocabulary used in app-header so the
            // sidebar feels like part of the same iOS-style surface.
            className="size-9 rounded-full border-0 bg-card p-0 text-muted-foreground shadow-float transition-colors hover:bg-card hover:text-foreground"
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

      <ScrollArea className="min-h-0 flex-1">
        <div className="px-2 pb-2">
          {GROUP_ORDER.map((key) => {
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
                  {items.map((conversation) => (
                    <div role="listitem" key={conversation.id}>
                      <ConversationButton
                        conversation={conversation}
                        active={conversation.id === activeId}
                        onSelect={onSelect}
                      />
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
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
    </nav>
  );
}
