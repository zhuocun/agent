"use client";

import { useSyncExternalStore } from "react";

// Chromium's install event. Not in lib.dom yet.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export type PwaInstallMode =
  // Chromium handed us a deferred prompt: one tap installs.
  | "prompt"
  // iOS Safari has no install API; the user must use Share → Add to Home Screen.
  | "ios"
  | null;

let deferredPrompt: BeforeInstallPromptEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (window.navigator as { standalone?: boolean }).standalone === true
  );
}

// UA sniff is the only option here: iOS Safari has no `beforeinstallprompt`.
function isIosSafari(): boolean {
  const ua = window.navigator.userAgent;
  const isIos =
    /iPad|iPhone|iPod/.test(ua) ||
    // iPadOS 13+ identifies as Mac; gate on touch points too.
    (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
  return isIos && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua);
}

// Listen at module load, not on mount: the event can fire before hydration
// and is never re-dispatched.
if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event as BeforeInstallPromptEvent;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    installed = true;
    emit();
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): PwaInstallMode {
  if (installed || isStandalone()) return null;
  if (deferredPrompt) return "prompt";
  return isIosSafari() ? "ios" : null;
}

function getServerSnapshot(): PwaInstallMode {
  return null;
}

/** How (and whether) this browser can install Olune right now. */
export function usePwaInstallMode(): PwaInstallMode {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Shows Chromium's native install sheet. Resolves true if accepted. */
export async function promptPwaInstall(): Promise<boolean> {
  const event = deferredPrompt;
  if (!event) return false;
  // A deferred prompt can only be used once.
  deferredPrompt = null;
  emit();
  await event.prompt();
  const { outcome } = await event.userChoice;
  return outcome === "accepted";
}
