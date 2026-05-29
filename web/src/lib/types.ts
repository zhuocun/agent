// Shared domain types for the chat thread.
// Mirrors the PRD data model: typed multi-part messages (PRD 01 §4.4 / PRD 04),
// per-message model + cost transparency (PRD 07), and served-vs-requested
// substitution (PRD 01 §4.6 / PRD 07 §5).

export type ModelTierId = "fast" | "smart" | "pro" | "auto";

export interface ModelTier {
  id: ModelTierId;
  label: string; // user-facing: never a raw model ID (PRD 06 §5.6)
  description: string;
  speedHint: "fastest" | "fast" | "balanced" | "slow";
  costHint: "lowest" | "low" | "medium" | "high";
  contextHint: string; // e.g. "128K"
}

// Reasoning-effort / extended-thinking control surfaced in the composer
// (PRD 01 §4.2 / §4.3). Mapping to provider knobs lives in PRD 02; the UI
// only needs the relative cost/latency hints to honour the transparency
// wedge ("higher reasoning ⇒ higher cost, slower").
export type ReasoningEffortId = "auto" | "minimal" | "standard" | "extended";

export interface ReasoningEffort {
  id: ReasoningEffortId;
  label: string;
  description: string;
  // Relative hints; map to provider knobs in PRD 02. UI uses them for the
  // "Cost: …" / "Latency: …" indicators in the dropdown.
  costHint: "auto" | "lowest" | "low" | "medium" | "high";
  latencyHint: "auto" | "fastest" | "fast" | "balanced" | "slow";
}

export type SubstitutionReasonCode =
  | "auto_downgrade"
  | "provider_fallback"
  | "rate_limited"
  | "capacity_reroute"
  | "deprecated_model"
  | "gateway_route";

// Faithful UI subset of PRD 07 §4.1 cost_breakdown.
export interface LongContext {
  flat: boolean; // flat pricing: no long-context surcharge, e.g. DeepSeek (first-class positive fact)
  tierScope?: "session" | "overage";
  tokensRepriced?: "all" | "above_threshold" | "none";
  appliedTier?: {
    label: string;
    thresholdTokens: number;
    priceInPerM: number;
    priceOutPerM: number;
  };
  sessionMultiplier?: { input: number; output: number };
}

export interface CostBreakdown {
  currency: string; // "USD"
  listPriceInPerM: number;
  listPriceOutPerM: number;
  inputTokens: number;
  outputTokens: number;
  reasoningTokens: number;
  cachedInputTokens: number;
  longContext: LongContext;
  promoApplied: boolean;
  subtotalUsd: number;
  sessionSurchargeUsd: number;
}

export interface ModelAttribution {
  requestedTierId: ModelTierId;
  servedTierId: ModelTierId;
  servedModelLabel: string; // e.g. "DeepSeek Chat"
  isByok: boolean;
  costUsd: number;
  costConfidence: "exact" | "estimate";
  breakdown: CostBreakdown;
  // Present only when served != requested (silent-downgrade prevention).
  substitution?: {
    reasonCode: SubstitutionReasonCode;
    reasonText: string; // e.g. "answered by Fast because Pro was rate-limited"
  };
}

export type MessagePart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string; durationSec?: number }
  | { type: "status"; label: string; state: "active" | "done" };

export type MessageRole = "user" | "assistant";

// Per-assistant-message stream lifecycle (PRD 01 §5.1).
export type StreamStatus =
  | "idle"
  | "submitted" // pre-first-token
  | "streaming"
  | "done"
  | "stopped"
  | "error";

export type Feedback = "up" | "down" | null;

export interface ChatMessage {
  id: string;
  role: MessageRole;
  parts: MessagePart[];
  createdAt: string; // ISO
  // Assistant-only:
  status?: StreamStatus;
  attribution?: ModelAttribution;
  feedback?: Feedback;
}

export interface UsageBudget {
  used: number;
  limit: number;
  periodLabel: string; // e.g. "this month"
  isByok: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  selectedTierId: ModelTierId;
  isTemporary: boolean;
}

// A lightweight history-list entry for the sidebar (PRD 01 §4.2 / PRD 03).
// The full message body is loaded on demand; the list only needs identity,
// a title, recency for grouping, and a couple of display flags.
export interface ConversationSummary {
  id: string;
  title: string;
  updatedAt: string; // ISO — used to bucket into Today / Yesterday / Previous 7 days …
  isTemporary?: boolean;
  pinned?: boolean;
}

// User-editable preferences surfaced in the settings panel (PRD 06 §5.7 / PRD 05).
// Privacy-first defaults: temporary off, training opt-in OFF.
export interface UserPreferences {
  defaultTierId: ModelTierId;
  temporaryByDefault: boolean;
  trainingOptIn: boolean; // default false — conversations are not used for training
  sendOnEnter: boolean;
  autoExpandReasoning: boolean;
}

// Account / billing identity for the sidebar footer + settings (PRD 05 / PRD 07 §5.8).
export interface AccountInfo {
  name: string;
  email: string;
  planLabel: string; // e.g. "Pro" — never a raw SKU
  byokEnabled: boolean;
  byokMaskedKey?: string; // e.g. "sk-…4f2a", shown only when byokEnabled
}

// Onboarding / empty-state prompt starters (PRD 01 §4.3).
// `icon` is a stable key the welcome screen maps to a lucide glyph — keeps the
// data layer free of React/component imports.
export interface PromptSuggestion {
  id: string;
  icon: "code" | "explain" | "write" | "analyze" | "brainstorm" | "debug";
  title: string; // short card label
  prompt: string; // full text inserted into the composer on pick
}

// Native slash command (PRD 01 §4.3 / §5.3). The composer popover renders these
// when the user types "/" at line start. `name` is the bare slug (no leading
// slash); the UI prefixes it. `prompt` is the template inserted verbatim into
// the textarea on pick. `icon` follows the same stable-key pattern as
// PromptSuggestion to keep the data layer React-free.
export type SlashCommandIconKey =
  | "summarize"
  | "explain"
  | "translate"
  | "rewrite"
  | "debug"
  | "code-review"
  | "draft-email"
  | "brainstorm";

export interface SlashCommand {
  id: string;
  name: string; // e.g. "summarize" — NO leading slash; UI prefixes it
  description: string;
  prompt: string;
  icon: SlashCommandIconKey;
}
