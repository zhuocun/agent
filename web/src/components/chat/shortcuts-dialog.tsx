"use client";

import {
  useCallback,
  useState,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { RotateCcw } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { KeyCaps } from "@/components/chat/key-caps";
import { formatShortcut, usePlatform } from "@/lib/shortcut-format";
import {
  checkReservedCombo,
  type EffectiveBindings,
} from "@/lib/shortcut-defaults";
import type { ShortcutId } from "@/lib/types";
import type { ShortcutKeys } from "@/lib/use-keyboard-shortcuts";

export interface ShortcutRow {
  // Stable id — present for rebindable rows (every dialog row is rebindable in
  // editable mode). Optional so legacy read-only callers can omit it.
  id?: ShortcutId;
  label: string;
  shortcut: ShortcutKeys;
  // Whether this row currently runs on a user override (vs. its default).
  // Drives the per-row "Reset" affordance in editable mode.
  isOverridden?: boolean;
}

export interface ShortcutSection {
  heading: string;
  items: ShortcutRow[];
}

export interface ShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shortcuts: ShortcutSection[];
  // --- Editable mode (D23) ------------------------------------------------
  // When `editable` is set, rows expose a capture-to-rebind control, a per-row
  // reset, and the footer exposes reset-to-defaults. Omit for the read-only
  // "show all shortcuts" view.
  editable?: boolean;
  // Current effective bindings — the guard checks duplicates against these.
  effectiveBindings?: EffectiveBindings;
  // Human label for an action id (used in duplicate-conflict messages).
  labelFor?: (id: ShortcutId) => string;
  // Commit a guarded rebind for one action.
  onRebind?: (id: ShortcutId, combo: ShortcutKeys) => void;
  // Revert one action to its built-in default.
  onResetAction?: (id: ShortcutId) => void;
  // Revert every action to its built-in default.
  onResetAll?: () => void;
}

// True for keydown events that are a lone modifier press (no "real" key yet).
// We wait for a non-modifier key before building a combo so the user can hold
// Cmd/Shift and then press the letter.
function isLoneModifier(e: ReactKeyboardEvent): boolean {
  return (
    e.key === "Shift" ||
    e.key === "Control" ||
    e.key === "Meta" ||
    e.key === "Alt" ||
    e.key === "AltGraph" ||
    e.key === "CapsLock" ||
    e.key === "Dead"
  );
}

// Build a matcher `ShortcutKeys` from a native keydown. `mod` collapses
// Cmd-on-Mac / Ctrl-on-others into one boolean, mirroring the live matcher.
function comboFromEvent(
  e: ReactKeyboardEvent,
  isMac: boolean,
): ShortcutKeys {
  const mod = isMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
  return {
    key: e.key,
    mod,
    shift: e.shiftKey,
  };
}

function ReadOnlyRow({
  row,
  isMac,
}: {
  row: ShortcutRow;
  isMac: boolean;
}): JSX.Element {
  const segments = formatShortcut(row.shortcut, isMac);
  const spoken = segments.join(" plus ");
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

function EditableRow({
  row,
  isMac,
  effectiveBindings,
  labelFor,
  onRebind,
  onResetAction,
  capturing,
  onStartCapture,
  onStopCapture,
}: {
  row: ShortcutRow;
  isMac: boolean;
  effectiveBindings: EffectiveBindings;
  labelFor?: (id: ShortcutId) => string;
  onRebind: (id: ShortcutId, combo: ShortcutKeys) => void;
  onResetAction: (id: ShortcutId) => void;
  capturing: boolean;
  onStartCapture: () => void;
  onStopCapture: () => void;
}): JSX.Element {
  const id = row.id as ShortcutId;
  // The inline rejection message. Only surfaced while this row is capturing
  // (see the gated render below), so a stale value can't leak after capture
  // ends — and the next capture's first keypress overwrites it regardless.
  const [error, setError] = useState<string | null>(null);

  const handleKeyDown = (e: ReactKeyboardEvent): void => {
    if (!capturing) return;
    // Escape cancels capture without rebinding (and is itself reserved).
    if (e.key === "Escape") {
      e.preventDefault();
      onStopCapture();
      return;
    }
    if (isLoneModifier(e)) {
      // Wait for the non-modifier key.
      e.preventDefault();
      return;
    }
    e.preventDefault();
    // Alt is ignored by the live matcher — reject at capture so the user gets a
    // clear message rather than a silently-Alt-less binding.
    if (e.altKey || e.key === "AltGraph") {
      setError("Alt isn't supported in shortcuts. Use ⌘/Ctrl and/or Shift.");
      return;
    }
    const combo = comboFromEvent(e, isMac);
    const result = checkReservedCombo(combo, id, effectiveBindings, labelFor);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setError(null);
    onRebind(id, combo);
    onStopCapture();
  };

  const segments = formatShortcut(row.shortcut, isMac);
  const spoken = segments.join(" plus ");

  return (
    <div
      role="listitem"
      className="flex flex-col gap-1 rounded-lg px-2 py-1.5"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="min-w-0 truncate text-sm text-foreground">
          {row.label}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          {row.isOverridden ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label={`Reset ${row.label} to default`}
              data-testid={`shortcut-reset-${id}`}
              onClick={() => {
                onStopCapture();
                setError(null);
                onResetAction(id);
              }}
            >
              <RotateCcw aria-hidden />
            </Button>
          ) : null}
          <button
            type="button"
            data-testid={`shortcut-rebind-${id}`}
            aria-label={
              capturing
                ? `Recording new shortcut for ${row.label}. Press a key combination, or Escape to cancel.`
                : `${row.label}: ${spoken}. Activate to rebind.`
            }
            aria-pressed={capturing}
            onClick={() => (capturing ? onStopCapture() : onStartCapture())}
            onKeyDown={handleKeyDown}
            onBlur={() => onStopCapture()}
            className={
              capturing
                ? "flex min-w-24 items-center justify-center rounded-md border border-ring bg-ring/10 px-2 py-1 text-xs font-medium text-foreground ring-2 ring-ring/25 outline-none"
                : "flex min-w-24 items-center justify-center rounded-md border border-border bg-muted/40 px-2 py-1 outline-none transition-colors hover:bg-muted focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25"
            }
          >
            {capturing ? (
              <span className="text-muted-foreground">Press keys…</span>
            ) : (
              <KeyCaps shortcut={row.shortcut} variant="row" />
            )}
          </button>
        </div>
      </div>
      {capturing && error ? (
        <p
          role="alert"
          className="text-right text-xs text-destructive"
          data-testid={`shortcut-error-${id}`}
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

// PRD 01 §4.9 / §5.7 — "show all shortcuts" dialog. In editable mode (D23) each
// row gains a capture-to-rebind control with a reserved-combo guard, a per-row
// reset, and a global reset-to-defaults. Base UI's Dialog gives us the focus
// trap + Esc-to-close + return-focus-on-close; the body is a list on top.
export function ShortcutsDialog({
  open,
  onOpenChange,
  shortcuts,
  editable = false,
  effectiveBindings,
  labelFor,
  onRebind,
  onResetAction,
  onResetAll,
}: ShortcutsDialogProps): JSX.Element {
  const { isMac } = usePlatform();
  // At most one row captures at a time (id of the capturing row, or null).
  const [capturingId, setCapturingId] = useState<ShortcutId | null>(null);

  // Reset capture state whenever the dialog closes so it never re-opens mid-
  // capture. Done in the change handler (not an effect) to satisfy the
  // no-setState-in-effect rule.
  const handleOpenChange = useCallback(
    (next: boolean): void => {
      if (!next) setCapturingId(null);
      onOpenChange(next);
    },
    [onOpenChange],
  );

  const canEdit =
    editable &&
    effectiveBindings != null &&
    onRebind != null &&
    onResetAction != null;

  const anyOverridden = shortcuts.some((section) =>
    section.items.some((row) => row.isOverridden),
  );

  const stopCapture = useCallback(() => setCapturingId(null), []);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      {/* Bottom sheet on mobile (base default); cap width only at sm+ so the
          mobile sheet stays full-width. Home-indicator-safe bottom padding is
          provided by the base DialogContent. */}
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            {canEdit
              ? "Rebind any action — press a key combination to record it. Enter and Escape stay reserved for sending and stopping."
              : "Every action below is reachable without the mouse."}
          </DialogDescription>
        </DialogHeader>
        <div className="-mr-2 max-h-[60dvh] space-y-5 overflow-y-auto pr-2">
          {shortcuts.map((section) => (
            <section key={section.heading} className="space-y-1">
              <h3 className="px-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                {section.heading}
              </h3>
              <div role="list" aria-label={section.heading}>
                {section.items.map((row) =>
                  canEdit && row.id ? (
                    <EditableRow
                      key={row.id}
                      row={row}
                      isMac={isMac}
                      effectiveBindings={effectiveBindings}
                      labelFor={labelFor}
                      onRebind={onRebind}
                      onResetAction={onResetAction}
                      capturing={capturingId === row.id}
                      onStartCapture={() =>
                        setCapturingId(row.id as ShortcutId)
                      }
                      onStopCapture={stopCapture}
                    />
                  ) : (
                    <ReadOnlyRow
                      key={row.id ?? row.label}
                      row={row}
                      isMac={isMac}
                    />
                  ),
                )}
              </div>
            </section>
          ))}
        </div>
        {canEdit && onResetAll ? (
          <div className="flex justify-end border-t border-border pt-3">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!anyOverridden}
              data-testid="shortcut-reset-all"
              onClick={() => {
                stopCapture();
                onResetAll();
              }}
            >
              <RotateCcw aria-hidden />
              Reset all to defaults
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
