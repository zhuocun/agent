"use client";

import { useState } from "react";
import {
  AlignLeft,
  Bug,
  ChevronRight,
  Code2,
  Lightbulb,
  PenLine,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { PromptSuggestion } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface WelcomeScreenProps {
  userName?: string;
  exiting?: boolean;
  onPromptSelect?: (text: string) => void;
  suggestions: PromptSuggestion[];
  // When true, render the minimal greeting only (no date eyebrow, no
  // suggestion list). Used when other surfaces in the viewport already convey
  // recency / next-step affordances (e.g. the conversation list is non-empty),
  // so the welcome state shouldn't double-up with date + prompt rails.
  compact?: boolean;
}

// Stable icon-key → glyph map for bootstrap suggestions. Exhaustive over the
// PromptSuggestion["icon"] union so a new key can't silently render nothing.
const SUGGESTION_ICONS: Record<PromptSuggestion["icon"], LucideIcon> = {
  code: Code2,
  explain: Lightbulb,
  write: PenLine,
  analyze: AlignLeft,
  brainstorm: Sparkles,
  debug: Bug,
};

function buildGreeting(userName?: string): string {
  const hour = new Date().getHours();
  const suffix = userName ? `, ${userName}` : "";

  if (hour >= 5 && hour <= 11) return `Good morning${suffix}`;
  if (hour >= 12 && hour <= 16) return `Good afternoon${suffix}`;
  if (hour >= 17 && hour <= 21) return `Good evening${suffix}`;
  return userName ? `Hello, ${userName}` : "Hello";
}

function formatDate(): string {
  // Locale-aware; never hardcode field order. iOS-lockscreen-style eyebrow.
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());
}

interface Prompt {
  icon: LucideIcon;
  label: string;
}

// Quiet objects that hint at variety of use without performing a feature pitch.
const PROMPTS: readonly Prompt[] = [
  { icon: Lightbulb, label: "Explain a concept, simply" },
  { icon: PenLine, label: "Help me draft a message" },
  { icon: AlignLeft, label: "Summarize something for me" },
  { icon: Sparkles, label: "Brainstorm ideas with me" },
];

// Progressive disclosure on mobile: show this many prompts before "More".
const INITIAL_PROMPT_COUNT_MOBILE = 2;

export function WelcomeScreen({
  userName,
  exiting = false,
  onPromptSelect,
  suggestions,
  compact = false,
}: WelcomeScreenProps) {
  const heading = buildGreeting(userName);
  const today = formatDate();
  const [promptsExpanded, setPromptsExpanded] = useState(false);

  const promptItems =
    suggestions.length > 0
      ? suggestions.map((s) => ({
          key: s.id,
          icon: SUGGESTION_ICONS[s.icon],
          label: s.title,
          text: s.prompt,
        }))
      : PROMPTS.map((p) => ({
          key: p.label,
          icon: p.icon,
          label: p.label,
          text: p.label,
        }));

  const hiddenMobileCount = Math.max(
    0,
    promptItems.length - INITIAL_PROMPT_COUNT_MOBILE,
  );
  const showMoreButton =
    !promptsExpanded && hiddenMobileCount > 0 && !compact;

  return (
    <div className="flex h-full flex-col items-start justify-center px-4 md:items-center">
      <div
        className={
          exiting
            ? "animate-welcome-exit flex w-full max-w-md flex-col items-start text-left transition-[opacity,transform] duration-200 ease-[var(--ease-welcome)] opacity-0 -translate-y-2 md:items-center md:text-center"
            : "flex w-full max-w-md flex-col items-start text-left md:items-center md:text-center"
        }
      >
        {compact ? null : (
          <p
            className="animate-welcome-enter mb-3 hidden text-sm font-medium text-muted-foreground md:block"
            style={{ animationDelay: "0ms" }}
          >
            {today}
          </p>
        )}

        <h1
          className="animate-welcome-enter text-2xl font-medium tracking-tight md:text-4xl lg:text-5xl"
          style={{ animationDelay: "70ms" }}
        >
          {heading}
        </h1>

        {compact ? null : (
          <ul
            aria-label="Suggested prompts"
            className="glass-clear mt-8 w-full overflow-hidden rounded-3xl text-left md:mt-12"
          >
            {promptItems.map(({ key, icon: Icon, label, text }, index) => {
              const hiddenOnMobile =
                !promptsExpanded && index >= INITIAL_PROMPT_COUNT_MOBILE;
              return (
                <li
                  key={key}
                  className={cn("list-none", hiddenOnMobile && "hidden md:list-item")}
                >
                  <button
                    type="button"
                    onClick={() => onPromptSelect?.(text)}
                    className="animate-welcome-enter flex w-full items-center gap-3 border-t border-border/60 px-5 py-3.5 text-[1.0625rem] leading-6 text-foreground transition-colors duration-200 ease-out first:border-t-0 [@media(hover:hover)]:hover:bg-foreground/[0.04] active:bg-foreground/[0.06] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none md:text-base"
                    style={{ animationDelay: `${150 + index * 60}ms` }}
                  >
                    <Icon
                      className="size-5 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    {label}
                    <ChevronRight
                      className="ml-auto hidden size-4 shrink-0 text-muted-foreground/60 md:block"
                      aria-hidden="true"
                    />
                  </button>
                </li>
              );
            })}
            {showMoreButton ? (
              <li className="list-none md:hidden">
                <button
                  type="button"
                  onClick={() => setPromptsExpanded(true)}
                  className="flex w-full items-center justify-center border-t border-border/60 px-5 py-3 text-sm font-medium text-muted-foreground transition-colors active:bg-foreground/[0.06] focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
                >
                  {hiddenMobileCount} more suggestion
                  {hiddenMobileCount === 1 ? "" : "s"}
                </button>
              </li>
            ) : null}
          </ul>
        )}
      </div>
    </div>
  );
}
