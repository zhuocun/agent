"use client";

import type { JSX } from "react";

// EU AI Act Article 50(1) interaction-disclosure surface (PRD 05 §7.5).
// Shown on the welcome/empty state — not below the composer (#245 removed that
// placement as chrome clutter). Calm, readable, accessibility-conformant.
export function AiDisclosure(): JSX.Element {
  return (
    <p
      role="note"
      aria-label="AI interaction disclosure"
      className="mt-4 max-w-md ui-caption leading-snug text-muted-foreground"
      data-testid="ai-interaction-disclosure"
    >
      You&apos;re chatting with an AI assistant. Responses may be inaccurate —
      verify important information.
    </p>
  );
}
