"use client";

import { useEffect, useId, useMemo, useRef, type JSX, type RefObject } from "react";
import {
  Bug,
  Code2,
  FileText,
  Languages,
  Lightbulb,
  Mail,
  PenLine,
  ScrollText,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { SlashCommand, SlashCommandIconKey } from "@/lib/types";

const COMMAND_ICONS: Record<SlashCommandIconKey, LucideIcon> = {
  summarize: ScrollText,
  explain: FileText,
  translate: Languages,
  rewrite: PenLine,
  debug: Bug,
  "code-review": Code2,
  "draft-email": Mail,
  brainstorm: Lightbulb,
};

export interface SlashCommandsPopoverProps {
  open: boolean;
  commands: SlashCommand[];
  query: string;
  selectedIndex: number;
  onSelectedIndexChange: (next: number) => void;
  onPick: (command: SlashCommand) => void;
  onClose: () => void;
  // Optional ids so the composer can wire combobox ↔ listbox/activedescendant
  // pairs across the two components.
  listboxId?: string;
  optionIdPrefix?: string;
  // Optional anchor element (e.g. the composer capsule). Clicks inside this
  // element count as "inside" for outside-click dismissal — so positioning the
  // cursor in the textarea doesn't close the popover.
  anchorRef?: RefObject<HTMLElement | null>;
}

// Case-insensitive name/description filter. Pure so the composer can compute
// the same filtered set when handling Enter/Tab without re-renders.
export function filterCommands(
  commands: SlashCommand[],
  query: string,
): SlashCommand[] {
  const q = query.toLowerCase();
  if (!q) return commands;
  return commands.filter(
    (c) =>
      c.name.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q),
  );
}

export function SlashCommandsPopover({
  open,
  commands,
  query,
  selectedIndex,
  onSelectedIndexChange,
  onPick,
  onClose,
  listboxId,
  optionIdPrefix,
  anchorRef,
}: SlashCommandsPopoverProps): JSX.Element | null {
  const popupRef = useRef<HTMLDivElement>(null);
  const fallbackListboxId = useId();
  const fallbackOptionPrefix = useId();
  const resolvedListboxId = listboxId ?? fallbackListboxId;
  const resolvedOptionPrefix = optionIdPrefix ?? fallbackOptionPrefix;

  const filtered = useMemo(
    () => filterCommands(commands, query),
    [commands, query],
  );

  // Outside-click dismissal — pointerdown beats the textarea's click and runs
  // before focus mutations, so the textarea keeps focus after the popover
  // closes (the composer never moves focus on close). Clicks inside the
  // anchor (the composer capsule) also count as "inside" so cursor positioning
  // or tier-picker interaction never dismisses the popover.
  useEffect(() => {
    if (!open) return;
    const handler = (event: PointerEvent): void => {
      const node = popupRef.current;
      if (!node) return;
      if (!(event.target instanceof Node)) return;
      if (node.contains(event.target)) return;
      const anchor = anchorRef?.current;
      if (anchor && anchor.contains(event.target)) return;
      onClose();
    };
    document.addEventListener("pointerdown", handler);
    return () => document.removeEventListener("pointerdown", handler);
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  const clamped =
    filtered.length === 0
      ? -1
      : Math.min(Math.max(selectedIndex, 0), filtered.length - 1);

  return (
    <div
      ref={popupRef}
      className={cn(
        "absolute bottom-full inset-x-0 z-20 mb-2",
        "glass-strong overflow-hidden rounded-2xl text-foreground",
        "transition-opacity duration-150 motion-reduce:transition-none",
      )}
      role="presentation"
    >
      <div id={`${resolvedListboxId}-label`} className="sr-only">
        Slash commands
      </div>
      {/* Always render the listbox so `aria-controls` on the textarea points
          at a real element — even when no commands match. An empty listbox is
          valid ARIA; the no-match hint sits alongside it inside the popup. */}
      <ul
        role="listbox"
        id={resolvedListboxId}
        aria-labelledby={`${resolvedListboxId}-label`}
        className={cn(
          "max-h-72 overflow-y-auto py-1",
          filtered.length === 0 && "sr-only",
        )}
      >
        {filtered.map((command, index) => {
          const isSelected = index === clamped;
          const Icon = COMMAND_ICONS[command.icon];
          const id = `${resolvedOptionPrefix}-${index}`;
          return (
            <li
              key={command.id}
              id={id}
              role="option"
              aria-selected={isSelected}
              onMouseEnter={() => onSelectedIndexChange(index)}
              onMouseDown={(e) => {
                // mousedown beats the textarea's blur, which would unmount
                // the popover before the click resolved.
                e.preventDefault();
                onPick(command);
              }}
              className={cn(
                "mx-1 flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm",
                isSelected
                  ? "bg-accent text-accent-foreground"
                  : "text-foreground",
              )}
            >
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-lg",
                  isSelected
                    ? "bg-accent text-accent-foreground"
                    : "bg-secondary text-muted-foreground",
                )}
              >
                <Icon aria-hidden className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-mono text-sm font-medium">
                  /{command.name}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {command.description}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      {filtered.length === 0 ? (
        <div className="px-4 py-3 text-sm text-muted-foreground">
          No commands match — keep typing for a regular message.
        </div>
      ) : null}
    </div>
  );
}
