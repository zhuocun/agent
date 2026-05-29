"use client";

import { useEffect, useId, useMemo, useRef, useState, type JSX } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { MessageSquare, Search, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { useSwipeDismiss } from "@/lib/use-swipe-dismiss";
import { KeyCaps } from "@/components/chat/key-caps";
import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";
import type { ConversationSummary } from "@/lib/types";

// A palette action — one of the global handlers exposed to the keyboard layer
// AND surfaced as a row inside the palette. `shortcut` is the descriptor used
// to render the right-aligned key-cap hint.
export interface CommandAction {
  id: string;
  label: string;
  icon?: LucideIcon;
  shortcut?: ShortcutKeys;
  section: "Actions" | "Settings";
  run: () => void;
}

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: CommandAction[];
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelectConversation: (id: string) => void;
}

// Flat list item — either an action or a conversation. The list is rendered
// as a single ARIA listbox; the section labels are visual headings (not
// listbox children) and are skipped when computing keyboard indices.
type Item =
  | { kind: "action"; section: "Actions" | "Settings"; action: CommandAction; flatIndex: number }
  | { kind: "conversation"; conversation: ConversationSummary; isActive: boolean; flatIndex: number };

// Cap for the "Recent" section when there's no query. Searching a non-empty
// query spans all conversations per PRD §4.9.
const RECENT_CAP = 5;

function buildItems(
  query: string,
  actions: CommandAction[],
  conversations: ConversationSummary[],
  activeId: string | null,
): { sections: { heading: string; items: Item[] }[]; flat: Item[] } {
  const q = query.trim().toLowerCase();
  const match = (s: string): boolean => (q ? s.toLowerCase().includes(q) : true);

  const actionItems = actions.filter((a) => match(a.label));

  // Newest first. Sort a copy so the parent's array stays untouched.
  const sortedConversations = [...conversations].sort((a, b) =>
    a.updatedAt < b.updatedAt ? 1 : a.updatedAt > b.updatedAt ? -1 : 0,
  );
  const filteredConversations = sortedConversations.filter((c) =>
    match(c.title),
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
}: CommandPaletteProps): JSX.Element {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isMobile, setIsMobile] = useState(false);
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

  const { sheetRef, handleProps, contentProps } = useSwipeDismiss({
    enabled: isMobile,
    onDismiss: () => handleOpenChangeRef.current(false),
  });

  const { sections, flat } = useMemo(
    () => buildItems(query, actions, conversations, activeId),
    [query, actions, conversations, activeId],
  );

  const clampedIndex =
    flat.length === 0 ? 0 : Math.min(selectedIndex, flat.length - 1);

  const activeOptionId =
    flat.length > 0 ? `${optionIdPrefix}-${clampedIndex}` : undefined;

  // Closing the palette clears search + selection — done here (event-driven)
  // rather than in an effect to avoid the cascading-render lint.
  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setQuery("");
      setSelectedIndex(0);
    }
    onOpenChange(next);
  };

  // Keep a stable ref so the swipe hook's onDismiss always calls the latest
  // handleOpenChange without re-subscribing the gesture listeners.
  const handleOpenChangeRef = useRef(handleOpenChange);
  useEffect(() => {
    handleOpenChangeRef.current = handleOpenChange;
  });

  const runItem = (item: Item): void => {
    if (item.kind === "action") {
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
          className="fixed inset-0 z-50 bg-foreground/45 backdrop-blur-sm transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0"
        />
        <DialogPrimitive.Popup
          ref={sheetRef}
          // Override glass-regular's blur with the denser dialog blur (same
          // trick as DialogContent so the popup reads as the canonical "modal"
          // glass surface).
          style={{
            backdropFilter:
              "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
            WebkitBackdropFilter:
              "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
          }}
          {...contentProps}
          className={cn(
            // Mobile (default): iOS bottom sheet — full-width, bottom-pinned,
            // rounded top, slides up with iOS sheet easing, swipe-to-dismiss.
            "glass-strong fixed inset-x-0 bottom-0 z-50 flex max-h-[80dvh] w-full flex-col gap-0 overflow-hidden rounded-t-3xl rounded-b-none p-0 text-foreground",
            "transition-[transform,opacity] duration-[400ms] ease-[cubic-bezier(0.32,0.72,0,1)] max-sm:data-[ending-style]:translate-y-full max-sm:data-[starting-style]:translate-y-full",
            // Desktop (sm+): centered top-anchored modal with scale+fade. The
            // -translate-x keeps composing with scale during the anim.
            "sm:inset-x-auto sm:bottom-auto sm:top-[20dvh] sm:left-1/2 sm:max-h-[60dvh] sm:max-w-xl sm:-translate-x-1/2 sm:rounded-3xl sm:transition-all sm:duration-200 sm:data-[ending-style]:scale-95 sm:data-[ending-style]:opacity-0 sm:data-[starting-style]:scale-95 sm:data-[starting-style]:opacity-0"
          )}
        >
          {/* Grabber: drag affordance + swipe-to-dismiss handle, mobile only. */}
          <div
            aria-hidden
            {...handleProps}
            className="mx-auto mt-2.5 h-1.5 w-9 shrink-0 cursor-grab touch-none rounded-full bg-foreground/15 sm:hidden"
          />
          <DialogPrimitive.Title className="sr-only">
            Command palette
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search actions and conversations. Use arrow keys to navigate, Enter
            to select, Escape to close.
          </DialogPrimitive.Description>

          <div className="relative flex shrink-0 items-center border-b border-foreground/10 px-5">
            <Search
              aria-hidden
              className="pointer-events-none size-4 shrink-0 text-muted-foreground"
            />
            <input
              ref={inputRef}
              type="text"
              role="combobox"
              aria-haspopup="listbox"
              aria-expanded={open}
              aria-controls={listboxId}
              aria-activedescendant={activeOptionId}
              aria-autocomplete="list"
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              onKeyDown={onInputKeyDown}
              placeholder="Search actions and conversations…"
              className="block w-full bg-transparent py-4 pl-3 pr-2 text-lg text-foreground outline-none placeholder:text-muted-foreground"
            />
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto py-2">
            {flat.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">
                No results — try a different term
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
                                "mx-2 flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm",
                                isSelected
                                  ? "bg-accent text-accent-foreground"
                                  : "text-foreground",
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
                              "mx-2 flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm",
                              isSelected
                                ? "bg-accent text-accent-foreground"
                                : "text-foreground",
                            )}
                          >
                            <MessageSquare
                              aria-hidden
                              className="size-4 shrink-0 text-muted-foreground"
                            />
                            <span className="min-w-0 flex-1 truncate">
                              {item.conversation.title}
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

          <div className="shrink-0 border-t border-foreground/10 px-5 py-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] text-[11px] text-muted-foreground sm:pb-2">
            <span className="font-mono">↑↓</span> to navigate ·{" "}
            <span className="font-mono">↵</span> to select ·{" "}
            <span className="font-mono">Esc</span> to close
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
