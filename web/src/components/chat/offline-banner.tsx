"use client";

import type { JSX } from "react";
import { CloudOff } from "lucide-react";

import { cn } from "@/lib/utils";

// Calm connectivity pill for the top status slot. Shares the degraded and
// temporary banners' shape so the slot never changes height.
export function OfflineBanner({
  className,
  temporary = false,
}: {
  className?: string;
  temporary?: boolean;
}): JSX.Element {
  return (
    <div className={cn("flex justify-center px-3 pt-1", className)}>
      <div
        role="status"
        data-testid="offline-banner"
        className="inline-flex h-11 max-w-full items-center gap-1.5 rounded-full bg-muted px-3.5 ui-caption text-muted-foreground ring-1 ring-border"
      >
        <CloudOff aria-hidden className="size-3.5 shrink-0" />
        <span className="min-w-0">
          <span className="font-medium text-foreground">Offline</span>
          <span>
            {temporary
              ? " · Temporary chat"
              : " — drafts stay on this device."}
          </span>
        </span>
      </div>
    </div>
  );
}
