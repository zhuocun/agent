"use client";

import { useEffect, useState } from "react";
import { Share, X } from "lucide-react";

import { cn } from "@/lib/utils";

const DISMISS_KEY = "olune.ios-install-hint.dismissed";

// The welcome state's suggestion rail. While it is mounted the fixed coachmark
// (anchored above the composer) overlaps the last chip on short viewports —
// iPhone 13 (390×844) occludes the 4th suggestion. The role/name pair is
// load-bearing for the e2e suite (welcome-screen.tsx), so it doubles as a
// stable hook to detect the rail's presence.
const WELCOME_RAIL_SELECTOR = 'ul[aria-label="Suggested prompts"]';

// Detect iOS Safari running in a browser tab (not an installed PWA). The UA
// sniff is the accepted approach for this narrow case — iOS Safari does not
// implement `beforeinstallprompt`, so there is no feature-detect alternative.
function isIosSafariTab(): boolean {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent;
  const isIos = /iPad|iPhone|iPod/.test(ua);
  // iPadOS 13+ identifies as Mac; gate on touch points too.
  const isIpadOs =
    ua.includes("Macintosh") && navigator.maxTouchPoints > 1;
  if (!isIos && !isIpadOs) return false;

  const isSafari =
    /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua);
  if (!isSafari) return false;

  // matchMedia is reliable here; iOS sets `standalone` on `navigator` too.
  const standaloneMedia = window.matchMedia(
    "(display-mode: standalone)"
  ).matches;
  const standaloneNav =
    "standalone" in window.navigator &&
    (window.navigator as { standalone?: boolean }).standalone === true;
  return !standaloneMedia && !standaloneNav;
}

export function InstallCoachmark(): React.JSX.Element | null {
  const [visible, setVisible] = useState(false);
  const [welcomeRailVisible, setWelcomeRailVisible] = useState(false);
  const [shortViewport, setShortViewport] = useState(false);

  useEffect(() => {
    if (!isIosSafariTab()) return;
    try {
      if (window.localStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      // localStorage blocked (private mode) — show once per session anyway.
    }
    // Defer a beat so the hint does not race the first paint of the chat.
    const t = window.setTimeout(() => setVisible(true), 1200);
    return () => window.clearTimeout(t);
  }, []);

  // Hide on short viewports where the fixed pill would crowd the composer and
  // follow-up chips once the welcome rail unmounts (iPhone SE 320×568).
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(max-height: 599px)");
    const sync = (): void => setShortViewport(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  // Track the welcome suggestion rail so the coachmark yields the bottom of the
  // viewport to it (it would otherwise occlude the last chip on short phones).
  // A MutationObserver keeps this live: the rail unmounts once the user sends a
  // prompt, at which point the hint is free to appear. Surfaces without a rail
  // (e.g. /status) keep this false, so the coachmark shows there as before.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const sync = (): void => {
      setWelcomeRailVisible(
        document.querySelector(WELCOME_RAIL_SELECTOR) !== null
      );
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  const dismiss = (): void => {
    setVisible(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore
    }
  };

  if (!visible || welcomeRailVisible || shortViewport) return null;

  return (
    <div
      data-testid="install-coachmark"
      role="status"
      aria-live="polite"
      className={cn(
        "pointer-events-auto fixed inset-x-3 z-30",
        // Sit ABOVE the composer capsule, not on top of it. `--bottom-inset` is
        // the safe-area floor; the composer chrome occupies ~5rem above it (the
        // same offset the toast stack clears), so reuse it here.
        // Clear the composer capsule, AI disclosure, and follow-up chips —
        // 5rem was too tight and the pill overlapped the send field on phones.
        // Park at +13rem so the pill sits above jump-to-latest (+9.5rem, h-11)
        // — both are z-30 and the coachmark mounts after app children in
        // layout.tsx, so any vertical overlap would steal taps from the button.
        "bottom-[calc(var(--bottom-inset)+13rem)]",
        "mx-auto flex max-w-md items-center gap-3 rounded-2xl",
        // `glass-regular` supplies the translucent material: saturated/
        // contrasted backdrop-filter, the inset hairline rim, the top highlight,
        // and the ambient+key shadow. So we drop the old flat `bg-popover/95`,
        // the explicit `border border-border`, and `shadow-float` — the utility
        // carries all three. Only layout/padding/foreground stay local.
        "glass-regular px-3.5 py-2.5 text-popover-foreground"
      )}
    >
      <Share
        aria-hidden
        className="size-4 shrink-0 text-brand"
        strokeWidth={2}
      />
      <p className="min-w-0 flex-1 ui-body leading-snug">
        Install Olune: tap{" "}
        <span className="font-medium">Share</span>, then{" "}
        <span className="font-medium">Add to Home Screen</span>.
      </p>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss install hint"
        className={cn(
          "inline-flex size-11 shrink-0 items-center justify-center rounded-full",
          "text-muted-foreground hover:bg-accent hover:text-foreground",
          "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
        )}
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
