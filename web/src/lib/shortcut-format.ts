"use client";

import { useSyncExternalStore } from "react";

import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";

// Hydration-safe platform detection. SSR cannot know the user's platform, so
// the first client paint must match SSR: assume non-Mac (renders "Ctrl"), then
// flip after mount. Without this, server-rendered "Ctrl" replaced by "⌘" on
// the client triggers a React hydration mismatch warning.
//
// useSyncExternalStore lets us return the SSR-stable value during server
// render and the real client value after mount without setState-in-effect.
function readIsMac(): boolean {
  if (typeof navigator === "undefined") return false;
  // navigator.platform is deprecated but still the most reliable signal for
  // distinguishing macOS from Windows/Linux for keyboard-shortcut display.
  return (navigator.platform?.toLowerCase() ?? "").includes("mac");
}
// Subscribe is a no-op: platform doesn't change at runtime.
function subscribePlatform(): () => void {
  return () => {};
}
export function usePlatform(): { isMac: boolean } {
  const isMac = useSyncExternalStore(
    subscribePlatform,
    readIsMac,
    () => false, // SSR snapshot — always "non-Mac" so server HTML matches the first client paint.
  );
  return { isMac };
}

// Normalize a single-character key for display: uppercase letters, keep
// punctuation as-is. Special-cases the literal " " and named keys.
function formatKey(key: string): string {
  if (key === " ") return "Space";
  if (key === "Escape") return "Esc";
  if (key === "Backspace") return "Backspace";
  if (key === "ArrowUp") return "↑";
  if (key === "ArrowDown") return "↓";
  if (key === "ArrowLeft") return "←";
  if (key === "ArrowRight") return "→";
  if (key === "Enter") return "↵";
  if (key.length === 1) return key.toUpperCase();
  return key;
}

// Returns the human-readable key-cap segments for a shortcut, in display
// order (modifier(s) first, then the key). Used by both the palette right-
// aligned hint and the shortcuts dialog kbd rows.
export function formatShortcut(s: ShortcutKeys, isMac: boolean): string[] {
  const segments: string[] = [];
  if (s.mod) segments.push(isMac ? "⌘" : "Ctrl");
  if (s.shift) segments.push(isMac ? "⇧" : "Shift");
  segments.push(formatKey(s.key));
  return segments;
}
