// Keyboard-shortcut customization core (D23).
//
// "Customization is a labeled default, not a lock." Users may remap the app's
// otherwise-fixed shortcuts; the overrides persist on
// `preferences.keyboardShortcuts` and merge over the built-in `KEY_BINDINGS`
// defaults. This module is the pure, framework-free home for that logic:
//   - `resolveBindings(defaults, overrides)` — merge defaults + overrides into
//     the EFFECTIVE binding for each action (drives both the live keydown
//     matcher AND the shortcuts dialog/palette display).
//   - `checkReservedCombo(...)` — the reserved-combo guard: rejects combos that
//     would clobber the composer invariants (Enter/Escape), critical browser/OS
//     combos, Alt-bearing combos (the matcher ignores Alt), and duplicates.
//   - serialize/deserialize helpers for the JSON override column.
//   - reset helpers (per-action + reset-all).
//
// Kept dependency-light (only types) so it stays unit-testable and free of the
// heavy chat-thread module.

import type {
  KeyboardShortcuts,
  ShortcutId,
  ShortcutOverride,
} from "@/lib/types";
import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";

// A binding the user can rebind: the matcher keystroke plus its stable id and a
// human label. Structurally the chat-thread `KeyBinding` minus its handler.
export interface RebindableBinding extends ShortcutKeys {
  id: ShortcutId;
  label: string;
}

// The effective, resolved binding map: every action id -> its current keystroke
// (default unless the user overrode it).
export type EffectiveBindings = Record<ShortcutId, ShortcutKeys>;

// --- Combo identity ------------------------------------------------------

// Normalize a key the SAME way the live matcher does
// (`use-keyboard-shortcuts.ts`): single characters lower-case, named keys
// verbatim. Two combos that normalize to the same canonical string collide.
export function normalizeComboKey(key: string): string {
  if (key.length === 1) return key.toLowerCase();
  return key;
}

// Stable canonical signature for a combo — used for duplicate detection and
// equality. Alt is intentionally excluded (the matcher ignores it).
export function comboSignature(keys: ShortcutKeys): string {
  const mod = keys.mod === true ? "1" : "0";
  const shift = keys.shift === true ? "1" : "0";
  return `${mod}:${shift}:${normalizeComboKey(keys.key)}`;
}

export function combosEqual(a: ShortcutKeys, b: ShortcutKeys): boolean {
  return comboSignature(a) === comboSignature(b);
}

// --- Defaults + resolution ----------------------------------------------

// Build the built-in default map from the `KEY_BINDINGS` registry. The result
// is keyed by id and carries the full keystroke (including `allowInInput`),
// which overrides never touch.
export function defaultsFromBindings(
  bindings: readonly RebindableBinding[],
): EffectiveBindings {
  const out = {} as EffectiveBindings;
  for (const b of bindings) {
    out[b.id] = {
      key: b.key,
      mod: b.mod,
      shift: b.shift,
      allowInInput: b.allowInInput,
    };
  }
  return out;
}

// Merge a built-in default keystroke with a user override. Only the matcher-
// significant fields (key/mod/shift) come from the override; `allowInInput`
// always comes from the default so a remap can't accidentally make a bare key
// hijack typing (or vice versa).
export function applyOverride(
  base: ShortcutKeys,
  override: ShortcutOverride | undefined,
): ShortcutKeys {
  if (!override) return base;
  return {
    key: override.key,
    mod: override.mod === true,
    shift: override.shift === true,
    allowInInput: base.allowInInput,
  };
}

// The EFFECTIVE bindings = defaults merged with the user's overrides. Unknown
// override ids (e.g. a stale map referencing a removed action) are ignored.
export function resolveBindings(
  defaults: EffectiveBindings,
  overrides: KeyboardShortcuts | undefined,
): EffectiveBindings {
  const out = {} as EffectiveBindings;
  for (const id of Object.keys(defaults) as ShortcutId[]) {
    out[id] = applyOverride(defaults[id], overrides?.[id]);
  }
  return out;
}

// Whether an action currently has a user override (vs. running on its default).
export function isOverridden(
  overrides: KeyboardShortcuts | undefined,
  id: ShortcutId,
): boolean {
  return overrides?.[id] != null;
}

// --- Reserved-combo guard -----------------------------------------------

export type ReservedReason =
  | "alt"
  | "composer-invariant"
  | "browser-critical"
  | "duplicate"
  | "empty";

export interface GuardRejection {
  ok: false;
  reason: ReservedReason;
  // Human-readable, ready to render inline beneath the capture control.
  message: string;
  // For `duplicate`: the action id already bound to this combo.
  conflictId?: ShortcutId;
}

export interface GuardAcceptance {
  ok: true;
}

export type GuardResult = GuardAcceptance | GuardRejection;

// Keys owned by the inline-composer invariants, which stay FIXED and must never
// be rebindable to (Enter = send, Escape = stop-streaming / dismiss). Matched
// regardless of mod/shift so Mod+Enter / Shift+Enter etc. are all rejected.
const COMPOSER_INVARIANT_KEYS = new Set(["Enter", "Escape"]);

// Critical Mod+<key> browser/OS combos that the app must not steal. Lower-cased
// single chars (matcher normalization). Mod+Shift+<key> variants are guarded
// too — see `checkReservedCombo`.
const BROWSER_CRITICAL_MOD_KEYS = new Set([
  "c", // copy
  "v", // paste
  "x", // cut
  "a", // select all
  "z", // undo
  "t", // new tab
  "w", // close tab
  "n", // new window
  "q", // quit
  "r", // reload
  "l", // focus address bar
]);

function describeReserved(reason: ReservedReason): string {
  switch (reason) {
    case "alt":
      return "Alt isn't supported in shortcuts. Use ⌘/Ctrl and/or Shift.";
    case "composer-invariant":
      return "Enter and Escape are reserved for sending and stopping, so they can't be remapped.";
    case "browser-critical":
      return "That's a critical browser or system shortcut and can't be reassigned.";
    case "empty":
      return "Press a key combination to set this shortcut.";
    case "duplicate":
      // Overridden with the conflicting action's label by the caller.
      return "That combination is already used by another action.";
  }
}

// The reserved-combo guard. Returns `{ ok: true }` when `candidate` is a legal
// binding for `targetId`, or a typed rejection with an inline-ready message.
//
// `existing` is the CURRENT effective binding map (so duplicate detection runs
// against what's actually live, including other users' overrides). Re-selecting
// `targetId`'s own current combo is always allowed (no-op), and a combo that
// only collides with the target itself is not a duplicate.
export function checkReservedCombo(
  candidate: ShortcutKeys,
  targetId: ShortcutId,
  existing: EffectiveBindings,
  labelFor?: (id: ShortcutId) => string,
): GuardResult {
  const key = candidate.key;
  if (!key) {
    return { ok: false, reason: "empty", message: describeReserved("empty") };
  }

  // Alt is ignored by the matcher, so a combo "needing" Alt would silently fire
  // without it. Reject up front. (We can't read Alt off `ShortcutKeys`, which
  // has no alt field — the capture layer rejects Alt before building the combo —
  // but guard the named "Alt"/"AltGraph" key itself too.)
  if (key === "Alt" || key === "AltGraph") {
    return { ok: false, reason: "alt", message: describeReserved("alt") };
  }

  // Composer invariants: Enter / Escape with ANY modifier set.
  if (COMPOSER_INVARIANT_KEYS.has(key)) {
    return {
      ok: false,
      reason: "composer-invariant",
      message: describeReserved("composer-invariant"),
    };
  }

  // Critical browser/OS combos: Mod+<key> and Mod+Shift+<key>. Bare keys and
  // Shift-only keys are NOT browser-critical (they're page-level at most).
  if (candidate.mod === true) {
    const norm = normalizeComboKey(key);
    if (BROWSER_CRITICAL_MOD_KEYS.has(norm)) {
      return {
        ok: false,
        reason: "browser-critical",
        message: describeReserved("browser-critical"),
      };
    }
  }

  // Duplicate detection: does this combo already belong to a DIFFERENT action?
  const signature = comboSignature(candidate);
  for (const id of Object.keys(existing) as ShortcutId[]) {
    if (id === targetId) continue;
    if (comboSignature(existing[id]) === signature) {
      const label = labelFor?.(id);
      return {
        ok: false,
        reason: "duplicate",
        conflictId: id,
        message: label
          ? `That combination is already used by “${label}”.`
          : describeReserved("duplicate"),
      };
    }
  }

  return { ok: true };
}

// --- Serialize / deserialize (JSON column) -------------------------------

// Coerce a single stored entry into a clean override, or null if unusable.
// Only matcher-significant fields survive; mod/shift are coerced to booleans.
function coerceOverride(raw: unknown): ShortcutOverride | null {
  if (typeof raw !== "object" || raw === null) return null;
  const candidate = raw as Record<string, unknown>;
  const key = candidate.key;
  if (typeof key !== "string" || key.length === 0) return null;
  const override: ShortcutOverride = { key };
  if (candidate.mod === true) override.mod = true;
  if (candidate.shift === true) override.shift = true;
  return override;
}

// Parse an unknown JSON value (e.g. straight off the wire) into a clean,
// id-validated override map. Drops unknown action ids and malformed combos so a
// corrupt/forward-compatible payload can never crash the resolver.
export function deserializeShortcuts(
  raw: unknown,
  knownIds: readonly ShortcutId[],
): KeyboardShortcuts {
  if (typeof raw !== "object" || raw === null) return {};
  const known = new Set<string>(knownIds);
  const source = raw as Record<string, unknown>;
  const out: KeyboardShortcuts = {};
  for (const [id, value] of Object.entries(source)) {
    if (!known.has(id)) continue;
    const override = coerceOverride(value);
    if (override) out[id as ShortcutId] = override;
  }
  return out;
}

// Produce the canonical, minimal override map to persist. Only entries that
// actually DIFFER from their default are kept (a remap back to the default is
// stored as "no override" — keeping the column minimal and self-healing).
export function serializeShortcuts(
  overrides: KeyboardShortcuts,
  defaults: EffectiveBindings,
): KeyboardShortcuts {
  const out: KeyboardShortcuts = {};
  for (const [id, override] of Object.entries(overrides) as [
    ShortcutId,
    ShortcutOverride | undefined,
  ][]) {
    if (!override) continue;
    const base = defaults[id];
    const effective = applyOverride(base, override);
    if (base && combosEqual(base, effective)) continue; // same as default → drop
    out[id] = {
      key: override.key,
      ...(override.mod === true ? { mod: true } : {}),
      ...(override.shift === true ? { shift: true } : {}),
    };
  }
  return out;
}

// --- Reset helpers -------------------------------------------------------

// Remove a single action's override (revert it to its built-in default).
export function clearOverride(
  overrides: KeyboardShortcuts,
  id: ShortcutId,
): KeyboardShortcuts {
  if (overrides[id] == null) return overrides;
  const next = { ...overrides };
  delete next[id];
  return next;
}

// Set/replace a single action's override.
export function setOverride(
  overrides: KeyboardShortcuts,
  id: ShortcutId,
  candidate: ShortcutKeys,
): KeyboardShortcuts {
  const override: ShortcutOverride = {
    key: candidate.key,
    ...(candidate.mod === true ? { mod: true } : {}),
    ...(candidate.shift === true ? { shift: true } : {}),
  };
  return { ...overrides, [id]: override };
}

// Reset everything back to defaults: the empty override map.
export function resetAllOverrides(): KeyboardShortcuts {
  return {};
}
