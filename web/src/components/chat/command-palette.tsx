"use client";

import { useId, useMemo, useRef, useState, type JSX } from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { MessageSquare, Search, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatShortcut, usePlatform } from "@/lib/shortcut-format";
import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";
import type { ConversationSummary } from "@/lib/types";

// A palette action — one of the global handlers exposed to the keyboard layer
// AND surfaced as a row inside the palette. `shortcut` is the descriptor used
// to render the right-aligned key-cap hint; it doesn't have to be the same
// object passed to useKeyboardShortcuts (the palette doesn't dispatch from
// it), but in practice callers reuse the same descriptors.
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
  | { kind: "action"; section: "Actions" | "Settings"; action: CommandAction }
  | { kind: "conversation"; conversation: ConversationSummary; isActive: boolean };

// Build the flat-but-grouped item list from the current query. Empty query
// shows everything; non-empty filters by case-insensitive substring on
// labels/titles.
function buildItems(
  query: string,
  actions: CommandAction[],
  conversations: ConversationSummary[],
  activeId: string | null,
): { sections: { heading: string; items: Item[] }[]; flat: Item[] } {
  const q = query.trim().toLowerCase();
  const match = (s: string): boolean => (q ? s.toLowerCase().includes(q) : true);

  const actionItems = actions.filter((a) => match(a.label));
  const actionsSection = actionItems
    .filter((a) => a.section === "Actions")
    .map<Item>((action) => ({ kind: "action", section: "Actions", action }));
  const settingsSection = actionItems
    .filter((a) => a.section === "Settings")
    .map<Item>((action) => ({ kind: "action", section: "Settings", action }));

  const recentSection = conversations
    .filter((c) => match(c.title))
    .map<Item>((c) => ({ kind: "conversation", conversation: c, isActive: c.id === activeId }));

  const sections: { heading: string; items: Item[] }[] = [];
  if (actionsSection.length > 0) sections.push({ heading: "Actions", items: actionsSection });
  if (settingsSection.length > 0) sections.push({ heading: "Settings", items: settingsSection });
  if (recentSection.length > 0) sections.push({ heading: "Recent", items: recentSection });

  const flat = sections.flatMap((s) => s.items);
  return { sections, flat };
}

// Single key-cap hint row, used on the right side of each action row. Mirrors
// the shortcuts dialog's visual treatment so the two surfaces are consistent.
function ShortcutHint({ shortcut }: { shortcut: ShortcutKeys }): JSX.Element {
  const { isMac } = usePlatform();
  const segments = formatShortcut(shortcut, isMac);
  return (
    <span className="ml-3 flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
      {segments.map((s, i) => (
        <kbd
          key={i}
          className="rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] leading-none text-foreground"
        >
          {s}
        </kbd>
      ))}
    </span>
  );
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
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();
  const optionIdPrefix = useId();

  const { sections, flat } = useMemo(
    () => buildItems(query, actions, conversations, activeId),
    [query, actions, conversations, activeId],
  );

  // Clamp the selected index against the current result list so a filter that
  // narrows results doesn't leave selection pointing past the end. Derived
  // (not state) — no effect needed, no cascading render.
  const clampedIndex =
    flat.length === 0 ? 0 : Math.min(selectedIndex, flat.length - 1);

  // ID of the currently selected option, used for aria-activedescendant. The
  // combobox pattern: the input keeps DOM focus, the listbox highlights move
  // via activedescendant rather than tabindex/roving focus.
  const activeOptionId =
    flat.length > 0 ? `${optionIdPrefix}-${clampedIndex}` : undefined;

  // Wrap onOpenChange so closing the palette also clears the search query and
  // resets selection. Doing this here (event-driven) rather than in an effect
  // avoids the cascading-render lint while preserving the same UX.
  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setQuery("");
      setSelectedIndex(0);
    }
    onOpenChange(next);
  };

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

  // Running index across sections so each row knows its position in `flat`.
  let runningIndex = 0;

  return (
    <DialogPrimitive.Root open={open} onOpenChange={handleOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          className="fixed inset-0 z-50 bg-black/45 backdrop-blur-sm transition-opacity duration-200 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0"
        />
        <DialogPrimitive.Popup
          // Override glass-regular's blur with the denser dialog blur (same
          // trick as DialogContent so the popup reads as the canonical "modal"
          // glass surface).
          style={{
            backdropFilter:
              "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
            WebkitBackdropFilter:
              "blur(var(--glass-blur-xl)) saturate(var(--glass-saturate)) contrast(var(--glass-contrast))",
          }}
          className="glass-strong fixed top-[20vh] left-1/2 z-50 flex max-h-[60vh] w-full max-w-xl -translate-x-1/2 flex-col gap-0 overflow-hidden rounded-3xl p-0 text-foreground transition-all duration-200 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0"
        >
          <DialogPrimitive.Title className="sr-only">
            Command palette
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search actions and conversations. Use arrow keys to navigate, Enter
            to select, Escape to close.
          </DialogPrimitive.Description>

          {/* Search input — wears the combobox role so the listbox+
              activedescendant pattern is announced to AT correctly. */}
          <div className="relative flex shrink-0 items-center border-b border-foreground/10 px-5">
            <Search
              aria-hidden
              className="pointer-events-none size-4 shrink-0 text-muted-foreground"
            />
            <input
              ref={inputRef}
              type="text"
              role="combobox"
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

          {/* Results listbox. */}
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
                        const indexInFlat = runningIndex++;
                        const isSelected = indexInFlat === clampedIndex;
                        const id = `${optionIdPrefix}-${indexInFlat}`;
                        if (item.kind === "action") {
                          const Icon = item.action.icon;
                          return (
                            <li
                              key={item.action.id}
                              id={id}
                              role="option"
                              aria-selected={isSelected}
                              onMouseEnter={() => setSelectedIndex(indexInFlat)}
                              onMouseDown={(e) => {
                                // mousedown to beat the input's blur, which
                                // would otherwise unmount the row before the
                                // click resolved.
                                e.preventDefault();
                                runItem(item);
                              }}
                              className={cn(
                                "mx-2 flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-sm",
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
                                <ShortcutHint shortcut={item.action.shortcut} />
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
                            onMouseEnter={() => setSelectedIndex(indexInFlat)}
                            onMouseDown={(e) => {
                              e.preventDefault();
                              runItem(item);
                            }}
                            className={cn(
                              "mx-2 flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-sm",
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

          {/* Hint row — keyboard discoverability inside the palette itself. */}
          <div className="shrink-0 border-t border-foreground/10 px-5 py-2 text-[11px] text-muted-foreground">
            <span className="font-mono">↑↓</span> to navigate ·{" "}
            <span className="font-mono">↵</span> to select ·{" "}
            <span className="font-mono">Esc</span> to close
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
