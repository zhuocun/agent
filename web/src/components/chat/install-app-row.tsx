"use client";

import { useState, useSyncExternalStore } from "react";
import { MonitorDown, Share, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toast";
import { promptPwaInstall, usePwaInstallMode } from "@/lib/use-pwa-install";

const DISMISS_KEY = "olune.install-hint.dismissed";

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

const noopSubscribe = (): (() => void) => () => {};

// Quiet "Install app" row in the sidebar footer. It lives in the navigation
// surface rather than floating over the chat, so it can never cover the
// composer, suggestion chips, or jump-to-latest. Renders only when the browser
// can actually install (Chromium deferred prompt, or iOS Safari tab).
export function InstallAppRow(): React.JSX.Element | null {
  const mode = usePwaInstallMode();
  const storedDismissed = useSyncExternalStore(
    noopSubscribe,
    readDismissed,
    () => true,
  );
  const [dismissed, setDismissed] = useState(false);

  if (mode === null || storedDismissed || dismissed) return null;

  const install = (): void => {
    if (mode === "prompt") {
      void promptPwaInstall();
      return;
    }
    showToast({
      severity: "info",
      title: "Install Olune",
      body: "In Safari, tap Share, then Add to Home Screen.",
      durationMs: 10_000,
    });
  };

  const dismiss = (): void => {
    setDismissed(true);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Storage blocked (private mode): hide for this session only.
    }
  };

  const Icon = mode === "ios" ? Share : MonitorDown;

  return (
    <div data-testid="install-app-row" className="flex items-center gap-1">
      <Button
        type="button"
        variant="sidebar"
        size="sidebar"
        onClick={install}
        className="min-w-0 flex-1 text-muted-foreground hover:text-foreground"
      >
        <Icon className="size-4" aria-hidden />
        <span className="truncate">Install app</span>
      </Button>
      <Button
        type="button"
        variant="ghost"
        aria-label="Dismiss install suggestion"
        onClick={dismiss}
        className="size-9 shrink-0 rounded-full p-0 text-muted-foreground hover:text-foreground [@media(hover:none)]:size-11"
      >
        <X className="size-4" aria-hidden />
      </Button>
    </div>
  );
}
