"use client";

import type { JSX } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatShortcut, usePlatform } from "@/lib/shortcut-format";
import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";

export interface ShortcutRow {
  label: string;
  shortcut: ShortcutKeys;
}

export interface ShortcutSection {
  heading: string;
  items: ShortcutRow[];
}

export interface ShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shortcuts: ShortcutSection[];
}

// One row inside the shortcuts dialog: action label on the left, key caps on
// the right. The row is tabbable (tabIndex=0) so screen-reader users hit
// each entry and hear both the label and the key-cap text (PRD §5.7 a11y
// acceptance: "every shortcut row is reachable and announced").
function Row({ row, isMac }: { row: ShortcutRow; isMac: boolean }): JSX.Element {
  const segments = formatShortcut(row.shortcut, isMac);
  const spoken = segments.join(" plus ");
  return (
    <div
      tabIndex={0}
      role="listitem"
      aria-label={`${row.label}: ${spoken}`}
      className="flex items-center justify-between gap-4 rounded-lg px-2 py-1.5 outline-none focus-visible:shadow-[var(--focus-ring)]"
    >
      <span className="text-sm text-foreground">{row.label}</span>
      <span aria-hidden className="flex shrink-0 items-center gap-1">
        {segments.map((s, i) => (
          <span key={i} className="flex items-center gap-1">
            <kbd className="rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-xs leading-none text-foreground">
              {s}
            </kbd>
            {i < segments.length - 1 ? (
              <span className="text-xs text-muted-foreground">+</span>
            ) : null}
          </span>
        ))}
      </span>
    </div>
  );
}

// PRD 01 §4.9 / §5.7 — "show all shortcuts" dialog. Base UI's Dialog already
// gives us the focus trap + Esc-to-close + return-focus-on-close behaviors,
// so this is just a presentational shell on top.
export function ShortcutsDialog({
  open,
  onOpenChange,
  shortcuts,
}: ShortcutsDialogProps): JSX.Element {
  const { isMac } = usePlatform();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Every action below is reachable without the mouse.
          </DialogDescription>
        </DialogHeader>
        <div className="-mr-2 max-h-[60dvh] space-y-5 overflow-y-auto pr-2">
          {shortcuts.map((section) => (
            <section key={section.heading} className="space-y-1">
              <h3 className="px-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                {section.heading}
              </h3>
              <div role="list" aria-label={section.heading}>
                {section.items.map((row) => (
                  <Row key={row.label} row={row} isMac={isMac} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
