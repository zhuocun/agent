"use client";

import { useEffect, useState } from "react";

export interface VisualViewportState {
  /** Current visual viewport height in CSS px (shrinks when the iOS keyboard opens). */
  height: number;
  /** Visual viewport offset from the top of the layout viewport. */
  offsetTop: number;
  /**
   * Pixels of the layout viewport currently obscured at the bottom by an
   * on-screen keyboard / overlay. `0` when nothing is covering the content.
   */
  keyboardInset: number;
}

const EMPTY_STATE: VisualViewportState = {
  height: 0,
  offsetTop: 0,
  keyboardInset: 0,
};

function readState(): VisualViewportState {
  if (typeof window === "undefined" || !window.visualViewport) {
    return EMPTY_STATE;
  }
  const vv = window.visualViewport;
  const keyboardInset = Math.max(
    0,
    window.innerHeight - vv.height - vv.offsetTop,
  );
  return { height: vv.height, offsetTop: vv.offsetTop, keyboardInset };
}

/**
 * Tracks the `visualViewport` so callers can react to the iOS software keyboard,
 * which (unlike Android) does NOT shrink `dvh`/layout viewport. SSR-safe: returns
 * a zeroed state when there is no `window`/`visualViewport`, and a no-op there.
 */
export function useVisualViewport(): VisualViewportState {
  // Lazy initializer reads the real viewport once on the client (and stays
  // zeroed during SSR) so we never need a bare setState in the effect body.
  const [state, setState] = useState<VisualViewportState>(readState);

  useEffect(() => {
    const vv =
      typeof window !== "undefined" ? window.visualViewport : null;
    if (!vv) return;

    // Event-driven sync (resize/scroll fire on keyboard show/hide and panning).
    // This is a listener callback, not a render-time/bare-effect setState.
    const update = (): void => {
      setState(readState());
    };

    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);

  return state;
}
