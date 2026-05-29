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

  const label = isStreaming
    ? "Thinking…"
    : durationSec && durationSec > 0
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
          "group/reasoning-trigger inline-flex items-center gap-1 text-left text-xs text-muted-foreground/70",
          "bg-transparent p-0 underline-offset-2",
          "outline-none focus-visible:underline",
        )}
      >
        {isStreaming ? (
          <span
            className={cn(
              "bg-gradient-to-r from-muted-foreground/70 via-foreground/80 to-muted-foreground/70",
              "bg-[length:200%_100%] bg-clip-text text-transparent",
              "motion-safe:animate-shimmer",
            )}
          >
            {label}
          </span>
        ) : (
          <span>{label}</span>
        )}
        {/* Base UI's CollapsibleTrigger exposes data-panel-open (not data-state); rotate via group selector. */}
        <ChevronDown
          aria-hidden
          className="size-3.5 transition-transform duration-200 group-data-[panel-open]/reasoning-trigger:rotate-180"
        />
      </CollapsibleTrigger>

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
