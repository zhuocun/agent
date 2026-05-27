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

export type SubstitutionReasonCode =
  | "auto_downgrade"
  | "provider_fallback"
  | "rate_limited"
  | "capacity_reroute"
  | "deprecated_model"
  | "gateway_route";

// Faithful UI subset of PRD 07 §4.1 cost_breakdown.
export interface LongContext {
  flat: boolean; // Anthropic-style: no long-context surcharge (first-class positive fact)
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
  servedModelLabel: string; // e.g. "Claude Haiku 4.5"
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
