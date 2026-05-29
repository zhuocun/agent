"use client";

import { useEffect, useState } from "react";
import { Share, X } from "lucide-react";

import { cn } from "@/lib/utils";

const DISMISS_KEY = "olune.ios-install-hint.dismissed";

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

  const dismiss = (): void => {
    setVisible(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore
    }
  };

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "pointer-events-auto fixed inset-x-3 z-40",
        "bottom-[calc(env(safe-area-inset-bottom)+0.75rem)]",
        "mx-auto flex max-w-md items-center gap-3 rounded-2xl",
        "border border-border bg-popover/95 px-3.5 py-2.5",
        "text-popover-foreground shadow-float backdrop-blur"
      )}
    >
      <Share
        aria-hidden
        className="size-4 shrink-0 text-brand"
        strokeWidth={2}
      />
      <p className="min-w-0 flex-1 text-[13px] leading-snug">
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
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        )}
      >
        <X aria-hidden className="size-4" />
      </button>
    </div>
  );
}
