"use client";

import { useEffect, useRef } from "react";

import { AiDisclosure } from "@/components/chat/ai-disclosure";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { useVisualViewport } from "@/lib/use-visual-viewport";
import { cn } from "@/lib/utils";

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
        className={cn(
          // Left safe-area inset so the desktop rail clears a landscape notch;
          // the main column owns its own insets via the header/composer.
          "hidden shrink-0 overflow-hidden pl-[env(safe-area-inset-left)] transition-[width] duration-200 md:flex md:flex-col",
          sidebarOpen ? "md:w-72" : "md:w-0"
        )}
      >
        {sidebar}
      </aside>

      <Drawer open={mobileNavOpen} onOpenChange={onMobileNavOpenChange}>
        <DrawerContent
          side="left"
          showClose={false}
          className="w-72 pl-[env(safe-area-inset-left)]"
        >
          {sidebar}
        </DrawerContent>
      </Drawer>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>

      <AiDisclosure />
    </div>
  );
}
