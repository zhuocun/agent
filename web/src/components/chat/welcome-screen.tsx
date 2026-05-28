"use client";

import {
  BarChart3,
  BookOpen,
  Bug,
  Code2,
  Lightbulb,
  PenLine,
  type LucideIcon,
} from "lucide-react";

import { MOCK_SUGGESTIONS } from "@/lib/mock-data";
import type { PromptSuggestion } from "@/lib/types";
import { cn } from "@/lib/utils";

const SUGGESTION_ICONS: Record<PromptSuggestion["icon"], LucideIcon> = {
  code: Code2,
  explain: BookOpen,
  write: PenLine,
  analyze: BarChart3,
  brainstorm: Lightbulb,
  debug: Bug,
};

export interface WelcomeScreenProps {
  onPickSuggestion: (prompt: string) => void;
  userName?: string;
}

export function WelcomeScreen({
  onPickSuggestion,
  userName,
}: WelcomeScreenProps): React.JSX.Element {
  const heading = userName ? `How can I help, ${userName}?` : "How can I help?";

  return (
    <div className="flex h-full flex-col items-center justify-center px-4">
      <div className="flex flex-col items-center text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-brand text-xl font-bold text-brand-foreground">
          O
        </div>
        <h1 className="mt-5 text-2xl font-semibold tracking-tight sm:text-3xl">
          {heading}
        </h1>
        <p className="mt-3 text-muted-foreground">
          Ask anything, or start with one of these.
        </p>
      </div>

      <div className="mt-12 grid w-full max-w-xl grid-cols-1 gap-2 sm:grid-cols-2">
        {MOCK_SUGGESTIONS.map((suggestion) => {
          const Icon = SUGGESTION_ICONS[suggestion.icon];
          return (
            <button
              key={suggestion.id}
              type="button"
              onClick={() => onPickSuggestion(suggestion.prompt)}
              className={cn(
                "flex items-start gap-3 rounded-2xl bg-muted/40 p-4 text-left",
                "transition-colors hover:bg-muted",
                "focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]",
              )}
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium">
                  {suggestion.title}
                </span>
                <span className="line-clamp-2 text-xs text-muted-foreground">
                  {suggestion.prompt}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
