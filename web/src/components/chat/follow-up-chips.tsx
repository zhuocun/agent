"use client";

import { CornerDownRight } from "lucide-react";

import { useT } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";

// Max chips shown under a message — three keeps the row to one line on phones
// and avoids turning the footer into a wall of suggestions.
const MAX_FOLLOW_UPS = 3;

// Heuristic follow-up suggestions for a finished assistant answer (T11). No
// model call: we look at the LAST paragraph for questions the assistant posed
// back to the user (a common "want me to…?" / "should I…?" ending) and surface
// those as one-tap chips. When the answer poses no question we fall back to two
// generic deepen-the-thread prompts. Exported pure for unit coverage.
export function deriveFollowUps(
  text: string,
  fallback: { tellMore: string; example: string },
): string[] {
  const trimmed = text.trim();
  if (trimmed.length === 0) return [];

  const paragraphs = trimmed.split(/\n{2,}/);
  const lastParagraph = paragraphs[paragraphs.length - 1] ?? "";

  // Split the last paragraph into sentences and keep the ones phrased as a
  // question. Strip leading list markers / quotes so a bulleted question reads
  // cleanly as a chip.
  const questions = lastParagraph
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.replace(/^[\s>*\-\d.)]+/, "").trim())
    .filter((sentence) => sentence.endsWith("?") && sentence.length > 1)
    // Overly long questions make poor chips — keep them short and scannable.
    .filter((sentence) => sentence.length <= 80);

  if (questions.length > 0) {
    return questions.slice(0, MAX_FOLLOW_UPS);
  }

  return [fallback.tellMore, fallback.example];
}

export function FollowUpChips({
  text,
  onSelect,
}: {
  text: string;
  // Selecting a chip hands its text to the parent, which prefills the composer
  // (it is NEVER auto-sent — the user reviews/edits first).
  onSelect: (text: string) => void;
}) {
  const t = useT();
  const suggestions = deriveFollowUps(text, {
    tellMore: t("followups.tellMore"),
    example: t("followups.example"),
  });

  if (suggestions.length === 0) return null;

  return (
    <div
      className="flex flex-wrap items-center gap-2 pt-1"
      data-testid="follow-up-chips"
      aria-label="Suggested follow-ups"
    >
      {suggestions.map((suggestion, index) => (
        <button
          key={`${index}-${suggestion}`}
          type="button"
          onClick={() => onSelect(suggestion)}
          data-testid="follow-up-chip"
          className={cn(
            "inline-flex min-h-11 max-w-full items-center gap-1.5 rounded-full px-3 py-1.5 md:min-h-0",
            "border border-border/70 bg-background/60 text-xs text-muted-foreground",
            "transition-colors hover:border-border hover:bg-foreground/[0.04] hover:text-foreground",
            "focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none",
          )}
        >
          <CornerDownRight aria-hidden className="size-3 shrink-0" />
          <span className="min-w-0 truncate">{suggestion}</span>
        </button>
      ))}
    </div>
  );
}
