"use client";

import type { JSX } from "react";

// EU AI Act Article 50(1) interaction-disclosure surface (PRD 04 §5.7,
// UNCONDITIONAL P0). A persistent, calm one-liner — `text-muted-foreground` at
// the smallest body step — sized to disappear into the chrome while remaining
// readable without hover. Lives in the gradient header strip so the working
// surface keeps its calm and the disclosure rides with the safe-area inset.
export function AiDisclosure(): JSX.Element {
  return (
    <div
      role="note"
      aria-label="AI interaction disclosure"
      className="pointer-events-none fixed inset-x-0 top-[calc(env(safe-area-inset-top)+2.75rem)] z-30 flex justify-center md:top-[calc(env(safe-area-inset-top)+4.25rem)]"
    >
      <p className="rounded-full px-2 text-xs leading-tight text-muted-foreground">
        You&apos;re chatting with AI. Responses may be inaccurate.
      </p>
    </div>
  );
}
