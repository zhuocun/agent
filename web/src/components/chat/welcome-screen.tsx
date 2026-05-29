"use client";

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

// Authoring placeholders — quiet objects that hint at variety of use without
// performing a feature pitch.
const PROMPTS: readonly string[] = [
  "Explain a concept like I'm new to it",
  "Help me draft a message",
  "Summarize this for me",
  "Brainstorm with me",
];

export function WelcomeScreen({
  userName,
  exiting = false,
  onPromptSelect,
}: WelcomeScreenProps) {
  const heading = buildGreeting(userName);

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
            // of truth for the seam.
            ? "animate-welcome-exit flex w-full max-w-3xl flex-col items-center text-center transition-[opacity,transform] duration-200 [transition-timing-function:cubic-bezier(0.16,1,0.3,1)] opacity-0 -translate-y-2"
            : "flex w-full max-w-3xl flex-col items-center text-center animate-welcome-enter"
        }
      >
        <h1 className="text-4xl font-medium tracking-tight md:text-5xl lg:text-6xl">
          {heading}
        </h1>

        <ul
          aria-label="Suggested prompts"
          className="mt-16 grid w-full grid-cols-1 gap-3 md:mt-20 md:grid-cols-2"
        >
          {PROMPTS.map((prompt) => (
            <li key={prompt} className="list-none">
              <button
                type="button"
                onClick={() => onPromptSelect?.(prompt)}
                className="w-full rounded-2xl bg-foreground/[0.04] p-5 text-left text-sm leading-6 text-foreground transition-colors duration-200 ease-out [@media(hover:hover)]:hover:bg-foreground/[0.07] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background md:text-base"
              >
                {prompt}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
