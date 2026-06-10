"use client";

import { useEffect, useState } from "react";
import {
  AlignLeft,
  Bug,
  Code2,
  Lightbulb,
  PenLine,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { PromptSuggestion } from "@/lib/types";

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

export function WelcomeScreen({
  userName,
  exiting = false,
  onPromptSelect,
  suggestions,
  compact = false,
}: WelcomeScreenProps) {
  // Greeting/date depend on the client's local clock — gate on mount so SSR and
  // hydration never disagree on the hour or weekday string.
  const [mounted, setMounted] = useState(false);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- client-only clock
  useEffect(() => setMounted(true), []);

  const heading = mounted
    ? buildGreeting(userName)
    : userName
      ? `Hello, ${userName}`
      : "Hello";
  const today = mounted ? formatDate() : "";

  const bootstrapPrompts =
    suggestions.length > 0
      ? compact
        ? suggestions.slice(0, 2)
        : suggestions
      : null;
  const fallbackPrompts =
    suggestions.length > 0
      ? null
      : compact
        ? PROMPTS.slice(0, 2)
        : PROMPTS;

  return (
    <div className="flex h-full flex-col items-center justify-center px-4">
      <div
        className={
          exiting
            // `animate-welcome-exit` is a class hook (not a Tailwind animation
            // utility) so the reduced-motion CSS in globals.css can zero this
            // inline transition the same way it zeroes `.animate-welcome-enter`.
            // Without the hook, prefers-reduced-motion would still see a 200ms
            // opacity/transform tween here even though the JS timer is source
            // of truth for the seam. On exit the whole block fades/translates as
            // one unit; the children's already-finished enter animations don't
            // replay. Max-width must match the resting variant exactly, or the
            // group snaps width at the exit seam. (max-w-xl: the serif display
            // greeting + wrapping pill rail need more room than the old
            // inset-group's max-w-md.)
            ? "animate-welcome-exit flex w-full max-w-xl flex-col items-center text-center transition-[opacity,transform] duration-200 ease-[var(--ease-welcome)] opacity-0 -translate-y-2"
            // Entrance choreography lives on each child below (staggered via
            // inline animationDelay). The wrapper itself carries layout only.
            : "flex w-full max-w-xl flex-col items-center text-center"
        }
      >
        {/* Slim pill banner above the greeting — the date eyebrow recast in the
            BYOK-badge / install-coachmark capsule language. glass-clear keeps
            it the quietest material in the system; under prefers-contrast the
            utility densifies its fill on its own (globals.css). */}
        {compact || !today ? null : (
          <p
            className="animate-welcome-enter glass-clear mb-7 inline-flex items-center rounded-full px-3.5 py-1.5 text-xs font-medium tracking-wide text-muted-foreground"
            style={{ animationDelay: "0ms" }}
          >
            {today}
          </p>
        )}

        {/* Hero greeting — the one display-serif moment in the app (Decision 16
            carve-out of Decision 04's working-surface rule). Instrument Serif
            ships weight 400 only, so font-normal is structural, not stylistic.
            text-balance keeps two-line personalized greetings ragged-even. */}
        <h2
          className="animate-welcome-enter font-heading text-5xl font-normal tracking-tight text-balance text-foreground md:text-6xl lg:text-7xl"
          style={{ animationDelay: "40ms" }}
        >
          {heading}
        </h2>

        {/* Suggestion rail: rounded glass pills wrapping under the greeting
            (the Lovable-style hero rail) in place of the old iOS inset group.
            Each pill is its own `glass-clear` capsule — lowest-opacity material
            in the system, so the hero atmosphere still reads through it — and
            the hover tint swaps the fill for a foreground wash exactly like
            the header's glass float buttons (`hover:bg-foreground/5`). The
            `<ul aria-label="Suggested prompts">` role/name pair and the
            click-to-insert wiring are load-bearing for the e2e suite — keep
            both. prefers-reduced-motion neutralizes `animate-welcome-enter`
            globally (globals.css), so the stagger delays are inert there. */}
        {bootstrapPrompts || fallbackPrompts ? (
        <ul
          aria-label="Suggested prompts"
          className="mt-10 flex w-full flex-wrap items-center justify-center gap-2.5 md:mt-12"
        >
          {bootstrapPrompts
            ? bootstrapPrompts.map((s, index) => {
                const Icon = SUGGESTION_ICONS[s.icon];
                return (
                  <li key={s.id} className="list-none">
                    <button
                      type="button"
                      onClick={() => onPromptSelect?.(s.prompt)}
                      className="animate-welcome-enter glass-clear inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-[0.9375rem] leading-5 text-foreground transition-colors duration-200 ease-out [@media(hover:hover)]:hover:bg-foreground/5 active:bg-foreground/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      style={{ animationDelay: `${100 + index * 50}ms` }}
                    >
                      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                      {s.title}
                    </button>
                  </li>
                );
              })
            : fallbackPrompts!.map(({ icon: Icon, label }, index) => (
                <li key={label} className="list-none">
                  <button
                    type="button"
                    onClick={() => onPromptSelect?.(label)}
                    className="animate-welcome-enter glass-clear inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-[0.9375rem] leading-5 text-foreground transition-colors duration-200 ease-out [@media(hover:hover)]:hover:bg-foreground/5 active:bg-foreground/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    style={{ animationDelay: `${100 + index * 50}ms` }}
                  >
                    <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    {label}
                  </button>
                </li>
              ))}
        </ul>
        ) : null}
      </div>
    </div>
  );
}
