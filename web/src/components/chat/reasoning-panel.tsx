"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronRight } from "lucide-react";

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

  const label = isStreaming
    ? "Thinking…"
    : durationSec && durationSec > 0
      ? `Reasoned for ${formatDuration(durationSec)}`
      : "Reasoning";

  return (
    <Collapsible
      open={open}
      onOpenChange={handleOpenChange}
      className="text-muted-foreground"
    >
      <CollapsibleTrigger
        aria-label={open ? "Hide reasoning" : "Show reasoning"}
        className={cn(
          "group/reasoning -mx-1 flex w-full min-h-10 items-center gap-1.5 rounded-md px-1 py-1",
          "text-left text-sm text-muted-foreground",
          "transition-colors hover:text-foreground",
          "outline-none focus-visible:shadow-[var(--focus-ring)]",
        )}
      >
        {isStreaming ? (
          <span
            className={cn(
              "bg-gradient-to-r from-muted-foreground via-foreground to-muted-foreground",
              "bg-[length:200%_100%] bg-clip-text text-transparent",
              "motion-safe:animate-shimmer",
            )}
          >
            {label}
          </span>
        ) : (
          <span>{label}</span>
        )}

        <ChevronRight
          aria-hidden="true"
          className={cn(
            "ml-auto size-4 shrink-0 text-muted-foreground/70 transition-transform duration-200",
            open && "rotate-90",
          )}
        />
      </CollapsibleTrigger>

      {/* keepMounted preserves streamed text so live updates stay smooth while collapsed. */}
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
            "mt-2 border-l border-foreground/10 pl-3 text-sm leading-relaxed",
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
