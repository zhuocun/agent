"use client";

import { useEffect, useRef } from "react";

// Display-only keystroke metadata — palette/dialog rows accept this without a
// handler so the descriptor array stays a pure value (React Compiler won't
// flag it as a ref-carrier).
export interface ShortcutKeys {
  key: string;
  mod?: boolean; // Cmd on Mac, Ctrl elsewhere
  shift?: boolean;
  // Opt-in to firing while focus is inside an input/textarea/contenteditable.
  // Bare-key shortcuts must not hijack typing; modifier combos that aren't
  // valid keystrokes (Cmd+K, Cmd+/, Shift+Esc) can safely set this.
  allowInInput?: boolean;
}

export interface Shortcut extends ShortcutKeys {
  handler: (e: KeyboardEvent) => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return true;
  if (target.isContentEditable) return true;
  return false;
}

function normalizeKey(key: string): string {
  if (key.length === 1) return key.toLowerCase();
  return key;
}

// Global keyboard-shortcuts hook (PRD 01 §4.9, §5.5). Capture-phase keydown on
// `window` so we can preventDefault before page-level handlers see it.
// IME-safe: composition keystrokes are skipped so CJK input remains usable.
export function useKeyboardShortcuts(shortcuts: Shortcut[]): void {
  // Ref-indirection so the effect runs once: re-attaching on every render
  // would churn the listener and race React 18+ Strict-Mode double-invocation.
  const shortcutsRef = useRef<Shortcut[]>(shortcuts);
  useEffect(() => {
    shortcutsRef.current = shortcuts;
  }, [shortcuts]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const isMac =
      typeof navigator !== "undefined" &&
      (navigator.platform?.toLowerCase() ?? "").includes("mac");

    const onKeyDown = (e: KeyboardEvent): void => {
      if (e.isComposing || e.keyCode === 229) return;

      const editable = isEditableTarget(e.target);
      const eventKey = normalizeKey(e.key);

      for (const s of shortcutsRef.current) {
        const wantMod = s.mod === true;
        // Cmd-on-Mac XOR Ctrl-on-others — never both. The whole reason `mod`
        // is one boolean instead of two.
        const gotMod = isMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
        if (wantMod !== gotMod) continue;

        const wantShift = s.shift === true;
        if (wantShift !== e.shiftKey) continue;

        if (e.altKey) continue;

        if (normalizeKey(s.key) !== eventKey) continue;

        if (editable && !s.allowInInput) continue;

        e.preventDefault();
        s.handler(e);
        return;
      }
    };

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);
}
