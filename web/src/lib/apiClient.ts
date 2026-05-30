// Typed fetch wrapper for the FastAPI backend.
//
// Reads NEXT_PUBLIC_API_BASE_URL at module load. The value is inlined at build
// time by Next, so this MUST be a direct `process.env.NEXT_PUBLIC_API_BASE_URL`
// reference (dynamic lookups are not inlined).
// See node_modules/next/dist/docs/01-app/02-guides/environment-variables.md.
import type {
  AccountInfo,
  Conversation,
  ConversationSummary,
  Feedback,
  ModelTier,
  ModelTierId,
  PromptSuggestion,
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
      "NEXT_PUBLIC_API_BASE_URL is not set. Define it in web/.env.local (or your deploy env) before making API calls.",
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
  del<T = void>(path: string, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: "DELETE", signal });
  },
};

export default apiClient;

// --- Typed endpoint wrappers ------------------------------------------------

export function fetchBootstrap(signal?: AbortSignal): Promise<BootstrapResponse> {
  return apiClient.get<BootstrapResponse>("/api/bootstrap", signal);
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

export function createConversation(
  body: { selectedTierId: ModelTierId; isTemporary?: boolean },
  signal?: AbortSignal,
): Promise<Conversation> {
  return apiClient.post<Conversation>("/api/conversations", body, signal);
}

export function patchConversation(
  id: string,
  body: { title?: string; pinned?: boolean },
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
