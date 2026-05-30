"use client";

import { AlignLeft, ChevronRight, Lightbulb, PenLine, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface WelcomeScreenProps {
  userName?: string;
  exiting?: boolean;
  onPromptSelect?: (text: string) => void;
}

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
}: WelcomeScreenProps) {
  const heading = buildGreeting(userName);
  const today = formatDate();

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
            ? "animate-welcome-exit flex w-full max-w-md flex-col items-center text-center transition-[opacity,transform] duration-200 [transition-timing-function:cubic-bezier(0.16,1,0.3,1)] opacity-0 -translate-y-2"
            // Entrance choreography lives on each child below (staggered via
            // inline animationDelay). The wrapper itself carries layout only.
            : "flex w-full max-w-md flex-col items-center text-center"
        }
      >
        <p
          className="animate-welcome-enter mb-3 text-sm font-medium tracking-tight text-muted-foreground"
          style={{ animationDelay: "0ms" }}
        >
          {today}
        </p>

        <h1
          className="animate-welcome-enter text-4xl font-medium tracking-tight md:text-5xl lg:text-6xl"
          style={{ animationDelay: "70ms" }}
        >
          {heading}
        </h1>

        {/* One iOS-Settings-style inset group: a single quiet surface with
            hairline separators between rows (none above the first) and a
            trailing disclosure chevron per row. `overflow-hidden` clips the
            row press-highlights to the rounded corners. The fill is lighter
            than the old per-card 0.04 so the brand halo reads through it. */}
        <ul
          aria-label="Suggested prompts"
          className="mt-10 w-full overflow-hidden rounded-2xl bg-foreground/[0.03] text-left md:mt-12"
        >
          {PROMPTS.map(({ icon: Icon, label }, index) => (
            <li key={label} className="list-none">
              <button
                type="button"
                onClick={() => onPromptSelect?.(label)}
                className="animate-welcome-enter flex w-full items-center gap-3 border-t border-border/60 px-5 py-3.5 text-sm leading-6 text-foreground transition-colors duration-200 ease-out first:border-t-0 [@media(hover:hover)]:hover:bg-foreground/[0.04] active:bg-foreground/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand md:text-base"
                style={{ animationDelay: `${150 + index * 60}ms` }}
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
      </div>
    </div>
  );
}
