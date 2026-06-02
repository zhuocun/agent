// Shared domain types for the chat thread.
// Mirrors the PRD data model: typed multi-part messages (PRD 01 §4.4 / PRD 04),
// per-message model + cost transparency (PRD 07), and served-vs-requested
// substitution (PRD 01 §4.6 / PRD 07 §5).

export type ModelTierId = "fast" | "smart" | "pro" | "auto";

export interface ProviderDataPolicy {
  trainsOnData: boolean;
  trainingDefault: "never" | "opt_in" | "opt_out" | "unknown";
  dataResidency: string;
  retentionDays?: number | null;
  zeroDataRetentionAvailable: boolean;
  policyLabel: string;
}

export interface ModelTier {
  id: ModelTierId;
  label: string; // user-facing: never a raw model ID (PRD 06 §5.6)
  description: string;
  speedHint: "fastest" | "fast" | "balanced" | "slow";
  costHint: "lowest" | "low" | "medium" | "high";
  contextHint: string; // e.g. "1M"
  // Curated display name of the model this tier serves (e.g. "DeepSeek V4
  // Flash") — a friendly label, never a raw model ID. Filled by the BE from the
  // active provider backend. Empty for "auto" (its model varies per message via
  // the router), so the picker shows no single model for it.
  modelLabel: string;
  // Whether this tier can ground answers with a live web search. The composer's
  // web-search toggle is shown/enabled ONLY when the selected tier has this
  // true. Filled by the BE from the active provider backend (the mock in
  // model-tiers.ts is a realistic stand-in for the loading frame).
  supportsWebSearch: boolean;
  // Whether this tier accepts file attachments for the current turn.
  supportsAttachments: boolean;
  // Active backend route metadata. Mirrors api/app/schemas/tier.py and is
  // populated from the provider registry in bootstrap.
  providerId: string;
  providerLabel: string;
  providerRouteStatus: "available" | "pending" | "unavailable";
  defaultRouteEligible: boolean;
  dataPolicy: ProviderDataPolicy | null;
  providerOptions?: ProviderTierOption[];
  requiresPro?: boolean;
  platformAccess?: "free" | "pro";
}

export type ProviderRouteStatus = "available" | "pending" | "unavailable";

export interface ProviderTierOption {
  providerId: string;
  label: string;
  status: ProviderRouteStatus;
  modelLabel: string;
  supportsWebSearch: boolean;
  supportsAttachments: boolean;
  defaultRouteEligible: boolean;
  dataPolicy: ProviderDataPolicy | null;
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

// Served-vs-requested substitution detail (PRD 01 §4.6 / PRD 07 §5). Present
// only when the served tier/model differs from what the user requested
// (silent-downgrade prevention). Named so the full `ModelAttribution` (private
// surface) and the cost-stripped `PublicAttribution` (share surface) reuse one
// shape. Mirrors `Substitution` in api/app/schemas/message.py.
export interface Substitution {
  reasonCode: SubstitutionReasonCode;
  reasonText: string; // e.g. "answered by Fast because Pro was rate-limited"
}

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
  providerId?: string;
  providerLabel?: string;
  isByok: boolean;
  costUsd: number;
  costConfidence: "exact" | "estimate";
  breakdown: CostBreakdown;
  // Present only when served != requested (silent-downgrade prevention).
  substitution?: Substitution;
}

// A single web-search result surfaced as a source card under a grounded
// answer. Mirrors the BE `sources` SSE event item + the persisted `sources`
// message part (api/app/schemas/message.py). `snippet` / `domain` are
// best-effort and may be absent.
export interface SourceItem {
  id: number;
  title: string;
  url: string;
  snippet?: string;
  domain?: string;
}

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type ToolApprovalState =
  | "not_required"
  | "pending"
  | "approved"
  | "rejected";

export type ToolRunStatus =
  | "pending"
  | "awaiting_approval"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type MessagePart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string; durationSec?: number }
  | { type: "status"; label: string; state: "active" | "done" }
  // Web-search sources, rendered AFTER the answer text. Added to the shared
  // `MessagePart` union so it auto-flows to the share surface (`PublicMessage`
  // reuses `MessagePart`) and round-trips via GET /api/conversations/:id.
  | { type: "sources"; items: SourceItem[] }
  // User attachment metadata. Outgoing send requests may add transient payload
  // fields; the server strips those before persistence.
  | AttachmentPart
  // Tool/function calling foundation. The backend streams and persists these
  // around the web-search tool loop; future tools can reuse the same renderer
  // and share model.
  | {
      type: "tool_call";
      id: string;
      name: string;
      label?: string;
      status?: ToolRunStatus;
      approvalState?: ToolApprovalState;
      input?: Record<string, JsonValue>;
    }
  | {
      type: "tool_result";
      toolCallId: string;
      name: string;
      label?: string;
      status?: ToolRunStatus;
      approvalState?: ToolApprovalState;
      summary?: string;
      output?: Record<string, JsonValue>;
      error?: string;
    };

export interface AttachmentPart {
  type: "attachment";
  id: string;
  name: string;
  mediaType: "image" | "pdf" | "text";
  mimeType: string;
  sizeBytes: number;
  storagePolicy?: "transient";
  dataUrl?: string;
  contentBase64?: string;
}

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
  monthlySpendUsd?: number;
  monthlyQuotaUsd?: number;
  creditBalanceUsd?: number;
  platformRemainingUsd?: number | null;
  recentLedgerEntries?: UsageLedgerEntry[];
}

export interface UsageLedgerEntry {
  id: string;
  entryType: "grant" | "platform_debit" | "adjustment";
  amountUsd: number;
  description?: string | null;
  referenceType?: string | null;
  referenceId?: string | null;
  createdAt: string;
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
  matchSnippet?: string;
  matchedMessageId?: string | null;
}

// User-editable preferences surfaced in the settings panel (PRD 06 §5.7 / PRD 05).
// Privacy-first defaults: temporary off, training opt-in OFF.
export interface UserPreferences {
  defaultTierId: ModelTierId;
  temporaryByDefault: boolean;
  trainingOptIn: boolean; // default false — conversations are not used for training
  sendOnEnter: boolean;
  autoExpandReasoning: boolean;
  telemetryEnabled: boolean; // first-party product telemetry only
  customInstructions: string;
  retentionDays: 30 | 90 | null; // null = retain forever
}

// Account / billing identity for the sidebar footer + settings (PRD 05 / PRD 07 §5.8).
export interface AccountInfo {
  name: string;
  email: string;
  planLabel: string; // e.g. "Pro" — never a raw SKU
  billing?: BillingState;
  byokEnabled: boolean;
  byokMaskedKey?: string; // e.g. "sk-…4f2a", shown only when byokEnabled
  byokKeys?: ByokKeyStatus[];
  // Guest vs. registered discriminator (camelCase wire field). Authoritative
  // signal for gating the sign-in CTA, BYOK, and the sign-out row. Guests are
  // minted server-side without an email; registered accounts carry one.
  isAnonymous: boolean;
}

export interface BillingState {
  planId: "free" | "pro";
  planLabel: string;
  proEnabled: boolean;
  billingProvider?: "stripe" | "fake" | null;
  // Legacy Pro-checkout flag. New surfaces should use the per-kind flags below.
  checkoutAvailable: boolean;
  proCheckoutAvailable?: boolean;
  creditCheckoutAvailable?: boolean;
  portalAvailable: boolean;
  creditBalanceUsd: number;
}

export interface ByokKeyStatus {
  providerId: string;
  providerLabel: string;
  maskedKey: string;
  usable: boolean;
}

// Single source of truth for the guest/registered split. Prefer the
// authoritative `isAnonymous` wire field; fall back to email-presence only as
// a safety net for any payload that predates the field (PRD 04 §6: guests have
// null email). The `as` cast keeps the fallback honest if a caller passes an
// object that hasn't been refreshed yet.
export function isAnonymousAccount(account: AccountInfo): boolean {
  const flagged = (account as { isAnonymous?: unknown }).isAnonymous;
  if (typeof flagged === "boolean") return flagged;
  return account.email.trim().length === 0;
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

// --- Public-by-link share wire shapes (cost-stripped) -----------------------
//
// PRD 01 §4.10 / PRD 05 §4.3 / PRD 07 §6.4: a shared-by-link conversation shows
// the messages and the MODEL ATTRIBUTION but HIDES per-message cost. This is
// the deliberate exception to the cost-transparency surface — anyone with the
// link can read the conversation, so the per-turn cost ledger must never leak.
//
// These are NOT a filtered view over `ChatMessage` / `ModelAttribution`; they
// are a separate, deliberately narrow shape that has NOWHERE to put a cost
// field. The strip is therefore structural (the field can't exist), mirroring
// `api/app/schemas/share.py`. Reuse `MessagePart`, `Substitution`,
// `ModelTierId`, and `MessageRole` above — only the attribution differs (no
// cost / breakdown / confidence).

export interface PublicAttribution {
  requestedTierId: ModelTierId;
  servedTierId: ModelTierId;
  servedModelLabel: string; // e.g. "DeepSeek Chat"
  providerId?: string;
  providerLabel?: string;
  isByok: boolean;
  // Present only when served != requested. Same shape as the private surface.
  substitution?: Substitution;
}

export interface PublicMessage {
  id: string;
  role: MessageRole;
  parts: MessagePart[];
  createdAt: string; // ISO
  // Assistant turns carry model identity; user turns omit it.
  attribution?: PublicAttribution;
}

export interface PublicConversation {
  id: string;
  title: string;
  messages: PublicMessage[];
}

// Minting a share token for a conversation returns a RELATIVE path only; the
// FE assembles the absolute URL from its own origin (the BE never knows the
// public origin). Re-minting an already-shared conversation is idempotent and
// returns the SAME token.
export interface ShareLinkResponse {
  shareToken: string;
  sharePath: string; // relative, e.g. "/share/<token>"
}
