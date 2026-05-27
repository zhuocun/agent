"use client";

import { useEffect, useRef, useState } from "react";
import { Brain, ChevronDown } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

// Reasoning / "thinking" panel (PRD 01 §4.2, §5.2).
// A collapsible, visually subordinate panel rendered above an assistant answer.
export interface ReasoningPanelProps {
  text: string;
  durationSec?: number;
  isStreaming: boolean; // true while reasoning tokens are still arriving
}

export function ReasoningPanel({
  text,
  durationSec,
  isStreaming,
}: ReasoningPanelProps) {
  // Open is seeded from isStreaming (Thinking auto-expands; Done auto-collapses).
  // Once the user toggles manually, we respect their choice for the session and
  // stop auto-syncing to isStreaming (§5.2: "remembered for the session").
  const [open, setOpen] = useState(isStreaming);
  const userToggled = useRef(false);
  const prevStreaming = useRef(isStreaming);

  useEffect(() => {
    if (prevStreaming.current !== isStreaming) {
      prevStreaming.current = isStreaming;
      if (!userToggled.current) {
        // Auto: expand while thinking, collapse on completion.
        setOpen(isStreaming);
      }
    }
  }, [isStreaming]);

  const handleOpenChange = (next: boolean) => {
    userToggled.current = true;
    setOpen(next);
  };

  const label = isStreaming
    ? "Thinking…"
    : durationSec && durationSec > 0
      ? `Thought for ${formatDuration(durationSec)}`
      : "Reasoning";

  return (
    <Collapsible
      open={open}
      onOpenChange={handleOpenChange}
      className={cn(
        "overflow-hidden rounded-lg border border-border/60",
        "bg-reasoning-muted text-reasoning-muted-foreground",
      )}
    >
      <CollapsibleTrigger
        aria-label={open ? "Hide reasoning" : "Show reasoning"}
        className={cn(
          "group/reasoning flex min-h-10 w-full items-center gap-2 px-3 py-2",
          "text-left text-sm font-medium text-reasoning-muted-foreground",
          "transition-colors hover:bg-accent/40",
          "outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
        )}
      >
        <Brain
          aria-hidden="true"
          className={cn(
            "size-4 shrink-0 text-reasoning-muted-foreground",
            isStreaming && "motion-safe:animate-pulse",
          )}
        />

        {isStreaming ? (
          <span
            className={cn(
              "bg-gradient-to-r from-reasoning-muted-foreground via-foreground to-reasoning-muted-foreground",
              "bg-[length:200%_100%] bg-clip-text text-transparent",
              "motion-safe:animate-shimmer",
            )}
          >
            {label}
          </span>
        ) : (
          <span>{label}</span>
        )}

        <ChevronDown
          aria-hidden="true"
          className={cn(
            "ml-auto size-4 shrink-0 text-reasoning-muted-foreground transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </CollapsibleTrigger>

      {/* keepMounted preserves the streamed text node so live updates and the
          height transition stay smooth even while collapsed. */}
      <CollapsibleContent
        keepMounted
        className={cn(
          "overflow-hidden",
          "transition-[height] duration-200 ease-out",
          "h-[var(--collapsible-panel-height)] data-[starting-style]:h-0 data-[ending-style]:h-0",
        )}
      >
        <p
          className={cn(
            "px-3 pb-3 pt-1 text-sm leading-relaxed",
            "whitespace-pre-wrap break-words text-reasoning-muted-foreground",
          )}
        >
          {text}
        </p>
      </CollapsibleContent>
    </Collapsible>
  );
}

function formatDuration(durationSec?: number): string {
  const seconds = Math.max(0, Math.round(durationSec ?? 0));
  return `${seconds}s`;
}
