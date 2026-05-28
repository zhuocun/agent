"use client";

import { useSyncExternalStore } from "react";

import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";

// Hydration-safe platform detection. SSR cannot know the user's platform, so
// the first client paint must match SSR (always non-Mac) and only flip after
// mount — without this, swapping "Ctrl" → "⌘" trips React's hydration check.
function readIsMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return (navigator.platform?.toLowerCase() ?? "").includes("mac");
}
function subscribePlatform(): () => void {
  return () => {};
}
export function usePlatform(): { isMac: boolean } {
  const isMac = useSyncExternalStore(
    subscribePlatform,
    readIsMac,
    () => false, // SSR snapshot must match first client paint.
  );
  return { isMac };
}

function formatKey(key: string, isMac: boolean): string {
  if (key === " ") return "Space";
  if (key === "Escape") return "Esc";
  if (key === "Backspace") return isMac ? "⌫" : "Bksp";
  if (key === "ArrowUp") return "↑";
  if (key === "ArrowDown") return "↓";
  if (key === "ArrowLeft") return "←";
  if (key === "ArrowRight") return "→";
  if (key === "Enter") return "↵";
  if (key.length === 1) return key.toUpperCase();
  return key;
}

export function formatShortcut(s: ShortcutKeys, isMac: boolean): string[] {
  const segments: string[] = [];
  if (s.mod) segments.push(isMac ? "⌘" : "Ctrl");
  if (s.shift) segments.push(isMac ? "⇧" : "Shift");
  segments.push(formatKey(s.key, isMac));
  return segments;
}
