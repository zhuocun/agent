"use client";

import { useEffect, useState } from "react";
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
            // group snaps width at the exit seam.
            ? "animate-welcome-exit flex w-full max-w-md flex-col items-center text-center transition-[opacity,transform] duration-200 ease-[var(--ease-welcome)] opacity-0 -translate-y-2"
            // Entrance choreography lives on each child below (staggered via
            // inline animationDelay). The wrapper itself carries layout only.
            : "flex w-full max-w-md flex-col items-center text-center"
        }
      >
        {compact || !today ? null : (
          <p
            className="animate-welcome-enter mb-3 text-sm font-medium tracking-wide text-muted-foreground"
            style={{ animationDelay: "0ms" }}
          >
            {today}
          </p>
        )}

        <h2
          className="animate-welcome-enter text-4xl font-semibold tracking-tight text-foreground md:text-5xl lg:text-6xl"
          style={{ animationDelay: "0ms" }}
        >
          {heading}
        </h2>

        {/* One iOS-Settings-style inset group: a single quiet surface with
            hairline separators between rows (none above the first) and a
            trailing disclosure chevron per row. `overflow-hidden` clips the
            row press-highlights to the rounded corners. `glass-clear` is the
            lowest-opacity material in the system — the brand halo still reads
            through it (per the old 0.03 intent) while it adds the saturated
            backdrop-filter and the inset hairline rim the flat tint lacked.
            `rounded-3xl` gives the iOS-26-generous outer curvature; the rows'
            press-highlights are clipped to it, and their inner edges stay
            square against the separators so nothing fights the curve. */}
        {bootstrapPrompts || fallbackPrompts ? (
        <ul
          aria-label="Suggested prompts"
          className="glass-clear mt-10 w-full rounded-3xl text-left md:mt-12"
        >
          {bootstrapPrompts
            ? bootstrapPrompts.map((s, index) => {
                const Icon = SUGGESTION_ICONS[s.icon];
                return (
                  <li key={s.id} className="list-none">
                    <button
                      type="button"
                      onClick={() => onPromptSelect?.(s.prompt)}
                      className="animate-welcome-enter flex w-full items-center gap-3 border-t border-border px-5 py-3.5 text-[1.0625rem] leading-6 text-foreground transition-colors duration-200 ease-out first:rounded-t-3xl first:border-t-0 last:rounded-b-3xl [@media(hover:hover)]:hover:bg-foreground/[0.04] active:bg-foreground/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset md:text-[1.0625rem]"
                      style={{ animationDelay: `${60 + index * 40}ms` }}
                    >
                      <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                      {s.title}
                      <ChevronRight
                        className="ml-auto size-4 shrink-0 text-muted-foreground/60"
                        aria-hidden="true"
                      />
                    </button>
                  </li>
                );
              })
            : fallbackPrompts!.map(({ icon: Icon, label }, index) => (
                <li key={label} className="list-none">
                  <button
                    type="button"
                    onClick={() => onPromptSelect?.(label)}
                    className="animate-welcome-enter flex w-full items-center gap-3 border-t border-border px-5 py-3.5 text-[1.0625rem] leading-6 text-foreground transition-colors duration-200 ease-out first:rounded-t-3xl first:border-t-0 last:rounded-b-3xl [@media(hover:hover)]:hover:bg-foreground/[0.04] active:bg-foreground/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset md:text-[1.0625rem]"
                    style={{ animationDelay: `${60 + index * 40}ms` }}
                  >
                    <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                    {label}
                    <ChevronRight
                      className="ml-auto size-4 shrink-0 text-muted-foreground/60"
                      aria-hidden="true"
                    />
                  </button>
                </li>
              ))}
        </ul>
        ) : null}
      </div>
    </div>
  );
}
