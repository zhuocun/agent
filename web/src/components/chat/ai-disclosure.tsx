"use client";

import type { JSX } from "react";

// EU AI Act Article 50(1) interaction-disclosure surface (PRD 04 §5.7,
// UNCONDITIONAL P0). A persistent, calm one-liner — `text-muted-foreground`
// at the smallest body step — sized to disappear into the chrome while
// remaining readable without hover. Rendered in normal flow directly below
// the composer so the disclosure rides with the composer's bottom edge and
// stays visible alongside every send action.
export function AiDisclosure(): JSX.Element {
  return (
    <div
      role="note"
      aria-label="AI interaction disclosure"
      className="pointer-events-none flex justify-center pt-1.5"
    >
      <p className="px-2 text-[0.8125rem] leading-snug text-muted-foreground">
        You&apos;re chatting with AI. Responses may be inaccurate.
      </p>
    </div>
  );
}
