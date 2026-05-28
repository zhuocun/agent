"use client";

import { useEffect, useRef } from "react";

// Display-only keystroke metadata — the subset of a Shortcut needed to render
// key caps. Lets the palette / shortcuts dialog accept a static binding
// (without a runtime handler) so the descriptor array stays a pure value and
// isn't tracked by the React Compiler as a ref-carrier.
export interface ShortcutKeys {
  key: string; // e.g. "k", "/", "Escape", "Backspace", ";", "O"
  mod?: boolean; // Cmd on Mac, Ctrl elsewhere
  shift?: boolean;
  allowInInput?: boolean;
}

// A single keyboard shortcut descriptor. `mod` is the OS-correct modifier
// (Cmd on Mac, Ctrl elsewhere) — kept as one boolean so callers don't have to
// reason about platform when declaring shortcuts. `shift` is independent.
//
// `allowInInput` opts the shortcut into firing even when focus is inside an
// input / textarea / contenteditable element. Default false: bare-key
// shortcuts shouldn't hijack typing. Set true for modifier-based shortcuts
// that are unambiguous typing-wise (Cmd+K, Cmd+/, Shift+Esc).
export interface Shortcut extends ShortcutKeys {
  handler: (e: KeyboardEvent) => void;
}

// True when focus is inside an editable surface (text input, textarea,
// contenteditable). Used to gate non-modifier shortcuts from interrupting
// typing.
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return true;
  if (target.isContentEditable) return true;
  return false;
}

// Normalize an event's key for matching: lowercase for letters, keep
// punctuation/named keys as-is. The descriptor's `key` is normalized the same
// way so authors don't have to think about case.
function normalizeKey(key: string): string {
  if (key.length === 1) return key.toLowerCase();
  return key;
}

// Global keyboard-shortcuts hook (PRD 01 §4.9, §5.5). Attaches a single
// capture-phase keydown listener on `window` so we can preventDefault before
// page-level handlers see it. IME-safe: ignores composition keystrokes
// (`isComposing` / keyCode 229) so CJK input remains usable.
export function useKeyboardShortcuts(shortcuts: Shortcut[]): void {
  // Hold the latest shortcut list in a ref so the effect attaches the listener
  // exactly once (re-attaching on every render would churn the listener and
  // race with React 18+ Strict-Mode double-invocation).
  const shortcutsRef = useRef<Shortcut[]>(shortcuts);
  useEffect(() => {
    shortcutsRef.current = shortcuts;
  }, [shortcuts]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // navigator.platform is deprecated but still the most reliable signal for
    // distinguishing macOS from Windows/Linux for keyboard semantics.
    const isMac =
      typeof navigator !== "undefined" &&
      (navigator.platform?.toLowerCase() ?? "").includes("mac");

    const onKeyDown = (e: KeyboardEvent): void => {
      // IME-safe: do not interpret composition keystrokes.
      if (e.isComposing || e.keyCode === 229) return;

      const editable = isEditableTarget(e.target);
      const eventKey = normalizeKey(e.key);

      for (const s of shortcutsRef.current) {
        const wantMod = s.mod === true;
        // Cmd-on-Mac OR Ctrl-on-others — never both. This is the entire reason
        // `mod` exists as a single boolean.
        const gotMod = isMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
        if (wantMod !== gotMod) continue;

        const wantShift = s.shift === true;
        if (wantShift !== e.shiftKey) continue;

        // Reject incidental alt: we don't currently use alt in any shortcut,
        // and matching with altKey set would let unrelated combos fire.
        if (e.altKey) continue;

        if (normalizeKey(s.key) !== eventKey) continue;

        if (editable && !s.allowInInput) continue;

        e.preventDefault();
        s.handler(e);
        return;
      }
    };

    // Capture phase so we beat page-level listeners (e.g. the composer's
    // Esc-to-stop) only when we explicitly choose to handle a key.
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);
}
