"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Reusable pointer-driven "swipe left to reveal trailing actions" gesture,
 * tuned to feel like the native iOS list-row swipe.
 *
 * Design constraints (see implementation worker brief, item 1):
 * - MUST NOT fight vertical list scrolling. We only claim the gesture as a
 *   horizontal swipe once |dx| dominates |dy| past a small slop, and once an
 *   axis is decided we lock it for the rest of the gesture. A vertical decision
 *   bails out entirely so the scroll container handles the touch.
 * - Uses Pointer Events + pointer capture so we keep receiving moves even if the
 *   finger leaves the row, and so we don't depend on touch-event quirks.
 * - Full-swipe past a *proportional* distance (`fullSwipeRatio` × the row's
 *   measured width, floored at `fullSwipeFloor`) triggers the destructive
 *   action directly on release. A shorter swipe past `revealThreshold` snaps to
 *   the open (revealed) position; anything less snaps back closed.
 * - Honors `prefers-reduced-motion`: callers get `reducedMotion` so they can
 *   render the translate instantly (no slide transition).
 */

export interface SwipeActionsOptions {
  /** Total px width of the trailing action tray that should be revealed. */
  actionsWidth: number;
  /** Min leftward drag (px) to settle open after release. Default actionsWidth * 0.5. */
  revealThreshold?: number;
  /**
   * Fraction of the row's own measured width the finger must travel to trigger
   * the destructive action directly on release. A *proportional* threshold
   * (rather than a fixed px) so the full-swipe fires at a consistent "most of
   * the way across" feel regardless of layout width — a fixed 200px fires far
   * too early on a wide desktop rail and too late on a narrow phone sheet.
   * Defaults to 0.6 (≈60% of the row). Floored by `fullSwipeFloor` so a tiny
   * row can't make the gesture hair-trigger.
   */
  fullSwipeRatio?: number;
  /** Absolute floor (px) for the proportional full-swipe distance. Default 160. */
  fullSwipeFloor?: number;
  /** Fires when a full-swipe-left crosses the proportional threshold on release. */
  onFullSwipe: () => void;
  /** Disable the gesture entirely (e.g. while inline-renaming). */
  disabled?: boolean;
}

export interface SwipeActionsState {
  /** Live horizontal offset (<= 0). Bind to the row's transform. */
  offset: number;
  /** True once the row is settled at the open/revealed position. */
  open: boolean;
  /** True while a horizontal drag is actively in progress (suppress transition). */
  dragging: boolean;
  /** Mirror of the user's reduced-motion preference for transition gating. */
  reducedMotion: boolean;
  /** Programmatically snap closed (e.g. on row select, or tapping an action). */
  close: () => void;
  /** Pointer handlers to spread onto the draggable row element. */
  handlers: {
    onPointerDown: (e: React.PointerEvent) => void;
    onPointerMove: (e: React.PointerEvent) => void;
    onPointerUp: (e: React.PointerEvent) => void;
    onPointerCancel: (e: React.PointerEvent) => void;
    /**
     * Capture-phase click guard. A horizontal drag synthesizes a trailing
     * `click` on the inner tap target *before* React re-renders, so a handler
     * reading swipe `open` state would see a stale value and select the row.
     * We suppress that click here from a ref, which updates synchronously.
     */
    onClickCapture: (e: React.MouseEvent) => void;
  };
}

// Horizontal must beat vertical by this many px before we claim the gesture.
const AXIS_SLOP = 10;
// Allow a small rubber-band past the tray width so the open position has give.
const OVER_DRAG = 24;

type Axis = "undecided" | "horizontal" | "vertical";

export function useSwipeActions(
  options: SwipeActionsOptions,
): SwipeActionsState {
  const {
    actionsWidth,
    onFullSwipe,
    disabled = false,
    revealThreshold = actionsWidth * 0.5,
    fullSwipeRatio = 0.6,
    fullSwipeFloor = 160,
  } = options;

  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  // Per-gesture mutable state kept in a ref so move handlers don't re-render.
  const gesture = useRef<{
    pointerId: number | null;
    startX: number;
    startY: number;
    axis: Axis;
    baseOffset: number; // offset at gesture start (0 closed, -actionsWidth open)
    rowWidth: number; // measured width of the swiped row at gesture start
  }>({
    pointerId: null,
    startX: 0,
    startY: 0,
    axis: "undecided",
    baseOffset: 0,
    rowWidth: 0,
  });

  // True once the current gesture has been claimed as a horizontal drag, read
  // synchronously by the click guard. A ref (not state) so the trailing click
  // — fired before React re-renders — sees the correct value.
  const draggedRef = useRef(false);

  // Latest callbacks/values read inside handlers without re-binding listeners.
  const onFullSwipeRef = useRef(onFullSwipe);
  useEffect(() => {
    onFullSwipeRef.current = onFullSwipe;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const close = useCallback(() => {
    setOffset(0);
    setOpen(false);
  }, []);

  // Capture-phase guard: swallow the click that the browser synthesizes at the
  // end of a horizontal drag, so settling the tray open/closed never also
  // selects the row. Pure taps (no horizontal drag) pass through untouched.
  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (draggedRef.current) {
      e.preventDefault();
      e.stopPropagation();
      draggedRef.current = false;
    }
  }, []);

  const openMin = -(actionsWidth + OVER_DRAG);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (disabled) return;
      // Only primary pointer; ignore secondary touches/right-click.
      if (e.button != null && e.button > 0) return;
      // Fresh gesture: until we see horizontal movement, a release is a tap.
      draggedRef.current = false;
      // Measure the row up front (the handlers are spread onto the sliding row,
      // so currentTarget is the element we want). Captured per-gesture so the
      // proportional full-swipe threshold tracks the actual layout width — wide
      // desktop rail vs. narrow phone sheet — without any extra ref plumbing.
      const rowWidth =
        (e.currentTarget as Element).getBoundingClientRect?.().width ?? 0;
      gesture.current = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        axis: "undecided",
        baseOffset: open ? -actionsWidth : 0,
        rowWidth,
      };
    },
    [disabled, open, actionsWidth],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const g = gesture.current;
      if (g.pointerId !== e.pointerId) return;
      const dx = e.clientX - g.startX;
      const dy = e.clientY - g.startY;

      if (g.axis === "undecided") {
        // Wait until movement clears the slop on either axis before deciding.
        if (Math.abs(dx) < AXIS_SLOP && Math.abs(dy) < AXIS_SLOP) return;
        if (Math.abs(dx) > Math.abs(dy)) {
          g.axis = "horizontal";
          // Mark the gesture as a drag so the trailing click is suppressed.
          draggedRef.current = true;
          // Capture so we keep moves even if the finger slides off the row.
          (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
          setDragging(true);
        } else {
          // Vertical: hand the gesture back to the scroll container entirely.
          g.axis = "vertical";
          g.pointerId = null;
          return;
        }
      }

      if (g.axis !== "horizontal") return;

      // Clamp: can drag left to reveal (with a little over-drag), and right only
      // back to closed (0). No rightward reveal.
      let next = g.baseOffset + dx;
      if (next > 0) next = 0;
      if (next < openMin) next = openMin;
      setOffset(next);
    },
    [openMin],
  );

  const finishGesture = useCallback(
    (e: React.PointerEvent) => {
      const g = gesture.current;
      if (g.pointerId !== e.pointerId && g.axis !== "horizontal") {
        // Vertical / never-claimed gesture: nothing to settle.
        if (g.axis === "vertical") gesture.current.axis = "undecided";
        return;
      }
      const wasHorizontal = g.axis === "horizontal";
      const totalDx = e.clientX - g.startX;
      // Proportional full-swipe distance from the row width measured at
      // pointer-down, floored so a narrow row can't make it hair-trigger. Fall
      // back to the floor if the measurement was unavailable (width 0).
      const fullSwipeThreshold =
        g.rowWidth > 0
          ? Math.max(g.rowWidth * fullSwipeRatio, fullSwipeFloor)
          : fullSwipeFloor;
      gesture.current.pointerId = null;
      gesture.current.axis = "undecided";
      (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
      setDragging(false);

      if (!wasHorizontal) return;

      // Full swipe (measured from gesture start) fires the destructive action.
      if (-totalDx >= fullSwipeThreshold) {
        onFullSwipeRef.current();
        // Reset position; the row will typically unmount as a result.
        setOffset(0);
        setOpen(false);
        return;
      }

      // Settle open or closed based on the current revealed amount.
      const revealed = -offset;
      if (revealed >= revealThreshold) {
        setOffset(-actionsWidth);
        setOpen(true);
      } else {
        setOffset(0);
        setOpen(false);
      }
    },
    [fullSwipeRatio, fullSwipeFloor, revealThreshold, actionsWidth, offset],
  );

  return {
    offset,
    open,
    dragging,
    reducedMotion,
    close,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp: finishGesture,
      onPointerCancel: finishGesture,
      onClickCapture,
    },
  };
}
