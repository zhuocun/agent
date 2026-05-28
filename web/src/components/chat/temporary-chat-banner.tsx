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
    <div
      role="note"
      className={cn(
        "glass-capsule mx-auto mt-2 flex max-w-fit items-center gap-2 bg-temporary-chat-banner/40 px-3 py-1.5 text-sm text-temporary-chat-banner-foreground",
        className,
      )}
    >
      <Ghost aria-hidden className="size-4 shrink-0" />
      <p className="min-w-0 truncate">
        <span className="font-medium">Temporary chat</span>{" "}
        <span>
          — won&apos;t be saved or used to train models.
        </span>
      </p>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onTurnOff}
        className="ml-1 shrink-0"
      >
        Turn off
      </Button>
    </div>
  );
}
