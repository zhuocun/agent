"use client";

import { useEffect, useRef, useState } from "react";
import { Share, X } from "lucide-react";

import { cn } from "@/lib/utils";

const DISMISS_KEY = "olune.ios-install-hint.dismissed";

// Follow-up suggestion chips rendered under the last assistant message. On
// short threads they sit right where the fixed coachmark parks, so the pill
// yields (goes invisible) whenever its rect intersects any chip group's rect.
const FOLLOW_UP_CHIPS_SELECTOR = '[data-testid="follow-up-chips"]';

// The welcome state's suggestion rail. While it is mounted the fixed coachmark
// (anchored above the composer) overlaps the last chip on short viewports —
// iPhone 13 (390×844) occludes the 4th suggestion. The role/name pair is
// load-bearing for the e2e suite (welcome-screen.tsx), so it doubles as a
// stable hook to detect the rail's presence.
const WELCOME_RAIL_SELECTOR = 'ul[aria-label="Suggested prompts"]';

// The chat composer's textarea. Its presence tells the coachmark whether the
// bottom of the viewport carries the composer capsule (chat surfaces) or is
// free (composer-less surfaces like /status), which drives the pill's parking
// offset. The testid is load-bearing for the e2e suite (composer.tsx), so it
// doubles as a stable hook here.
const COMPOSER_SELECTOR = '[data-testid="composer-textarea"]';

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
  const [chipsOverlap, setChipsOverlap] = useState(false);
  const [composerPresent, setComposerPresent] = useState(true);
  const pillRef = useRef<HTMLDivElement | null>(null);

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
  // The same observer tracks the composer so the pill knows whether the bottom
  // of the viewport carries the composer capsule or is free to park against.
  useEffect(() => {
    if (typeof document === "undefined") return;
    const sync = (): void => {
      setWelcomeRailVisible(
        document.querySelector(WELCOME_RAIL_SELECTOR) !== null
      );
      setComposerPresent(
        document.querySelector(COMPOSER_SELECTOR) !== null
      );
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  // Yield to follow-up chips: whenever the pill's fixed rect intersects any
  // chip group (short threads park the chips exactly where the pill floats),
  // hide the pill instead of occluding tappable suggestions. The pill stays
  // mounted (visibility only) so its rect remains measurable and it can
  // reappear the moment the chips scroll clear or unmount. Rechecked on DOM
  // mutations (chips mount/unmount while streaming), scrolls (capture — the
  // chat list scrolls an inner container), and resizes, coalesced to one
  // measurement per frame.
  useEffect(() => {
    if (!visible || typeof document === "undefined") return;
    let frame = 0;
    const measure = (): void => {
      frame = 0;
      const pill = pillRef.current;
      if (!pill) return;
      const pillRect = pill.getBoundingClientRect();
      const chipGroups = document.querySelectorAll(FOLLOW_UP_CHIPS_SELECTOR);
      let overlap = false;
      for (const chips of chipGroups) {
        const rect = chips.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        if (
          rect.left < pillRect.right &&
          rect.right > pillRect.left &&
          rect.top < pillRect.bottom &&
          rect.bottom > pillRect.top
        ) {
          overlap = true;
          break;
        }
      }
      setChipsOverlap(overlap);
    };
    const schedule = (): void => {
      if (frame === 0) frame = window.requestAnimationFrame(measure);
    };
    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("scroll", schedule, {
      capture: true,
      passive: true,
    });
    window.addEventListener("resize", schedule);
    return () => {
      if (frame !== 0) window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("scroll", schedule, { capture: true });
      window.removeEventListener("resize", schedule);
    };
  }, [visible]);

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
      ref={pillRef}
      data-testid="install-coachmark"
      role="status"
      aria-live="polite"
      className={cn(
        // Yielding to overlapping follow-up chips uses visibility (not
        // unmount) so the rect stays measurable for the intersection check.
        chipsOverlap && "invisible",
        "pointer-events-auto fixed left-[max(env(safe-area-inset-left),0.75rem)] right-[max(env(safe-area-inset-right),0.75rem)] z-30",
        // Sit ABOVE the composer capsule, not on top of it. `--bottom-inset` is
        // the safe-area floor; the composer chrome occupies ~5rem above it (the
        // same offset the toast stack clears), so reuse it here.
        // Clear the composer capsule, AI disclosure, and follow-up chips —
        // 5rem was too tight and the pill overlapped the send field on phones.
        // Park at +13rem so the pill sits above jump-to-latest (+9.5rem, h-11)
        // — both are z-30 and the coachmark mounts after app children in
        // layout.tsx, so any vertical overlap would steal taps from the button.
        // Composer-less surfaces (/status) have no capsule or jump-to-latest to
        // clear, so the pill parks at the safe-area floor instead of floating
        // 13rem up into empty page.
        composerPresent
          ? "bottom-[calc(var(--bottom-inset)+13rem)]"
          : "bottom-[var(--bottom-inset)]",
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
          "text-muted-foreground transition-transform hover:bg-accent hover:text-foreground",
          "active:scale-[0.96] active:duration-[70ms] motion-reduce:active:scale-100",
          "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
        )}
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
