// Typed fetch wrapper for the FastAPI backend.
//
// Reads NEXT_PUBLIC_API_BASE_URL at module load. Production sets it to an
// empty string so browser requests stay same-origin (/api/*) and Next rewrites
// them to Fly. Local/e2e runs may set it to http://localhost:8000 to exercise
// the backend's direct-CORS path. The value is inlined at build time by Next,
// so this MUST be a direct `process.env.NEXT_PUBLIC_API_BASE_URL` reference
// (dynamic lookups are not inlined).
// See node_modules/next/dist/docs/01-app/02-guides/environment-variables.md.
import type {
  AccountInfo,
  ActivityEvent,
  Conversation,
  ConversationSummary,
  DataProcessingRollup,
  Feedback,
  MemoryFact,
  ModelDirectoryEntry,
  ModelTier,
  ModelTierId,
  ModerationAppealRequest,
  PlatformStatus,
  Project,
  ProjectSummary,
  PromptSuggestion,
  PromptTemplate,
  PublicConversation,
  SearchFilters,
  ShareLinkResponse,
  SpendAnalytics,
  Tag,
  UsageBudget,
  UserPreferences,
} from "@/lib/types";

// --- Wire types -------------------------------------------------------------

export interface BootstrapResponse {
  account: AccountInfo;
  preferences: UserPreferences;
  usage: UsageBudget;
  modelTiers: ModelTier[];
  suggestions: PromptSuggestion[];
  conversations: ConversationSummary[];
  // Projects/Spaces (D20). May be absent on a stale BE; the FE treats a missing
  // value as an empty list.
  projects?: ProjectSummary[];
  // Tags (Conversation Org v2). May be absent on a stale BE; the FE treats a
  // missing value as an empty list.
  tags?: Tag[];
  // Agentic mode availability. True only when the server has BOTH
  // `AGENTIC_ENABLED` and `TOOLS_ENABLED` on. Gates the composer's Deep
  // Research toggle so the FE never offers a mode the server would ignore.
  // May be absent on a stale BE; the FE treats a missing value as false.
  agenticEnabled?: boolean;
}

export type BillingCheckoutKind = "pro_subscription" | "credit_purchase";

export interface BillingSessionResponse {
  url: string;
}

export interface AccountExportResponse {
  account: AccountInfo;
  preferences: UserPreferences;
  usage: UsageBudget;
  conversations: Conversation[];
  memoryFacts?: MemoryFact[];
  projects?: Project[];
  tags?: Tag[];
  exportedAt: string;
}

export type ErrorSeverity = "info" | "warning" | "error" | "fatal";
export type ErrorActionKind = "retry" | "open_settings" | "dismiss";

export interface ErrorActionPayload {
  label: string;
  kind: ErrorActionKind;
}

export interface ApiErrorEnvelope {
  code: string;
  severity: ErrorSeverity;
  title: string;
  body: string;
  actions?: ErrorActionPayload[];
  retryAfterMs?: number;
  meta?: Record<string, unknown>;
}

// --- Error classes ----------------------------------------------------------

export class ApiError extends Error {
  readonly code: string;
  readonly severity: ErrorSeverity;
  readonly title: string;
  readonly body: string;
  readonly actions?: ErrorActionPayload[];
  readonly retryAfterMs?: number;
  readonly meta?: Record<string, unknown>;
  readonly status: number;

  constructor(envelope: ApiErrorEnvelope, status: number) {
    super(`${envelope.code}: ${envelope.title}`);
    this.name = "ApiError";
    this.code = envelope.code;
    this.severity = envelope.severity;
    this.title = envelope.title;
    this.body = envelope.body;
    this.actions = envelope.actions;
    this.retryAfterMs = envelope.retryAfterMs;
    this.meta = envelope.meta;
    this.status = status;
  }
}

export class ApiNetworkError extends Error {
  readonly cause?: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = "ApiNetworkError";
    this.cause = cause;
  }
}

// --- Base URL & request plumbing -------------------------------------------

const API_BASE_URL: string | undefined = process.env.NEXT_PUBLIC_API_BASE_URL;

function resolveUrl(path: string): string {
  if (API_BASE_URL === undefined) {
    throw new ApiNetworkError(
      "NEXT_PUBLIC_API_BASE_URL is not set. Define it as an empty string for same-origin /api/*, or as a backend origin for direct CORS.",
    );
  }
  // Empty string = same-origin (rewrite path); use the path as-is.
  if (API_BASE_URL === "") return path;
  return `${API_BASE_URL}${path}`;
}

interface RequestOptions {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

function isErrorEnvelope(value: unknown): value is { error: ApiErrorEnvelope } {
  if (typeof value !== "object" || value === null) return false;
  const err = (value as { error?: unknown }).error;
  if (typeof err !== "object" || err === null) return false;
  const e = err as Record<string, unknown>;
  return (
    typeof e.code === "string" &&
    typeof e.severity === "string" &&
    typeof e.title === "string" &&
    typeof e.body === "string"
  );
}

async function request<T>(path: string, opts: RequestOptions): Promise<T> {
  const url = resolveUrl(path);
  const headers: Record<string, string> = {};
  let body: string | undefined;
  if (opts.body !== undefined) {
    // CORS allow_headers is restricted to Content-Type only (api/app/main.py),
    // so we never send Accept.
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: opts.method,
      credentials: "include",
      headers,
      body,
      signal: opts.signal,
    });
  } catch (cause) {
    throw new ApiNetworkError(
      `Network request to ${opts.method} ${url} failed`,
      cause,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch (cause) {
    if (response.ok) {
      throw new ApiNetworkError(
        `Response from ${opts.method} ${url} was not valid JSON`,
        cause,
      );
    }
    throw new ApiError(
      {
        code: "UNKNOWN",
        severity: "error",
        title: "Request failed",
        body: `HTTP ${response.status} with non-JSON body.`,
      },
      response.status,
    );
  }

  if (response.status >= 400) {
    if (isErrorEnvelope(parsed)) {
      throw new ApiError(parsed.error, response.status);
    }
    throw new ApiError(
      {
        code: "UNKNOWN",
        severity: "error",
        title: "Request failed",
        body: `HTTP ${response.status} with unexpected body shape.`,
      },
      response.status,
    );
  }

  return parsed as T;
}

// --- Verb methods -----------------------------------------------------------

export const apiClient = {
  get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: "GET", signal });
  },
  post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: "POST", body, signal });
  },
  put<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: "PUT", body, signal });
  },
  patch<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: "PATCH", body, signal });
  },
  del<T = void>(path: string, signal?: AbortSignal, body?: unknown): Promise<T> {
    return request<T>(path, { method: "DELETE", body, signal });
  },
};

export default apiClient;

// --- Typed endpoint wrappers ------------------------------------------------

export function fetchBootstrap(signal?: AbortSignal): Promise<BootstrapResponse> {
  return apiClient.get<BootstrapResponse>("/api/bootstrap", signal);
}

// Download a full account export — account, preferences, usage, and every
// conversation — as a single JSON payload. Available to anonymous callers too.
export function fetchAccountExport(
  signal?: AbortSignal,
): Promise<AccountExportResponse> {
  return apiClient.get<AccountExportResponse>("/api/account/export", signal);
}

// Fetch the caller's longitudinal spend analytics (PRD 05 §4.5 D27). `days` is
// clamped server-side to 1..365 (default 30). Available to anonymous callers —
// it's their own data.
export function fetchSpendAnalytics(
  days?: number,
  signal?: AbortSignal,
): Promise<SpendAnalytics> {
  const path =
    days === undefined
      ? "/api/account/spend"
      : `/api/account/spend?days=${encodeURIComponent(String(days))}`;
  return apiClient.get<SpendAnalytics>(path, signal);
}

// Permanently delete the caller's account and all conversations. The BE requires
// a typed confirmation (the account email, or "DELETE" for anonymous callers),
// returns 204, and clears the `sid` cookie; the helper resolves to undefined.
export function deleteAccount(
  confirmation: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.del("/api/account", signal, { confirmation });
}

export function fetchConversation(
  id: string,
  signal?: AbortSignal,
): Promise<Conversation> {
  return apiClient.get<Conversation>(
    `/api/conversations/${encodeURIComponent(id)}`,
    signal,
  );
}

export function searchConversations(
  query: string,
  signal?: AbortSignal,
): Promise<ConversationSummary[]> {
  const params = new URLSearchParams({ q: query });
  return apiClient.get<ConversationSummary[]>(
    `/api/conversations/search?${params.toString()}`,
    signal,
  );
}

// Advanced history search: the same `/api/conversations/search` wire path as
// `searchConversations`, extended with the transparency-native filters. Each
// filter is appended only when set, so an empty `filters` produces the exact
// same request as the plain search. Backs the advanced-search dialog (NOT the
// sidebar box / Cmd+K palette, which keep using `searchConversations`).
export function searchHistory(
  query: string,
  filters: SearchFilters,
  signal?: AbortSignal,
): Promise<ConversationSummary[]> {
  const params = new URLSearchParams({ q: query });
  if (filters.servedModel) params.set("servedModel", filters.servedModel);
  if (filters.costMin != null) params.set("costMin", String(filters.costMin));
  if (filters.costMax != null) params.set("costMax", String(filters.costMax));
  if (filters.dateFrom) params.set("dateFrom", filters.dateFrom);
  if (filters.dateTo) params.set("dateTo", filters.dateTo);
  if (filters.projectId) params.set("projectId", filters.projectId);
  if (filters.tagId) params.set("tagId", filters.tagId);
  return apiClient.get<ConversationSummary[]>(
    `/api/conversations/search?${params.toString()}`,
    signal,
  );
}

export function createConversation(
  body: {
    selectedTierId: ModelTierId;
    isTemporary?: boolean;
    providerId?: string;
    // Project/Space to file the new conversation under (D20). When the project
    // has a `defaultTierId`, the BE pre-seeds the conversation's tier from it.
    projectId?: string;
  },
  signal?: AbortSignal,
): Promise<Conversation> {
  return apiClient.post<Conversation>("/api/conversations", body, signal);
}

export function branchConversation(
  id: string,
  body: { messageId: string },
  signal?: AbortSignal,
): Promise<Conversation> {
  return apiClient.post<Conversation>(
    `/api/conversations/${encodeURIComponent(id)}/branch`,
    body,
    signal,
  );
}

export function patchConversation(
  id: string,
  // `retentionDays` and `projectId` are THREE-VALUED to match the BE
  // (D31/D20): omit the key to leave it unchanged, send a value to set it, or
  // send `null` to clear it (retention -> inherit global; project -> un-file).
  // `archived` is a plain bool toggle; `tagIds` is a FULL REPLACE of the
  // conversation's tag set (omit = unchanged, `[]` = clear all) — Conversation
  // Org v2.
  body: {
    title?: string;
    pinned?: boolean;
    retentionDays?: number | null;
    projectId?: string | null;
    archived?: boolean;
    tagIds?: string[];
  },
  signal?: AbortSignal,
): Promise<Conversation> {
  return apiClient.patch<Conversation>(
    `/api/conversations/${encodeURIComponent(id)}`,
    body,
    signal,
  );
}

export function deleteConversation(
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.del(
    `/api/conversations/${encodeURIComponent(id)}`,
    signal,
  );
}

export function postConversationStop(
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.post<void>(
    `/api/conversations/${encodeURIComponent(id)}/stop`,
    undefined,
    signal,
  );
}

// Mint (or re-fetch — the BE is idempotent) a public share link for a
// conversation. Returns a RELATIVE `sharePath`; the caller assembles the
// absolute URL from `window.location.origin`. 404 when the conversation isn't
// owned by the caller or is a temporary chat.
export function createShareLink(
  id: string,
  signal?: AbortSignal,
): Promise<ShareLinkResponse> {
  return apiClient.post<ShareLinkResponse>(
    `/api/conversations/${encodeURIComponent(id)}/share`,
    undefined,
    signal,
  );
}

// Revoke a conversation's share link. Idempotent: revoking an unshared/
// already-revoked conversation still resolves (the BE returns 204). 404 when
// the conversation isn't owned by the caller or is a temporary chat.
export function deleteShareLink(
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.del(
    `/api/conversations/${encodeURIComponent(id)}/share`,
    signal,
  );
}

export function putPreferences(
  prefs: UserPreferences,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.put<void>("/api/preferences", prefs, signal);
}

export function postFeedback(
  messageId: string,
  feedback: Feedback,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.post<void>(
    `/api/messages/${encodeURIComponent(messageId)}/feedback`,
    { feedback },
    signal,
  );
}

export type TelemetryEventType =
  | "settings.opened"
  | "usage.viewed"
  | "attribution.opened"
  | "tier.changed"
  | "provider.changed"
  | "byok.form_opened"
  | "byok.saved"
  | "byok.deleted"
  | "install_prompt.shown"
  | "install_prompt.accepted"
  | "install_prompt.dismissed";

export function postTelemetryEvent(
  eventType: TelemetryEventType,
  properties?: Record<string, string | number | boolean | null>,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.post<void>(
    "/api/analytics/events",
    { eventType, properties: properties ?? {} },
    signal,
  );
}

export function putByok(
  body: { provider: string; apiKey: string },
  signal?: AbortSignal,
): Promise<AccountInfo> {
  return apiClient.put<AccountInfo>("/api/account/byok", body, signal);
}

export function deleteByok(
  provider: string,
  signal?: AbortSignal,
): Promise<AccountInfo> {
  return apiClient.del<AccountInfo>(
    `/api/account/byok/${encodeURIComponent(provider)}`,
    signal,
  );
}

export function createBillingCheckout(
  body: { kind: BillingCheckoutKind },
  signal?: AbortSignal,
): Promise<BillingSessionResponse> {
  return apiClient.post<BillingSessionResponse>(
    "/api/billing/checkout",
    body,
    signal,
  );
}

export function createBillingPortal(
  signal?: AbortSignal,
): Promise<BillingSessionResponse> {
  return apiClient.post<BillingSessionResponse>(
    "/api/billing/portal",
    undefined,
    signal,
  );
}

export function postAuthUpgrade(
  body: { email: string; password?: string },
  signal?: AbortSignal,
): Promise<AccountInfo> {
  return apiClient.post<AccountInfo>("/api/auth/upgrade", body, signal);
}

export function postAuthLogin(
  email: string,
  password: string,
  signal?: AbortSignal,
): Promise<AccountInfo> {
  return apiClient.post<AccountInfo>(
    "/api/auth/login",
    { email, password },
    signal,
  );
}

export function postAuthSignout(signal?: AbortSignal): Promise<void> {
  return apiClient.post<void>("/api/auth/signout", undefined, signal);
}

// --- Trust surfaces ---------------------------------------------------------

// The data-access activity log: the caller's own audit events, newest-first.
// Anonymous-allowed; the BE scopes to the caller and never returns another
// user's rows. `before` is the ISO `createdAt` of the oldest row seen so far,
// used as a keyset cursor for "Load more".
export function fetchActivity(
  before?: string,
  limit?: number,
  signal?: AbortSignal,
): Promise<ActivityEvent[]> {
  const params = new URLSearchParams();
  if (before) params.set("before", before);
  if (limit) params.set("limit", String(limit));
  const query = params.toString();
  return apiClient.get<ActivityEvent[]>(
    `/api/account/activity${query ? `?${query}` : ""}`,
    signal,
  );
}

// "Where your messages were processed": a provider rollup computed from the
// caller's persisted per-message attribution, with the jurisdiction read from
// the live provider registry. Anonymous-allowed.
export function fetchDataProcessing(
  signal?: AbortSignal,
): Promise<DataProcessingRollup> {
  return apiClient.get<DataProcessingRollup>(
    "/api/account/data-processing",
    signal,
  );
}

// Request review of a blocked turn. Records a `moderation.appeal` audit event
// and resolves on the BE's 204.
export function postModerationAppeal(
  body: ModerationAppealRequest,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.post<void>("/api/account/moderation-appeal", body, signal);
}

// --- Transparent long-term memory (D19) -------------------------------------
//
// The editable, attributed fact ledger. All caller-scoped + anonymous-allowed;
// each mutation emits a `memory.fact_*` audit event on the BE.

export function fetchMemoryFacts(signal?: AbortSignal): Promise<MemoryFact[]> {
  return apiClient.get<MemoryFact[]>("/api/account/memory", signal);
}

export function createMemoryFact(
  content: string,
  signal?: AbortSignal,
): Promise<MemoryFact> {
  return apiClient.post<MemoryFact>("/api/account/memory", { content }, signal);
}

export function updateMemoryFact(
  id: string,
  content: string,
  signal?: AbortSignal,
): Promise<MemoryFact> {
  return apiClient.patch<MemoryFact>(
    `/api/account/memory/${encodeURIComponent(id)}`,
    { content },
    signal,
  );
}

export function deleteMemoryFact(
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.del(`/api/account/memory/${encodeURIComponent(id)}`, signal);
}

// --- Projects/Spaces (D20) --------------------------------------------------
//
// Thin scoping containers for conversations. All caller-scoped +
// anonymous-allowed; each mutation emits a `project.*` audit event on the BE.
// The four settings on create/patch are OPTIONAL; on PATCH they are
// THREE-VALUED (omit = unchanged, value = set, `null` = clear back to inherit).

export interface ProjectCreateInput {
  name: string;
  customInstructions?: string | null;
  defaultTierId?: ModelTierId | null;
  retentionDays?: number | null;
  perConversationBudgetUsd?: number | null;
}

export interface ProjectUpdateInput {
  name?: string;
  customInstructions?: string | null;
  defaultTierId?: ModelTierId | null;
  retentionDays?: number | null;
  perConversationBudgetUsd?: number | null;
}

export function fetchProjects(signal?: AbortSignal): Promise<Project[]> {
  return apiClient.get<Project[]>("/api/projects", signal);
}

export function createProject(
  body: ProjectCreateInput,
  signal?: AbortSignal,
): Promise<Project> {
  return apiClient.post<Project>("/api/projects", body, signal);
}

export function updateProject(
  id: string,
  body: ProjectUpdateInput,
  signal?: AbortSignal,
): Promise<Project> {
  return apiClient.patch<Project>(
    `/api/projects/${encodeURIComponent(id)}`,
    body,
    signal,
  );
}

export function deleteProject(
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.del(`/api/projects/${encodeURIComponent(id)}`, signal);
}

// --- Tags (Conversation Org v2) ---------------------------------------------
//
// User-scoped labels assignable to conversations. All caller-scoped +
// anonymous-allowed; each mutation emits a `tag.*` audit event on the BE.
// `color` is optional on create/patch; on PATCH it is THREE-VALUED (omit =
// unchanged, value = set, `null` = clear the color).

export interface TagCreateInput {
  name: string;
  color?: string | null;
}

export interface TagUpdateInput {
  name?: string;
  color?: string | null;
}

export function fetchTags(signal?: AbortSignal): Promise<Tag[]> {
  return apiClient.get<Tag[]>("/api/tags", signal);
}

export function createTag(
  body: TagCreateInput,
  signal?: AbortSignal,
): Promise<Tag> {
  return apiClient.post<Tag>("/api/tags", body, signal);
}

export function updateTag(
  id: string,
  body: TagUpdateInput,
  signal?: AbortSignal,
): Promise<Tag> {
  return apiClient.patch<Tag>(
    `/api/tags/${encodeURIComponent(id)}`,
    body,
    signal,
  );
}

export function deleteTag(id: string, signal?: AbortSignal): Promise<void> {
  return apiClient.del(`/api/tags/${encodeURIComponent(id)}`, signal);
}

// --- Bulk conversation actions (Conversation Org v2) ------------------------
//
// Multi-select over the caller's OWN conversations. Foreign ids are silently
// ignored by the BE (IDOR-safe), so `affected` may be lower than the number of
// ids sent. `tagId` is required for the `tag`/`untag` actions.

export type BulkConversationAction =
  | "archive"
  | "unarchive"
  | "delete"
  | "tag"
  | "untag";

export interface BulkConversationInput {
  conversationIds: string[];
  action: BulkConversationAction;
  tagId?: string;
}

export interface BulkConversationResponse {
  affected: number;
}

export function bulkConversationAction(
  body: BulkConversationInput,
  signal?: AbortSignal,
): Promise<BulkConversationResponse> {
  return apiClient.post<BulkConversationResponse>(
    "/api/conversations/bulk",
    body,
    signal,
  );
}

// --- Prompt library (D23) ---------------------------------------------------
//
// User-authored, reusable prompt templates. All caller-scoped +
// anonymous-allowed; each mutation emits a `prompt_template.*` audit event on
// the BE. Selecting a template prefills the composer (pure prefill).

export interface PromptTemplateInput {
  title: string;
  body: string;
  description?: string | null;
}

export function fetchPromptTemplates(
  signal?: AbortSignal,
): Promise<PromptTemplate[]> {
  return apiClient.get<PromptTemplate[]>(
    "/api/account/prompt-templates",
    signal,
  );
}

export function createPromptTemplate(
  input: PromptTemplateInput,
  signal?: AbortSignal,
): Promise<PromptTemplate> {
  return apiClient.post<PromptTemplate>(
    "/api/account/prompt-templates",
    input,
    signal,
  );
}

export function updatePromptTemplate(
  id: string,
  input: PromptTemplateInput,
  signal?: AbortSignal,
): Promise<PromptTemplate> {
  return apiClient.patch<PromptTemplate>(
    `/api/account/prompt-templates/${encodeURIComponent(id)}`,
    input,
    signal,
  );
}

export function deletePromptTemplate(
  id: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.del(
    `/api/account/prompt-templates/${encodeURIComponent(id)}`,
    signal,
  );
}

// The model & data-policy directory: every provider route in the registry with
// its data policy and per-tier capabilities + list prices. Anonymous-allowed;
// the catalog is identical for every caller (registry-derived).
export function fetchModelDirectory(
  signal?: AbortSignal,
): Promise<ModelDirectoryEntry[]> {
  return apiClient.get<ModelDirectoryEntry[]>(
    "/api/models/directory",
    signal,
  );
}

// Public platform health summary backing the /status page + degraded banner.
// PUBLIC on the BE (no auth/cookie) — it routes through the same same-origin
// `/api/*` wire path as everything else and works unauthenticated.
export function fetchPlatformStatus(
  signal?: AbortSignal,
): Promise<PlatformStatus> {
  return apiClient.get<PlatformStatus>("/api/status", signal);
}

// Public-by-link read. UNAUTHENTICATED on the BE (no cookie minted) — the share
// token IS the capability. We still route through the same `request()` helper
// for one wire path; in production that means the FE `/api/*` rewrite, while
// local/e2e can also target the backend origin directly. Including credentials
// is harmless here since the BE never reads a session for this route. An
// unknown or revoked token surfaces as an `ApiError` with `.status === 404`,
// which the share page maps to its "no longer available" empty state.
export function fetchPublicConversation(
  token: string,
  signal?: AbortSignal,
): Promise<PublicConversation> {
  return apiClient.get<PublicConversation>(
    `/api/share/${encodeURIComponent(token)}`,
    signal,
  );
}
