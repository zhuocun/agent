"use client";

import { cn } from "@/lib/utils";

// Pre-first-token indicator (PRD 01 §4.1, §5.1; PRD 06 §5.2).
// Shown from send until the first content token, then replaced by streamed
// content (never shown alongside content). A separate polite status region
// announces generation status (PRD 06 §3.5 / PRD 01 §5.7), so the visual here
// is purely decorative and marked aria-hidden.
//
// Motion: a soft shimmer pill with three bouncing dots. Under
// prefers-reduced-motion the global stylesheet (globals.css §3.4) neutralizes
// animations; the motion-safe: gate keeps the static fallback intentional — a
// "Thinking…" label with three steady muted dots still clearly reads as an
// active, in-progress state rather than a frozen artifact.
export function TypingIndicator() {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "inline-flex w-fit items-center gap-2 rounded-full px-3 py-1.5",
        "bg-muted text-muted-foreground",
        // Shimmer sweep — only when motion is allowed.
        "bg-[length:200%_100%] motion-safe:bg-gradient-to-r",
        "motion-safe:from-muted motion-safe:via-accent motion-safe:to-muted",
        "motion-safe:animate-shimmer",
      )}
    >
      <span className="flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn(
              "size-1.5 rounded-full bg-muted-foreground/70",
              "motion-safe:animate-bounce",
            )}
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </span>
      <span className="text-xs font-medium">Thinking…</span>
    </div>
  );
}
