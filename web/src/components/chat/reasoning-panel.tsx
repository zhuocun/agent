"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export interface ReasoningPanelProps {
  text: string;
  durationSec?: number;
  isStreaming: boolean;
  defaultOpen?: boolean;
}

export function ReasoningPanel({
  text,
  durationSec,
  isStreaming,
  defaultOpen = false,
}: ReasoningPanelProps) {
  const [open, setOpen] = useState(isStreaming || defaultOpen);
  const userToggled = useRef(false);
  const prevStreaming = useRef(isStreaming);

  useEffect(() => {
    if (prevStreaming.current !== isStreaming) {
      prevStreaming.current = isStreaming;
      if (!userToggled.current) {
        setOpen(isStreaming || defaultOpen);
      }
    }
  }, [isStreaming, defaultOpen]);

  const handleOpenChange = (next: boolean) => {
    userToggled.current = true;
    setOpen(next);
  };

  const streamingLabel = "Thinking…";
  const settledLabel =
    durationSec && durationSec > 0
      ? `Reasoned for ${formatDuration(durationSec)}`
      : "Reasoning";

  return (
    <Collapsible
      open={open}
      onOpenChange={handleOpenChange}
      // E2E target: the streaming spec asserts reasoning text streams in;
      // testid avoids depending on the localized "Reasoning"/"Thinking…" label.
      data-testid="reasoning-panel"
      className="text-muted-foreground"
    >
      <CollapsibleTrigger
        className={cn(
          "group/reasoning-trigger inline-flex items-center gap-1 text-left text-xs text-muted-foreground",
          "bg-transparent p-0 underline-offset-2",
          "outline-none focus-visible:underline",
        )}
      >
        {/* Both labels share the same grid cell so the trigger's intrinsic
            width snaps to the longer one and the cross-fade has no horizontal
            shift; opacity tweens in lockstep with the body collapse below. */}
        <span className="relative inline-grid">
          <span
            aria-hidden={!isStreaming}
            className={cn(
              "[grid-area:1/1] transition-opacity duration-200 ease-out",
              isStreaming ? "opacity-100" : "opacity-0",
              "bg-gradient-to-r from-muted-foreground/70 via-foreground/80 to-muted-foreground/70",
              "bg-[length:200%_100%] bg-clip-text text-transparent",
              "motion-safe:animate-shimmer",
            )}
          >
            {streamingLabel}
          </span>
          <span
            aria-hidden={isStreaming}
            className={cn(
              "[grid-area:1/1] transition-opacity duration-200 ease-out",
              isStreaming ? "opacity-0" : "opacity-100",
            )}
          >
            {settledLabel}
          </span>
        </span>
        {/* Base UI's CollapsibleTrigger exposes data-panel-open (not data-state); rotate via group selector. */}
        <ChevronDown
          aria-hidden
          className="size-3.5 transition-transform duration-200 group-data-[panel-open]/reasoning-trigger:rotate-180"
        />
      </CollapsibleTrigger>

      <CollapsibleContent
        keepMounted
        // Settling choreography: height and opacity tween in lockstep on the
        // same ease-out curve so the collapse reads as an object settling
        // rather than a div with overflow. The chevron rotation above shares
        // the same 200ms duration.
        className={cn(
          "overflow-hidden",
          "transition-[height,opacity] duration-200 ease-out",
          "h-[var(--collapsible-panel-height)] opacity-100",
          "data-[starting-style]:h-0 data-[starting-style]:opacity-0",
          "data-[ending-style]:h-0 data-[ending-style]:opacity-0",
        )}
      >
        <p
          className={cn(
            "mt-2 pl-3 text-sm leading-relaxed",
            "whitespace-pre-wrap break-words text-muted-foreground",
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
