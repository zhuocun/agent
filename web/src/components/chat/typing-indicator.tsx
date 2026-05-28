"use client";

import { cn } from "@/lib/utils";

export function TypingIndicator() {
  return (
    <div
      aria-hidden="true"
      className="inline-flex w-fit items-center gap-1.5"
    >
      <span
        className={cn(
          "size-1.5 rounded-full bg-foreground/30",
          "motion-safe:animate-pulse-soft",
        )}
      />
      <span className="text-xs font-medium text-muted-foreground">
        Thinking…
      </span>
    </div>
  );
}
