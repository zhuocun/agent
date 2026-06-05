import type { SlashCommand, UserPreferences } from "@/lib/types";

// Privacy-first default preferences. MIRRORS the backend defaults in
// api/app/db/repositories/preferences.py `_DEFAULTS` (asserted in
// api/tests/test_preferences.py): any change here must land there too. Used as
// the FE's optimistic baseline before bootstrap resolves the saved row.
export const MOCK_PREFERENCES: UserPreferences = {
  defaultTierId: "auto",
  temporaryByDefault: false,
  trainingOptIn: false,
  sendOnEnter: true,
  autoExpandReasoning: false,
  telemetryEnabled: true,
  customInstructions: "",
  retentionDays: null,
  monthlyBudgetUsd: null,
  perConversationBudgetUsd: null,
  memoryEnabled: false,
  keyboardShortcuts: {},
};

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
