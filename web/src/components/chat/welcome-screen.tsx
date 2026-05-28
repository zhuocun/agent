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

function buildGreeting(userName?: string): string {
  const hour = new Date().getHours();
  const suffix = userName ? `, ${userName}` : "";

  if (hour >= 5 && hour <= 11) return `Good morning${suffix}`;
  if (hour >= 12 && hour <= 16) return `Good afternoon${suffix}`;
  if (hour >= 17 && hour <= 21) return `Good evening${suffix}`;
  return userName ? `Working late, ${userName}?` : "Working late?";
}

export function WelcomeScreen({
  onPickSuggestion,
  userName,
}: WelcomeScreenProps): React.JSX.Element {
  const heading = buildGreeting(userName);

  return (
    <div className="flex h-full flex-col items-center justify-center px-4">
      <div className="flex flex-col items-center text-center animate-welcome-enter">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          {heading}
        </h1>
        <p className="mt-3 text-muted-foreground">
          What&apos;s on your mind?
        </p>
      </div>

      <div className="mt-12 grid w-full max-w-xl grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3 animate-welcome-enter [animation-delay:80ms]">
        {MOCK_SUGGESTIONS.map((suggestion) => {
          const Icon = SUGGESTION_ICONS[suggestion.icon];
          return (
            <button
              key={suggestion.id}
              type="button"
              onClick={() => onPickSuggestion(suggestion.prompt)}
              className={cn(
                "group/chip flex min-h-16 items-start gap-3 rounded-2xl bg-muted/40 p-4 text-left",
                "transition-all duration-150 hover:-translate-y-0.5 hover:bg-muted hover:shadow-sm",
                "focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]",
              )}
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground transition-colors group-hover/chip:bg-brand-muted group-hover/chip:text-brand">
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
