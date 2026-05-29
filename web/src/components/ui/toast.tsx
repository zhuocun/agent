"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

export type ToastSeverity = "info" | "warning" | "error" | "success";

export type ToastAction = {
  label: string;
  onClick: () => void;
};

export type ToastInput = {
  severity: ToastSeverity;
  title: string;
  body?: string;
  actions?: ToastAction[];
  durationMs?: number;
};

export type ToastHandle = {
  dismiss: () => void;
};

type ToastRecord = ToastInput & {
  id: number;
};

type Listener = () => void;

let nextId = 0;
let queue: readonly ToastRecord[] = [];
const listeners = new Set<Listener>();
const EMPTY_QUEUE: readonly ToastRecord[] = [];

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): readonly ToastRecord[] {
  return queue;
}

// useSyncExternalStore requires a stable empty reference on the server pass —
// returning the live `queue` would risk a hydration mismatch if a toast is
// enqueued before hydration completes.
function getServerSnapshot(): readonly ToastRecord[] {
  return EMPTY_QUEUE;
}

function dismiss(id: number): void {
  const before = queue.length;
  queue = queue.filter((t) => t.id !== id);
  if (queue.length !== before) emit();
}

// Module-scoped queue + tiny pub/sub. Lives outside React so non-component code
// (e.g. handler closures inside chat-thread) can call showToast without
// importing a context. SSR-safe because nothing here touches `window`.
export function showToast(input: ToastInput): ToastHandle {
  const id = nextId++;
  const record: ToastRecord = { ...input, id };
  queue = [...queue, record];
  emit();
  return {
    dismiss: () => dismiss(id),
  };
}

function defaultDurationFor(severity: ToastSeverity): number | null {
  // Warning and error are persistent (manual dismiss only) so the user has time
  // to read the failure reason before deciding whether to retry — info/success
  // are transient because they confirm a transition, not a problem.
  if (severity === "warning" || severity === "error") return null;
  return 5000;
}

const SEVERITY_ICON = {
  info: Info,
  warning: AlertTriangle,
  error: AlertOctagon,
  success: CheckCircle2,
} as const;

const SEVERITY_LABEL: Record<ToastSeverity, string> = {
  info: "Information",
  warning: "Warning",
  error: "Error",
  success: "Success",
};

// Tone tokens. Error/warning use their semantic role tokens at a quiet 10%
// background tint with full-saturation foreground — destructive red is never
// used as a flood fill (anti-pattern A). Success uses the inverted neutral
// pair rather than a green background, matching the "quiet success" rule.
// Info defers to the standard muted foreground so a routine confirmation never
// reads as a state change.
const SEVERITY_TONE: Record<ToastSeverity, string> = {
  info: "text-foreground [&_[data-toast-glyph]]:text-muted-foreground",
  warning:
    "text-foreground [&_[data-toast-glyph]]:text-warning before:absolute before:inset-y-3 before:left-0 before:w-[2px] before:rounded-r-full before:bg-warning/70",
  error:
    "text-foreground [&_[data-toast-glyph]]:text-destructive before:absolute before:inset-y-3 before:left-0 before:w-[2px] before:rounded-r-full before:bg-destructive/70",
  success:
    "text-foreground [&_[data-toast-glyph]]:text-success before:absolute before:inset-y-3 before:left-0 before:w-[2px] before:rounded-r-full before:bg-success/70",
};

function ToastItem({ toast }: { toast: ToastRecord }) {
  const Icon = SEVERITY_ICON[toast.severity];
  const duration = toast.durationMs ?? defaultDurationFor(toast.severity);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (duration === null) return;
    timerRef.current = window.setTimeout(() => {
      dismiss(toast.id);
    }, duration);
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [duration, toast.id]);

  // role=alert for error/warning so screen readers interrupt; status for
  // info/success so they queue politely behind the streamed-transition region.
  const role =
    toast.severity === "error" || toast.severity === "warning"
      ? "alert"
      : "status";

  return (
    <li
      role={role}
      aria-label={SEVERITY_LABEL[toast.severity]}
      className={cn(
        // Enter: a ToastItem mounts exactly when its record joins the queue —
        // the real "open" moment — so `animate-toast-in` (slide+fade from the
        // bottom edge, decel curve) fires once on mount. The shared util ships a
        // reduced-motion alternate that collapses to a pure cross-fade, so no
        // inline transform neutralizer is needed here. Exit is unchanged.
        "glass-strong pointer-events-auto relative flex w-full max-w-sm items-start gap-3 overflow-hidden rounded-2xl px-4 py-3 text-sm shadow-[var(--shadow-glass-key)] animate-toast-in transition-all duration-200 ease-out data-[state=closing]:opacity-0 motion-reduce:transition-none",
        SEVERITY_TONE[toast.severity],
      )}
    >
      <Icon
        data-toast-glyph
        aria-hidden
        className="mt-0.5 size-4 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <p className="font-medium leading-snug">{toast.title}</p>
        {toast.body ? (
          <p className="mt-1 text-muted-foreground leading-snug break-words">
            {toast.body}
          </p>
        ) : null}
        {toast.actions && toast.actions.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-3">
            {toast.actions.map((action, index) => (
              <button
                key={`${action.label}-${index}`}
                type="button"
                onClick={() => {
                  action.onClick();
                  dismiss(toast.id);
                }}
                className="rounded-full text-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
              >
                {action.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => dismiss(toast.id)}
        aria-label="Dismiss notification"
        className="-mr-1 -mt-1 inline-flex size-11 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
      >
        <X aria-hidden className="size-4" />
      </button>
    </li>
  );
}

export function Toaster() {
  // SSR-safe subscription: the server snapshot is a stable empty list so the
  // first render matches whether or not anything has been queued before
  // hydration, and the client subscription takes over after mount.
  const toasts = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  if (toasts.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 px-4 pb-[calc(var(--bottom-inset)+5rem)] pr-[max(env(safe-area-inset-right),1rem)] pl-[max(env(safe-area-inset-left),1rem)] md:inset-x-auto md:bottom-auto md:top-0 md:right-0 md:items-end md:pt-[max(env(safe-area-inset-top),1rem)] md:pb-0"
    >
      <ol className="flex w-full max-w-sm flex-col gap-2">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} />
        ))}
      </ol>
    </div>
  );
}
