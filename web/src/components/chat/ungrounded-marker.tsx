"use client";

import { SearchX } from "lucide-react";

// Honesty marker for an ungrounded web-search turn (PRD 07 §4.3): web search was
// requested but resolved zero usable sources. Calm and informational — NOT an
// error — so an ungrounded answer never gets to look cited.
//
// Shared by the private thread and the public share view so a shared ungrounded
// turn reads identically; the decision of WHEN to show it is one rule too
// (`shouldShowSourcesInMainPanel` in @/lib/agentic-layout).
export function UngroundedMarker() {
  return (
    <div
      className="inline-flex items-center gap-1.5 ui-caption text-muted-foreground"
      data-testid="ungrounded-marker"
    >
      <SearchX aria-hidden className="size-3.5" />
      <span>Answered without live sources</span>
    </div>
  );
}
