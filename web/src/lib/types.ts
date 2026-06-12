// Shared domain types for the chat thread.
// Mirrors the PRD data model: typed multi-part messages (PRD 01 §4.4 / PRD 04),
// per-message model + cost transparency (PRD 07), and served-vs-requested
// substitution (PRD 01 §4.6 / PRD 07 §5).

export type ModelTierId = "fast" | "smart" | "pro" | "auto";

// Agentic (multi-agent) turn mode. `single` wraps the normal agent loop as one
// orchestrator subagent; `deep_research` plans, fans out parallel worker
// subagents, and synthesizes their findings. Mirrors the BE send-body
// `agenticMode` literal (api/app/schemas/conversation.py). The FE only ever
// SENDS `deep_research` (the composer toggle); `single` exists so the union
// stays faithful to the wire contract.
export type AgenticMode = "single" | "deep_research";

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
  // Per-million-token LIST prices for this tier's served model, surfaced so the
  // composer can show a pre-send cost estimate (cost-estimate.ts). Filled by the
  // BE from the active provider backend's pricing; 0 for "auto" (the router
  // picks the model per turn, so there's no single price) and for any tier whose
  // binding is missing a price — the estimate UI shows "unavailable" then.
  listPriceInPerM: number;
  listPriceOutPerM: number;
  // Whether this tier accepts file attachments for the current turn.
  supportsAttachments: boolean;
  // Whether this tier can INTERPRET images (and native PDF document blocks).
  // DISTINCT from `supportsAttachments`: a tier may accept files (text/PDF as
  // transcript text) without being multimodal. When false the composer
  // auto-removes image attachments while keeping PDFs/text. Filled by the BE
  // from the active provider backend.
  supportsVision?: boolean;
  // Output modalities this tier's served model can PRODUCE (D22 precondition).
  // Defaults to ["text"] — every wired route is text-out today. Voice in v1
  // (dictation + read-aloud) runs ON-DEVICE in the browser via the Web Speech
  // API, so it is NOT reflected here as a provider output modality.
  modalitiesOut?: string[];
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
  supportsVision?: boolean;
  // Output modalities this route's model can PRODUCE (D22 precondition).
  // Defaults to ["text"] — mirrors `ModelTier` above.
  modalitiesOut?: string[];
  defaultRouteEligible: boolean;
  dataPolicy: ProviderDataPolicy | null;
  // Per-million-token LIST prices for this provider route's model. Mirror
  // `ModelTier` above so a per-provider estimate is possible; 0 when unpriced.
  listPriceInPerM: number;
  listPriceOutPerM: number;
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
  // Present only when structured output ("JSON mode") was requested for the
  // turn. `outputFormat` echoes the requested format; `outputValid` reports
  // whether the model's output parsed/validated as JSON. Mirrors the new
  // optional fields on the BE `terminal` frame's attribution.
  outputFormat?: "json_object" | "json_schema";
  outputValid?: boolean;
  // Transparent long-term memory (D19): how many saved facts were injected into
  // this turn. Present (and > 0) only when memory was applied — the FE renders
  // the "Memory used here" chip from this turn-level count. Mirrors the new
  // optional field on the BE `terminal` frame's attribution.
  memoryApplied?: number;
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
  // Origin class (PRD 07 §4.3 transparency contract). `web` is the only live
  // one today; `knowledge` (private RAG) and `connector` (third-party docs) are
  // RESERVED so the field round-trips now without a later migration. Absent is
  // treated as `web` by the UI.
  provenance?: "web" | "knowledge" | "connector";
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

// Agentic mode: a marker part opening one orchestrator subagent's section.
// Persisted (and streamed) ahead of that subagent's `subagentId`-tagged content
// parts so a reload can group the transcript by subagent and render per-worker
// activity + spend. `role` is the orchestration role (`primary` / `worker` /
// `aggregator` / `orchestrator`); `costUsd` / `attribution` are optional so a
// section can render before its subagent finishes. Mirrors `SubagentPart` in
// api/app/schemas/message.py. Present ONLY on agentic turns — the union
// addition is inert for every existing message.
export interface SubagentPart {
  type: "subagent";
  subagentId: string;
  label: string;
  role: string;
  attribution?: ModelAttribution;
  costUsd?: number;
}

export type MessagePart =
  | { type: "text"; text: string; subagentId?: string }
  | { type: "reasoning"; text: string; durationSec?: number; subagentId?: string }
  | { type: "status"; label: string; state: "active" | "done" }
  // Web-search sources, rendered AFTER the answer text. Added to the shared
  // `MessagePart` union so it auto-flows to the share surface (`PublicMessage`
  // reuses `MessagePart`) and round-trips via GET /api/conversations/:id.
  // `requested` is True when web search was EFFECTIVE for the turn: grounded ⇔
  // `items` non-empty; an empty `items` with `requested` is the ungrounded
  // state the UI marks "Answered without live sources".
  | { type: "sources"; items: SourceItem[]; requested?: boolean }
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
      subagentId?: string;
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
      subagentId?: string;
    }
  // Agentic mode subagent section marker (see `SubagentPart` above).
  | SubagentPart;

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
  // HITL pause: the turn ended in a terminal awaiting the user's tool-approval
  // decision. The bubble stays put and shows the approve/deny card; the
  // decision rides a follow-up message POST that resumes as a NEW bubble.
  | "awaiting_approval"
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
  // User-set monthly spend cap (PRD 07 §5.x). `null`/absent means no user cap.
  // Surfaced + edited in the settings budget UI.
  userBudgetUsd?: number | null;
  // The cap actually ENFORCED this period — the tighter of the user cap and any
  // platform cap. When this differs from `userBudgetUsd`, the platform cap is
  // binding and the settings UI shows the enforced figure.
  effectiveQuotaUsd?: number | null;
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

// --- Longitudinal spend analytics (PRD 05 §4.5 D27) -------------------------
//
// Mirrors api/app/schemas/account.py `SpendAnalytics`. Two cost bases are
// surfaced HONESTLY because they legitimately differ:
//   - `cumulativeMeterUsd`: every generation triggered (incl. regenerated /
//     deleted turns) — `sum(usage_rollup.cost_usd)`.
//   - `survivingMessagesUsd`: only the assistant messages still in the threads —
//     `sum(message.cost_usd)`.
export interface SpendDayBucket {
  date: string; // "YYYY-MM-DD" (UTC day)
  costUsd: number;
  messageCount: number;
}

export interface SpendModelBucket {
  label: string;
  tierId?: string | null;
  providerId?: string | null;
  costUsd: number;
  messageCount: number;
}

export interface SpendConversationBucket {
  conversationId: string;
  title: string;
  costUsd: number;
  messageCount: number;
}

export interface SpendAnalytics {
  rangeDays: number;
  currency: string; // "USD"
  survivingMessagesUsd: number;
  cumulativeMeterUsd: number;
  daily: SpendDayBucket[];
  byModel: SpendModelBucket[];
  byConversation: SpendConversationBucket[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  selectedTierId: ModelTierId;
  isTemporary: boolean;
  // Per-conversation retention override in days (D31). `null`/absent = inherit
  // the user's global `UserPreferences.retentionDays`. Drives the kebab
  // retention control + the "expires in ~N days" hint.
  retentionDays?: number | null;
  // Project/Space membership (D20). `null`/absent = unfiled. Drives the
  // Projects grouping in the sidebar + the "Assign to project" control.
  projectId?: string | null;
  // Archive flag (Conversation Org v2). `true` = hidden from the sidebar's main
  // list into the collapsible "Archived" section. Absent/false = active.
  archived?: boolean;
  // Assigned tag ids (Conversation Org v2). Drives the tag chips on the row +
  // the "Assign tags" picker. Absent/empty = no tags.
  tagIds?: string[];
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
  // Per-conversation retention override in days (D31). `null`/absent = inherit
  // the user's global retention. Echoed on the sidebar summary so the kebab
  // control + "expires in ~N days" hint render without a follow-up GET.
  retentionDays?: number | null;
  // Project/Space membership (D20). `null`/absent = unfiled. Echoed on the
  // sidebar summary so the Projects grouping renders without a follow-up GET.
  projectId?: string | null;
  // Archive flag (Conversation Org v2). `true` = hidden into the "Archived"
  // section. Echoed on the summary so the sidebar splits the list on first paint.
  archived?: boolean;
  // Assigned tag ids (Conversation Org v2). Echoed on the summary so tag chips +
  // the tag filter render without a follow-up GET. Absent/empty = no tags.
  tagIds?: string[];
  // Transparency-native fields populated by the advanced history-search dialog
  // (additive; absent on the plain sidebar/Cmd+K search results). Carry the
  // MATCHED message's served-model label, per-turn cost, and timestamp so each
  // result row can surface the transparency wedge inline.
  servedModelLabel?: string | null;
  costUsd?: number | null;
  matchedAt?: string | null;
}

// Filters for the advanced history-search dialog. Every field is optional; an
// omitted field means "no constraint" and the bare query behaves exactly like
// the existing conversation search. Mirrors the BE `GET /search` query params
// (`servedModel`, `costMin`, `costMax`, `dateFrom`, `dateTo`, `projectId`,
// `tagId`). Dates are ISO-8601 strings; cost is in USD; ids are UUID strings.
export interface SearchFilters {
  servedModel?: ModelTierId;
  costMin?: number;
  costMax?: number;
  dateFrom?: string;
  dateTo?: string;
  projectId?: string;
  tagId?: string;
}

// A Project/Space (D20): a thin scoping container that groups conversations and
// scopes the existing wedge controls — default tier, retention, per-conversation
// budget sub-cap, and shared custom instructions. Every setting is OPTIONAL and
// `null` means "inherit the user-global value" (a labeled default, not a lock).
export interface Project {
  id: string;
  name: string;
  customInstructions?: string | null;
  defaultTierId?: ModelTierId | null;
  retentionDays?: number | null;
  perConversationBudgetUsd?: number | null;
  createdAt: string;
  updatedAt: string;
}

// The bootstrap sidebar shape for a Project: the settings ride along so the
// FE pickers can render, but the timestamps stay out.
export interface ProjectSummary {
  id: string;
  name: string;
  customInstructions?: string | null;
  defaultTierId?: ModelTierId | null;
  retentionDays?: number | null;
  perConversationBudgetUsd?: number | null;
}

// A Tag (Conversation Org v2): a thin user-scoped label assignable to
// conversations and filterable in the sidebar. `color` is optional and the BE
// stores it opaquely (the FE picks a default when absent).
export interface Tag {
  id: string;
  name: string;
  color?: string | null;
  createdAt: string;
  updatedAt: string;
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
  // User-set monthly spend cap in USD, or null for no cap. Edited in the
  // settings budget UI; the BE enforces it (refusing turns once exceeded) and
  // echoes the effective figure back via `UsageBudget`.
  monthlyBudgetUsd: number | null;
  // User-set per-conversation spend ceiling in USD, or null for no cap. The BE
  // refuses the next platform-key turn once a conversation's accumulated
  // surviving-assistant cost reaches this cap (PRD 05 §4.5 D27).
  perConversationBudgetUsd: number | null;
  // Transparent long-term memory opt-in (D19). OFF by default. When on (and the
  // turn isn't temporary) the BE injects the user's saved facts into the turn.
  memoryEnabled: boolean;
  // User remaps of the app's keyboard shortcuts (D23). Keyed by stable
  // `ShortcutId` -> an override combo. An empty/missing entry for an action
  // means "use the built-in default". Optional on the wire so older bootstrap
  // payloads (and partial test stubs) still parse; the resolver treats a missing
  // map as empty. See `web/src/lib/shortcut-defaults.ts`.
  keyboardShortcuts?: KeyboardShortcuts;
}

// Stable, persistence-safe identifiers for each rebindable action (D23). These
// are the keys of the `keyboardShortcuts` override map and MUST stay in sync
// with the `ShortcutId` union driving `KEY_BINDINGS` in chat-thread.tsx. Kept
// here so the override map, the rebind dialog, and the resolver can share one
// type without importing the heavy chat-thread module.
export type ShortcutId =
  | "palette"
  | "new-chat"
  | "focus-composer"
  | "copy-last-response"
  | "copy-last-code"
  | "toggle-sidebar"
  | "custom-instructions"
  | "delete-chat"
  | "toggle-dictation"
  | "shortcuts"
  | "open-settings"
  | "toggle-theme"
  | "search-history";

// A single user-supplied shortcut override (D23). Mirrors the matcher-
// significant fields of `ShortcutKeys` (`web/src/lib/use-keyboard-shortcuts.ts`)
// and the BE `ShortcutOverride` schema. `allowInInput` is intentionally NOT part
// of an override — it's a per-action trait owned by the built-in default.
export interface ShortcutOverride {
  key: string;
  mod?: boolean; // Cmd on Mac, Ctrl elsewhere
  shift?: boolean;
}

// The override map persisted on `preferences.keyboardShortcuts`. Mirrors the BE
// `KeyboardShortcuts` type. Permissive on the value side; unknown action ids are
// ignored by the resolver.
export type KeyboardShortcuts = Partial<Record<ShortcutId, ShortcutOverride>>;

// A single editable, attributed long-term-memory fact (D19). The glass-box
// differentiator: every fact the assistant may use is a row the user can read,
// edit, and delete. Mirrors api/app/schemas/memory.py `MemoryFact`.
export interface MemoryFact {
  id: string;
  content: string;
  source: "manual" | "conversation";
  sourceConversationId?: string | null;
  createdAt: string; // ISO
  updatedAt: string; // ISO
}

// A user-authored, reusable prompt template (D23). Selecting one prefills the
// composer with `body` — a PURE composer prefill, NO model/cost/provider
// change. `body` may carry literal variable placeholders (e.g. `{{topic}}`)
// the user fills in after insertion. Mirrors
// api/app/schemas/prompt_template.py `PromptTemplate`.
export interface PromptTemplate {
  id: string;
  title: string;
  body: string;
  description?: string | null;
  createdAt: string; // ISO
  updatedAt: string; // ISO
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

// --- Trust surfaces (PRD 07 §6.5 / PRD 05 §7.4 / PRD 08 §5.6) ----------------
//
// The data-access activity log, the per-message processing-provenance rollup,
// and the moderation-appeal capture. Mirror api/app/schemas/activity.py. None
// of these carry message content — only event-relevant ids/labels and counts.

// One row of the data-access activity log (an audit-event projection). `details`
// is an opaque, content-free bag of event-relevant ids/labels (e.g. provider,
// conversationId, reasonCode) keyed per `eventType`.
export interface ActivityEvent {
  id: string;
  eventType: string;
  details: Record<string, unknown>;
  createdAt: string; // ISO
}

// One provider's slice of "where your messages were processed". `jurisdiction`
// is read from the LIVE provider registry (data residency); `null` means the
// provider has no published policy ("policy unavailable").
export interface DataProcessingBucket {
  providerId: string;
  providerLabel: string;
  jurisdiction: string | null;
  messageCount: number;
  isByokCount: number;
  platformCount: number;
  substitutionCount: number;
}

export interface DataProcessingRollup {
  totalAttributed: number;
  byProvider: DataProcessingBucket[];
}

// Request-review capture for a blocked turn. All fields optional — the FE
// forwards whatever the error envelope carried plus an optional free-text note.
export interface ModerationAppealRequest {
  reasonCode?: string;
  source?: string;
  note?: string;
}

// --- Model & data-policy directory (PRD 05 §4.5 / PRD 07 §5) -----------------
//
// A browsable catalog of every provider route in the registry plus its tiers'
// capabilities + list prices, so a user can compare data policies and pricing.
// Mirrors api/app/schemas/directory.py. A route with `dataPolicy: null` has no
// published policy and the UI renders "policy unavailable" — never a guess.

export interface ModelDirectoryTier {
  tierId: ModelTierId;
  modelLabel: string;
  listPriceInPerM: number;
  listPriceOutPerM: number;
  supportsWebSearch: boolean;
  supportsAttachments: boolean;
  supportsVision: boolean;
  // Output modalities this tier's model can PRODUCE (D22 precondition).
  // Defaults to ["text"] — every wired route is text-out today.
  modalitiesOut?: string[];
}

export interface ModelDirectoryEntry {
  providerId: string;
  label: string;
  status: ProviderRouteStatus;
  defaultRouteEligible: boolean;
  dataPolicy: ProviderDataPolicy | null;
  tiers: ModelDirectoryTier[];
}

// --- Public platform status (PRD 08 §10) ------------------------------------
//
// The calm health verdict behind the /status page + degraded banner. Derived
// server-side from recent Stream telemetry; carries no user/conversation
// content. Mirrors api/app/schemas/status.py.
export interface PlatformStatus {
  status: "operational" | "degraded";
  windowSeconds: number;
  sampleSize: number;
  errorCount: number;
  updatedAt: string; // ISO
}

// Minting a share token for a conversation returns a RELATIVE path only; the
// FE assembles the absolute URL from its own origin (the BE never knows the
// public origin). Re-minting an already-shared conversation is idempotent and
// returns the SAME token.
export interface ShareLinkResponse {
  shareToken: string;
  sharePath: string; // relative, e.g. "/share/<token>"
}
