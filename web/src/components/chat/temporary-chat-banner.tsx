"use client";

import type { JSX } from "react";
import { Ghost } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface TemporaryChatBannerProps {
  onTurnOff: () => void;
  className?: string;
}

// Slim transparency bar shown under the app header while a chat is in
// temporary mode (PRD 06 — privacy-first). Informational, not a live region:
// the parent only mounts it when temporary mode is active, so a screen reader
// encounters it on entry rather than as an interruption. The dedicated banner
// tokens carry the muted "off the record" treatment in both themes.
export function TemporaryChatBanner({
  onTurnOff,
  className,
}: TemporaryChatBannerProps): JSX.Element {
  return (
    <div className={cn("flex justify-center px-3 pt-1", className)}>
      <div
        role="note"
        // Tiny iOS-style pill: inline-flex, rounded-full, muted surface, no
        // border, no shadow — reads as a quiet status chip rather than a bar.
        className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
      >
        <Ghost aria-hidden className="size-3.5 shrink-0" />
        <span className="truncate">
          <span className="font-medium text-foreground">Temporary chat</span>
          <span> — won&apos;t be saved.</span>
        </span>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          onClick={onTurnOff}
          // Ghost xs Button already gives us a quiet inline affordance; the
          // negative margin pulls the pill right edge tight against the label.
          className="-mr-1 ml-0.5 h-5 px-1.5 text-xs"
        >
          Turn off
        </Button>
      </div>
    </div>
  );
}
