import type { PromptSuggestion, SlashCommand } from "@/lib/types";

// Native slash commands (PRD 01 §4.3 / §5.3). Templates end with a trailing
// space (one-liners) or an empty body inside code fences (multi-line) so the
// caret lands where the user needs to type next. These stay client-static —
// the BE serves prompt suggestions via bootstrap but the slash registry is
// purely a composer-UX affordance and doesn't need a round-trip.
export const MOCK_COMMANDS: SlashCommand[] = [
  {
    id: "cmd-summarize",
    name: "summarize",
    description: "Condense text into bullet points",
    prompt: "Summarize the following text into 3 bullet points: ",
    icon: "summarize",
  },
  {
    id: "cmd-explain",
    name: "explain",
    description: "Explain a concept in plain language",
    prompt: "Explain this in plain language for a beginner: ",
    icon: "explain",
  },
  {
    id: "cmd-rewrite",
    name: "rewrite",
    description: "Rewrite text more clearly and concisely",
    prompt: "Rewrite this more clearly and concisely: ",
    icon: "rewrite",
  },
  {
    id: "cmd-translate",
    name: "translate",
    description: "Translate text into English",
    prompt: "Translate the following text into English: ",
    icon: "translate",
  },
  {
    id: "cmd-code-review",
    name: "code-review",
    description: "Review code for bugs and improvements",
    prompt: "Review this code for bugs, style issues, and suggestions:\n\n```\n\n```",
    icon: "code-review",
  },
  {
    id: "cmd-debug",
    name: "debug",
    description: "Debug an error message and propose a fix",
    prompt: "Debug this error message and propose a fix:\n\n",
    icon: "debug",
  },
  {
    id: "cmd-draft-email",
    name: "draft-email",
    description: "Draft a professional email",
    prompt: "Draft a professional email about: ",
    icon: "draft-email",
  },
  {
    id: "cmd-brainstorm",
    name: "brainstorm",
    description: "Brainstorm a list of ideas",
    prompt: "Brainstorm 10 ideas for: ",
    icon: "brainstorm",
  },
];

// Empty-state prompt starters (PRD 01 §4.3). The BE includes a `suggestions`
// array in bootstrap; for now the welcome screen doesn't render them so this
// static set stands by as a fallback if/when the FE wires the welcome cards.
export const MOCK_SUGGESTIONS: PromptSuggestion[] = [
  {
    id: "s1",
    icon: "debug",
    title: "Debug a stack trace",
    prompt: "I'm getting a TypeError in this function — here's the stack trace. Walk me through finding the root cause.",
  },
  {
    id: "s2",
    icon: "explain",
    title: "Explain a concept",
    prompt: "Explain the difference between optimistic and pessimistic locking, with a concrete example of when each is the right choice.",
  },
  {
    id: "s3",
    icon: "write",
    title: "Draft a message",
    prompt: "Help me write a clear, friendly message letting my team know a deadline is slipping by a few days and why.",
  },
  {
    id: "s4",
    icon: "analyze",
    title: "Compare options",
    prompt: "Compare REST, GraphQL, and gRPC for a mobile app backend. Give me a short table of trade-offs and a recommendation.",
  },
];
