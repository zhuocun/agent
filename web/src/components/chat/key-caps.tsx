"use client";

import type { JSX } from "react";

import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";
import { formatShortcut, usePlatform } from "@/lib/shortcut-format";
import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";

export interface KeyCapsProps {
  shortcut: ShortcutKeys;
  // "compact" (palette right-aligned hint) uses tighter spacing and smaller
  // text; "row" (shortcuts dialog) shows "+" separators between caps.
  variant?: "compact" | "row";
  className?: string;
}

const KEY_CAP_CLASS =
  "h-auto w-auto min-w-0 rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-xs font-normal leading-none text-foreground";

export function KeyCaps({
  shortcut,
  variant = "compact",
  className,
}: KeyCapsProps): JSX.Element {
  const { isMac } = usePlatform();
  const segments = formatShortcut(shortcut, isMac);

  // Shortcut chords are inherently LTR (Ctrl → K, ⌘ → K). Isolate so an RTL
  // document doesn't reverse flex children into "K Ctrl".
  if (variant === "row") {
    return (
      <KbdGroup
        dir="ltr"
        aria-hidden
        className={cn("flex shrink-0 items-center gap-1 font-sans", className)}
      >
        {segments.map((s, i) => (
          <span key={i} className="flex items-center gap-1">
            <Kbd className={KEY_CAP_CLASS}>{s}</Kbd>
            {i < segments.length - 1 ? (
              <span className="text-xs text-muted-foreground">+</span>
            ) : null}
          </span>
        ))}
      </KbdGroup>
    );
  }

  return (
    <KbdGroup
      dir="ltr"
      aria-hidden
      className={cn(
        "flex shrink-0 items-center gap-1 font-sans text-xs text-muted-foreground",
        className,
      )}
    >
      {segments.map((s, i) => (
        <Kbd key={i} className={KEY_CAP_CLASS}>
          {s}
        </Kbd>
      ))}
    </KbdGroup>
  );
}
