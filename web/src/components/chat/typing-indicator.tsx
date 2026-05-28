"use client";

import { cn } from "@/lib/utils";

export function TypingIndicator() {
  return (
    <div
      aria-hidden="true"
      className="inline-flex w-fit items-center gap-1.5"
    >
      <span className="flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn(
              "size-1.5 rounded-full bg-foreground/30",
              "motion-safe:animate-bounce",
            )}
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </span>
      <span className="text-xs font-medium text-muted-foreground">
        Thinking…
      </span>
    </div>
  );
}
