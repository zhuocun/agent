"use client";

import type { JSX } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { KeyCaps } from "@/components/chat/key-caps";
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

function Row({ row, isMac }: { row: ShortcutRow; isMac: boolean }): JSX.Element {
  const segments = formatShortcut(row.shortcut, isMac);
  const spoken = segments.join(" plus ");
  // `role="listitem"` is non-interactive — leaving tabIndex unset keeps it
  // reachable to the AT virtual cursor without making it a Tab stop.
  return (
    <div
      role="listitem"
      aria-label={`${row.label}: ${spoken}`}
      className="flex items-center justify-between gap-4 rounded-lg px-2 py-1.5"
    >
      <span className="text-sm text-foreground">{row.label}</span>
      <KeyCaps shortcut={row.shortcut} variant="row" />
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
