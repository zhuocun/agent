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
        "flex items-center gap-2 border-b border-border px-4 py-2 text-sm",
        "bg-temporary-chat-banner text-temporary-chat-banner-foreground",
        className,
      )}
    >
      <Ghost aria-hidden className="size-4 shrink-0" />
      <p className="min-w-0 truncate">
        <span className="font-semibold">Temporary chat</span>{" "}
        <span className="text-temporary-chat-banner-foreground/80">
          — this conversation won&apos;t be saved to your history or used to
          train models.
        </span>
      </p>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onTurnOff}
        className="ml-auto shrink-0"
      >
        Turn off
      </Button>
    </div>
  );
}
