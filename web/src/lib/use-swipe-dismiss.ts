"use client";

import { useCallback, useEffect, useRef, type PointerEvent } from "react";

import { haptic } from "@/lib/use-haptic";

export interface UseSwipeDismissOptions {
  /**
   * Whether the swipe gesture is currently active (the sheet is presented as a
   * bottom sheet, i.e. on mobile). When false the hook is inert and returns
   * no-op handlers so desktop / centered dialogs are never affected.
   */
  enabled: boolean;
  /**
   * Called when the user drags past the dismiss threshold (or flicks down with
   * enough velocity). Should close the dialog — e.g. `() => onOpenChange(false)`.
   */
  onDismiss: () => void;
  /**
   * Fraction of the sheet's own height the finger must travel before a release
   * dismisses it. Defaults to 0.25 (25%).
   */
  threshold?: number;
  /**
   * Downward velocity (px/ms) above which a release dismisses regardless of
   * distance, so a quick flick works. Defaults to 0.5.
   */
  velocityThreshold?: number;
}

/** Pointer handlers spread onto a draggable region. */
export interface SwipeRegionHandlers {
  onPointerDown: (event: PointerEvent<HTMLElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLElement>) => void;
  onPointerCancel: (event: PointerEvent<HTMLElement>) => void;
}

export interface UseSwipeDismissResult {
  /** Ref for the sheet element that gets translated by the drag. */
  sheetRef: React.RefObject<HTMLDivElement | null>;
  /**
   * Handlers for the always-draggable region (grabber + header). Dragging from
   * here always engages, regardless of inner scroll position.
   */
  handleProps: SwipeRegionHandlers;
  /**
   * Handlers for the sheet body / scroll region. A drag only engages when no
   * scrollable ancestor within the sheet is scrolled past its top, so we never
   * hijack inner scrolling.
   */
  contentProps: SwipeRegionHandlers;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Interactive swipe-to-dismiss for an iOS-style bottom sheet. Pointer-event
 * based (works for touch, pen, mouse), uses pointer capture so the gesture
 * survives the finger leaving the element, and never hijacks inner scrolling:
 * a drag only engages from the grabber/header, or from the body when its
 * scroll region is already at the top.
 *
 * Respects `prefers-reduced-motion`: when reduced motion is requested we skip
 * the live transform + spring-back and dismiss instantly once the threshold is
 * crossed (no animated translate).
 */
export function useSwipeDismiss({
  enabled,
  onDismiss,
  threshold = 0.25,
  velocityThreshold = 0.5,
}: UseSwipeDismissOptions): UseSwipeDismissResult {
  const sheetRef = useRef<HTMLDivElement | null>(null);

  // Mutable gesture state kept in a ref so move/up handlers don't re-render.
  const drag = useRef<{
    pointerId: number;
    startY: number;
    lastY: number;
    lastT: number;
    velocity: number;
    dragging: boolean;
    reduced: boolean;
  } | null>(null);

  const onDismissRef = useRef(onDismiss);
  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  const setTransform = useCallback((dy: number, withTransition: boolean) => {
    const el = sheetRef.current;
    if (!el) return;
    el.style.transition = withTransition
      ? "transform 0.35s var(--ease-ios-sheet)"
      : "none";
    el.style.transform = dy > 0 ? `translateY(${dy}px)` : "";
  }, []);

  const reset = useCallback(() => {
    const el = sheetRef.current;
    if (el) {
      // Spring back to rest, then clear inline overrides so the element's
      // own (Tailwind) transitions/transforms take over again.
      setTransform(0, true);
      const clear = () => {
        if (!sheetRef.current) return;
        sheetRef.current.style.transition = "";
        sheetRef.current.style.transform = "";
      };
      window.setTimeout(clear, 360);
    }
    drag.current = null;
  }, [setTransform]);

  const endGesture = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const state = drag.current;
      if (!state || state.pointerId !== event.pointerId) return;
      const el = sheetRef.current;
      try {
        (event.currentTarget as HTMLElement).releasePointerCapture(
          event.pointerId,
        );
      } catch {
        // capture may already be gone; ignore.
      }
      const dy = state.lastY - state.startY;
      const sheetHeight = el?.getBoundingClientRect().height ?? 0;
      const pastDistance = sheetHeight > 0 && dy > sheetHeight * threshold;
      const flicked = state.velocity > velocityThreshold;
      if (state.dragging && (pastDistance || flicked)) {
        // Let the close transition run from the current dragged position by
        // not springing back; base UI's ending-style handles the exit.
        if (el && !state.reduced) {
          el.style.transition = "";
          el.style.transform = "";
        }
        drag.current = null;
        haptic("light");
        onDismissRef.current();
        return;
      }
      reset();
    },
    [reset, threshold, velocityThreshold],
  );

  const begin = useCallback(
    (event: PointerEvent<HTMLElement>, fromHandle: boolean) => {
      if (!enabled) return;
      if (drag.current) return;
      // Only the primary button / single touch.
      if (event.button !== 0 && event.pointerType === "mouse") return;

      if (!fromHandle) {
        // Body drags only engage when no scrollable ancestor inside the sheet
        // is scrolled away from the top — otherwise we'd steal the scroll. Walk
        // from the target up to (but not past) the sheet element.
        const sheet = sheetRef.current;
        let node = event.target as HTMLElement | null;
        while (node && node !== sheet) {
          if (node.scrollHeight > node.clientHeight && node.scrollTop > 0) {
            return;
          }
          node = node.parentElement;
        }
      }

      const reduced = prefersReducedMotion();
      drag.current = {
        pointerId: event.pointerId,
        startY: event.clientY,
        lastY: event.clientY,
        lastT: event.timeStamp,
        velocity: 0,
        dragging: false,
        reduced,
      };
      try {
        (event.currentTarget as HTMLElement).setPointerCapture(
          event.pointerId,
        );
      } catch {
        // setPointerCapture can throw if the pointer is already gone.
      }
    },
    [enabled],
  );

  const move = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const state = drag.current;
      if (!state || state.pointerId !== event.pointerId) return;
      const dy = event.clientY - state.startY;
      // Track velocity (px/ms) for flick detection.
      const dt = event.timeStamp - state.lastT;
      if (dt > 0) {
        state.velocity = (event.clientY - state.lastY) / dt;
      }
      state.lastY = event.clientY;
      state.lastT = event.timeStamp;

      if (dy <= 0) {
        // Dragging up — ignore; let it spring to rest.
        if (state.dragging && !state.reduced) setTransform(0, false);
        return;
      }
      // We are committed to a downward drag.
      if (!state.dragging) state.dragging = true;
      // Prevent the page/inner content from scrolling/selecting mid-drag.
      event.preventDefault();
      if (!state.reduced) {
        // Rubber-band slightly so the sheet feels physical.
        setTransform(dy, false);
      }
    },
    [setTransform],
  );

  // Inert no-op handler keeps disabled (desktop) call sites simple.
  const noop = useCallback(() => {}, []);

  const handleProps: SwipeRegionHandlers = {
    onPointerDown: enabled ? (e) => begin(e, true) : noop,
    onPointerMove: enabled ? move : noop,
    onPointerUp: enabled ? endGesture : noop,
    onPointerCancel: enabled ? endGesture : noop,
  };
  const contentProps: SwipeRegionHandlers = {
    onPointerDown: enabled ? (e) => begin(e, false) : noop,
    onPointerMove: enabled ? move : noop,
    onPointerUp: enabled ? endGesture : noop,
    onPointerCancel: enabled ? endGesture : noop,
  };

  return { sheetRef, handleProps, contentProps };
}
