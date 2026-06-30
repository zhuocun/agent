"use client";

import { useCallback, useEffect, useRef } from "react";

import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { useVisualViewport } from "@/lib/use-visual-viewport";
import { haptic } from "@/lib/use-haptic";
import { cn } from "@/lib/utils";

// Touch-only iOS-style "drag from the left edge to reveal the drawer". A
// pointer that lands inside this many px of the main column's left edge arms
// the gesture; horizontal-dominant movement past the threshold commits and
// pops the drawer open. We claim only horizontal-dominant drags so vertical
// scrolling is never hijacked. The handlers live on <main> itself (not an
// overlay) so taps in the edge zone still reach the message content beneath.
const EDGE_ZONE_PX = 20;
const EDGE_OPEN_THRESHOLD_PX = 32;
const EDGE_AXIS_SLOP_PX = 8;

export interface AppShellProps {
  sidebar: React.ReactNode; // a <Sidebar .../> element
  sidebarOpen: boolean; // desktop: persistent rail shown?
  mobileNavOpen: boolean; // mobile: drawer open?
  onMobileNavOpenChange: (open: boolean) => void;
  children: React.ReactNode; // the chat column
}

export function AppShell({
  sidebar,
  sidebarOpen,
  mobileNavOpen,
  onMobileNavOpenChange,
  children,
}: AppShellProps): React.JSX.Element {
  const { height, offsetTop, keyboardInset } = useVisualViewport();

  const edgeSwipe = useEdgeSwipe(
    useCallback(() => {
      haptic("selection");
      onMobileNavOpenChange(true);
    }, [onMobileNavOpenChange]),
    mobileNavOpen,
  );

  // iOS keyboard handling: on iOS the soft keyboard does NOT shrink `dvh`, so a
  // bottom-anchored composer slides under the keyboard. When the keyboard is up
  // (`keyboardInset > 0`) we pin the shell to the visual viewport's height and
  // top offset so the composer stays visible. No-op on desktop / where there is
  // no `visualViewport` (keyboardInset stays 0), so `h-dvh` governs as before.
  const keyboardOpen = keyboardInset > 0;
  const shellStyle: React.CSSProperties | undefined = keyboardOpen
    ? { height: `${height}px`, transform: `translateY(${offsetTop}px)` }
    : undefined;

  // Android hardware Back closes the mobile drawer instead of leaving the page.
  // We push a history entry when the drawer opens and pop it on close; a
  // `popstate` listener (the Back button) drives the drawer shut.
  const pushedRef = useRef(false);
  const onCloseRef = useRef(onMobileNavOpenChange);
  // Keep the latest close handler in a ref without reading/writing it during
  // render (which React forbids). The popstate listener reads `onCloseRef`.
  useEffect(() => {
    onCloseRef.current = onMobileNavOpenChange;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;

    if (mobileNavOpen) {
      window.history.pushState({ apertureMobileNav: true }, "");
      pushedRef.current = true;

      const onPopState = (): void => {
        pushedRef.current = false;
        onCloseRef.current(false);
      };
      window.addEventListener("popstate", onPopState);
      return () => {
        window.removeEventListener("popstate", onPopState);
        // Programmatic close (not via Back): unwind the entry we pushed.
        if (pushedRef.current) {
          pushedRef.current = false;
          window.history.back();
        }
      };
    }
    return;
  }, [mobileNavOpen]);

  return (
    <div
      className="flex h-dvh w-full overflow-hidden bg-background"
      style={shellStyle}
    >
      <aside
        aria-hidden={!sidebarOpen}
        inert={!sidebarOpen ? true : undefined}
        className={cn(
          // Left safe-area inset so the desktop rail clears a landscape notch;
          // the main column owns its own insets via the header/composer.
          "hidden shrink-0 overflow-hidden pl-[env(safe-area-inset-left)] transition-[width] duration-200 md:flex md:flex-col",
          sidebarOpen ? "md:w-72" : "pointer-events-none md:w-0"
        )}
      >
        {sidebar}
      </aside>

      <Drawer open={mobileNavOpen} onOpenChange={onMobileNavOpenChange}>
        <DrawerContent
          side="left"
          showClose={true}
          className="w-72 pl-[env(safe-area-inset-left)]"
        >
          {sidebar}
        </DrawerContent>
      </Drawer>

      <main
        className="relative flex min-w-0 flex-1 flex-col overflow-hidden"
        {...edgeSwipe}
      >
        {children}
      </main>
    </div>
  );
}

interface EdgeSwipeHandlers {
  onPointerDown: (e: React.PointerEvent<HTMLElement>) => void;
  onPointerMove: (e: React.PointerEvent<HTMLElement>) => void;
  onPointerUp: () => void;
  onPointerCancel: () => void;
}

/**
 * Edge-swipe gesture for the main column. Returns pointer handlers to spread
 * onto `<main>` — no overlay element, so taps near the left edge land on the
 * content as normal; only an arming drag that starts inside the edge zone and
 * turns horizontal-dominant opens the drawer.
 */
function useEdgeSwipe(onOpen: () => void, disabled: boolean): EdgeSwipeHandlers {
  const gesture = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    axis: "undecided" | "horizontal" | "vertical";
    committed: boolean;
  } | null>(null);

  const onOpenRef = useRef(onOpen);
  useEffect(() => {
    onOpenRef.current = onOpen;
  });

  const reset = useCallback(() => {
    gesture.current = null;
  }, []);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (disabled) return;
      // Touch / pen only — desktop mouse uses the sidebar rail directly.
      if (e.pointerType === "mouse") return;
      // Mobile drawer only: at md+ widths the persistent rail owns navigation
      // (the old overlay was `md:hidden`; this check preserves that gate).
      if (window.matchMedia("(min-width: 768px)").matches) return;
      // Arm only when the pointer lands inside the edge zone of the main
      // column itself, so taps/drags elsewhere are never intercepted.
      const mainLeft = e.currentTarget.getBoundingClientRect().left;
      if (e.clientX - mainLeft > EDGE_ZONE_PX) return;
      gesture.current = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        axis: "undecided",
        committed: false,
      };
    },
    [disabled],
  );

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLElement>) => {
    const g = gesture.current;
    if (!g || g.pointerId !== e.pointerId || g.committed) return;
    const dx = e.clientX - g.startX;
    const dy = e.clientY - g.startY;

    if (g.axis === "undecided") {
      if (Math.abs(dx) < EDGE_AXIS_SLOP_PX && Math.abs(dy) < EDGE_AXIS_SLOP_PX) {
        return;
      }
      if (Math.abs(dx) > Math.abs(dy) && dx > 0) {
        g.axis = "horizontal";
      } else {
        // Vertical or leftward drag — release the gesture so the main column
        // keeps owning the scroll / horizontal swipes for child surfaces.
        g.axis = "vertical";
        return;
      }
    }

    if (g.axis === "horizontal" && dx >= EDGE_OPEN_THRESHOLD_PX) {
      g.committed = true;
      onOpenRef.current();
    }
  }, []);

  return {
    onPointerDown,
    onPointerMove,
    onPointerUp: reset,
    onPointerCancel: reset,
  };
}
