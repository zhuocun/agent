"use client";

// Streaming SSE consumer for `POST /api/conversations/:id/messages`.
//
// `useApiStream` is a drop-in replacement for `useMockStream` from
// `./use-mock-stream` — same `{ state, start, stop, reset }` shape, same
// `onTerminal` callback semantics — but `start` takes network args and the
// turn drives a real fetch + SSE consume loop instead of a setInterval.
//
// Wire protocol (matches api/app/streaming/sse.py + handler.py):
//
//   event: submitted          data: { messageId, streamId? }
//   event: reasoning_delta    data: { text }
//   event: reasoning_done     data: {}
//   event: status             data: { label, state }
//   event: sources            data: { items }
//   event: tool_call          data: tool-call part
//   event: tool_result        data: tool-result part
//   event: answer_delta       data: { text }
//   event: terminal           data: { status: "done", messageId, attribution }
//   event: error              data: ErrorEnvelope     (final on failure)
//
// `submitted` always lands first. Exactly one of `terminal` | `error` is the
// last server frame on a non-disconnect run. On client `stop()`, neither
// arrives — the server persists `status="stopped"` out-of-band and we
// synthesize a local `{ status: "stopped" }` terminal for the caller.
//
// We deliberately use `fetch` + ReadableStream rather than `EventSource`:
// this stream is a credentialed POST with a JSON body, and local/e2e may target
// the backend origin directly to exercise CORS. sse-starlette emits keep-alive
// comment lines (`:`-prefixed) every ~15s; the parser drops them. `data:` is
// always single-line JSON (Pydantic `model_dump_json`), so we don't bother
// stitching multi-line `data:` values.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  postConversationStop,
  type ApiErrorEnvelope,
} from "@/lib/apiClient";
import type {
  AttachmentPart,
  JsonValue,
  ModelAttribution,
  ModelTierId,
  MessagePart,
  ReasoningEffortId,
  SourceItem,
  StreamStatus,
} from "@/lib/types";

// --- Types -----------------------------------------------------------------

// Live web-search status line, accumulated from `status` SSE events. `null`
// until the BE emits one (web search off ⇒ never set). `state` flips to
// "done" when the search completes (the spinner stops; the label stays).
export interface SearchStatus {
  label: string;
  state: "active" | "done";
}

export interface ApiStreamState {
  status: StreamStatus;
  reasoning: string;
  reasoningStreaming: boolean;
  // FE-computed wall-clock seconds; the BE does not emit a duration.
  reasoningDurationSec: number;
  answer: string;
  // Web-search status line ("Searching the web…"); null when web search is off
  // or the BE hasn't emitted a `status` event yet.
  searchStatus: SearchStatus | null;
  // Web-search source cards, accumulated from `sources` SSE events. Empty until
  // the BE emits sources.
  sources: SourceItem[];
  // True once a `sources` frame marked web search as effective for the turn.
  // Distinguishes the ungrounded state (`sources` empty + `sourcesRequested`)
  // from a plain non-search turn (`sources` empty + `!sourcesRequested`).
  sourcesRequested: boolean;
  // Tool/function transcript parts emitted by the backend tool loop.
  toolParts: ToolTranscriptPart[];
}

export interface TerminalResult {
  // `awaiting_approval` is a server terminal (HITL pause): the turn ended
  // pending a tool-approval decision. The bubble is committed in place (with
  // its tool parts) and shows the approve/deny card. Like `done` it carries
  // the assistant message id, but never an `attribution` (the cost lands on
  // the resumed turn).
  status: "done" | "stopped" | "error" | "awaiting_approval";
  reasoning: string;
  reasoningDurationSec: number;
  answer: string;
  // Final web-search status line (if any) so finalized messages keep the
  // "Searched the web" part. Null when web search was off.
  searchStatus: SearchStatus | null;
  // Final web-search sources (if any) so finalized messages keep their cards.
  sources: SourceItem[];
  // Whether web search was effective for the turn — drives the grounded vs
  // ungrounded ("Answered without live sources") distinction on the committed
  // message.
  sourcesRequested: boolean;
  // Final tool/function transcript parts.
  toolParts: ToolTranscriptPart[];
  // From `submitted` — always present once the server sent the first frame.
  serverUserMessageId?: string;
  // From `terminal` — present on `done` only (never on stopped/error).
  serverAssistantMessageId?: string;
  // From `terminal` — present on `done` only.
  attribution?: ModelAttribution;
  // Present on `error` only. Carries the ErrorEnvelope from the server
  // (`event: error` frame), or a synthesized one for network/parse failures.
  error?: ApiError;
}

// `conversationId` is always required. The plan calls for the caller to
// `POST /api/conversations` first (when starting a brand-new chat) and pass
// the resulting id here — there is no "create-on-send" path through this
// hook. Empty string is NOT a valid input.
export interface StartArgs {
  conversationId: string;
  clientMessageId: string; // FE-minted UUID; powers idempotent replay.
  tierId: ModelTierId;
  // Optional provider route for per-turn model selection. Older backends ignore
  // the field; newer backends use it to resolve the tier binding.
  providerId?: string;
  text: string;
  isTemporary?: boolean;
  regenerate?: boolean;
  // Continue a previously-Stopped turn: keeps the persisted partial and streams
  // a NEW assistant message linked to the same user message. Sent only when
  // true (the BE treats absence as false). Mutually exclusive with
  // `regenerate` / `editMessageId`.
  continueTurn?: boolean;
  editMessageId?: string;
  // HITL resume: the user's approve/deny decision for a tool call the turn
  // paused on. Sent only when set; mutually exclusive with
  // `regenerate`/`continueTurn`/`editMessageId` on the wire. The BE replays the
  // paused turn, applies the decision (running or rejecting the tool), and
  // streams the post-tool answer as a NEW assistant message.
  toolApproval?: {
    toolCallId: string;
    decision: "approve" | "deny";
    editedInput?: Record<string, unknown>;
  };
  // Toggled on in the composer; sent only when true (the BE treats absence as
  // false). Gated upstream on the selected tier's `supportsWebSearch`.
  webSearch?: boolean;
  // Reasoning-effort knob picked in the composer. Sent only when set to a
  // non-"auto" value (the BE treats absence as "auto"), so the default path is
  // byte-identical to today's wire shape. Ignored by providers that don't
  // expose an effort control (the picker disables it for them upstream).
  reasoningEffort?: ReasoningEffortId;
  // Structured-output ("JSON mode") request. Sent only when JSON mode is on;
  // the BE treats absence as off. The FE only ever requests `json_object` (no
  // schema-editor UI), but the field carries the full format object the BE
  // accepts. Available on all tiers (not tier-gated like `webSearch`).
  responseFormat?: { type: "json_object" };
  // Attachment metadata plus transient payload bytes for the current request.
  // The BE strips payload bytes before message persistence.
  attachments?: AttachmentPart[];
}

const INITIAL: ApiStreamState = {
  status: "idle",
  reasoning: "",
  reasoningStreaming: false,
  reasoningDurationSec: 0,
  answer: "",
  searchStatus: null,
  sources: [],
  sourcesRequested: false,
  toolParts: [],
};

type ToolTranscriptPart = Extract<
  MessagePart,
  { type: "tool_call" | "tool_result" }
>;

// --- Base URL --------------------------------------------------------------

// Local helper: apiClient.ts does not export its `resolveUrl` so we duplicate
// the same `process.env.NEXT_PUBLIC_API_BASE_URL` read here. Production leaves
// it empty for same-origin /api/* requests through the Next rewrite; local/e2e
// may set it to the backend origin for direct-CORS coverage. The value is
// inlined at build time by Next, so it MUST be a direct env reference (not a
// destructured variable) for the dead-code elimination to work.
// See node_modules/next/dist/docs/01-app/02-guides/environment-variables.md.
function getApiBase(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (base === undefined) {
    throw new ApiError(
      {
        code: "CONFIG",
        severity: "error",
        title: "API base URL missing",
        body:
          "NEXT_PUBLIC_API_BASE_URL is not set. Define it as an empty string " +
          "for same-origin /api/*, or as a backend origin for direct CORS.",
      },
      0,
    );
  }
  return base; // empty string = same-origin (rewrite path).
}

// --- SSE parsing -----------------------------------------------------------

interface ParsedFrame {
  event: string;
  data: string;
}

// Parse a single SSE frame (already split off on `\n\n`). We honour:
//   - `:`-prefixed lines (sse-starlette keep-alive pings) → skip
//   - `event:` → name (last one wins, per spec)
//   - `data:` → single-line payload (server always emits single-line JSON)
// `id:`, `retry:`, and multi-line `data:` aggregation are intentionally
// unsupported — the server emits none of them.
function parseFrame(raw: string): ParsedFrame | null {
  let event = "";
  let data = "";
  let sawData = false;
  for (const rawLine of raw.split("\n")) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    if (colon === -1) continue;
    const field = line.slice(0, colon);
    // SSE spec: optional single space after the colon.
    const value = line[colon + 1] === " " ? line.slice(colon + 2) : line.slice(colon + 1);
    if (field === "event") {
      event = value;
    } else if (field === "data") {
      data = value;
      sawData = true;
    }
  }
  if (!sawData || !event) return null;
  return { event, data };
}

// --- Payload shape guards --------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function readStringField(obj: Record<string, unknown>, key: string): string | null {
  const v = obj[key];
  return typeof v === "string" ? v : null;
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!isRecord(value)) return false;
  return (
    typeof value.code === "string" &&
    typeof value.severity === "string" &&
    typeof value.title === "string" &&
    typeof value.body === "string"
  );
}

// `terminal` payload narrows to `{ status?, messageId, attribution? }`. `status`
// widens from the original `"done"`-only to also carry `"awaiting_approval"`
// (the HITL pause), defaulting to `"done"` when the field is absent (older
// backends). On the `awaiting_approval` pause there's no `attribution` yet — the
// cost lands on the resumed turn — so attribution is optional here.
type TerminalFrameStatus = "done" | "awaiting_approval";

interface TerminalPayload {
  status: TerminalFrameStatus;
  messageId: string;
  attribution?: ModelAttribution;
}

function readTerminalStatus(value: unknown): TerminalFrameStatus {
  return value === "awaiting_approval" ? "awaiting_approval" : "done";
}

function parseTerminal(value: unknown): TerminalPayload | null {
  if (!isRecord(value)) return null;
  const messageId = readStringField(value, "messageId");
  if (!messageId) return null;
  const status = readTerminalStatus(value.status);
  const attribution = value.attribution;
  // We don't deep-validate ModelAttribution here — the BE owns its wire
  // shape via Pydantic, and the FE renders it through `AttributionRow`
  // which tolerates partial shapes. A bad attribution is a contract bug,
  // not a recoverable client-side error. On the `awaiting_approval` pause the
  // BE sends no attribution, so it stays undefined there.
  return {
    status,
    messageId,
    ...(isRecord(attribution)
      ? { attribution: attribution as unknown as ModelAttribution }
      : {}),
  };
}

// `status` payload narrows to `{ label, state }`. `state` is constrained to
// "active" | "done"; anything else (or a missing field) yields null and the
// frame is skipped.
function parseStatus(value: unknown): SearchStatus | null {
  if (!isRecord(value)) return null;
  const label = readStringField(value, "label");
  const state = readStringField(value, "state");
  if (label === null) return null;
  if (state !== "active" && state !== "done") return null;
  return { label, state };
}

function readProvenance(value: unknown): SourceItem["provenance"] | undefined {
  return value === "web" || value === "knowledge" || value === "connector"
    ? value
    : undefined;
}

// `sources` payload narrows to `{ items: SourceItem[], requested?: boolean }`.
// Each item must carry a numeric id plus string title + url; `snippet` /
// `domain` / `provenance` are optional. Malformed items are dropped rather than
// failing the whole stream — sources are a non-essential enrichment, not
// load-bearing answer content. `requested` flags whether web search was
// effective so an empty list can still surface the ungrounded marker.
interface ParsedSources {
  items: SourceItem[];
  requested: boolean;
}

function parseSources(value: unknown): ParsedSources | null {
  if (!isRecord(value)) return null;
  const items = value.items;
  if (!Array.isArray(items)) return null;
  const out: SourceItem[] = [];
  for (const raw of items) {
    if (!isRecord(raw)) continue;
    const id = raw.id;
    const title = readStringField(raw, "title");
    const url = readStringField(raw, "url");
    if (typeof id !== "number" || title === null || url === null) continue;
    const snippet = readStringField(raw, "snippet");
    const domain = readStringField(raw, "domain");
    const provenance = readProvenance(raw.provenance);
    out.push({
      id,
      title,
      url,
      ...(snippet !== null ? { snippet } : {}),
      ...(domain !== null ? { domain } : {}),
      ...(provenance ? { provenance } : {}),
    });
  }
  return { items: out, requested: value.requested === true };
}

function readToolStatus(value: unknown): ToolTranscriptPart["status"] | undefined {
  if (
    value === "pending" ||
    value === "awaiting_approval" ||
    value === "running" ||
    value === "succeeded" ||
    value === "failed" ||
    value === "cancelled"
  ) {
    return value;
  }
  return undefined;
}

function readApprovalState(
  value: unknown,
): ToolTranscriptPart["approvalState"] | undefined {
  if (
    value === "not_required" ||
    value === "pending" ||
    value === "approved" ||
    value === "rejected"
  ) {
    return value;
  }
  return undefined;
}

function asJsonRecord(value: unknown): Record<string, JsonValue> | undefined {
  return isRecord(value) ? (value as Record<string, JsonValue>) : undefined;
}

function parseToolCall(value: unknown): ToolTranscriptPart | null {
  if (!isRecord(value)) return null;
  const id = readStringField(value, "id");
  const name = readStringField(value, "name");
  if (id === null || name === null) return null;
  const label = readStringField(value, "label");
  return {
    type: "tool_call",
    id,
    name,
    ...(label !== null ? { label } : {}),
    ...(readToolStatus(value.status) ? { status: readToolStatus(value.status) } : {}),
    ...(readApprovalState(value.approvalState)
      ? { approvalState: readApprovalState(value.approvalState) }
      : {}),
    ...(asJsonRecord(value.input) ? { input: asJsonRecord(value.input) } : {}),
  };
}

function parseToolResult(value: unknown): ToolTranscriptPart | null {
  if (!isRecord(value)) return null;
  const toolCallId = readStringField(value, "toolCallId");
  const name = readStringField(value, "name");
  if (toolCallId === null || name === null) return null;
  const label = readStringField(value, "label");
  const summary = readStringField(value, "summary");
  const error = readStringField(value, "error");
  return {
    type: "tool_result",
    toolCallId,
    name,
    ...(label !== null ? { label } : {}),
    ...(readToolStatus(value.status) ? { status: readToolStatus(value.status) } : {}),
    ...(readApprovalState(value.approvalState)
      ? { approvalState: readApprovalState(value.approvalState) }
      : {}),
    ...(summary !== null ? { summary } : {}),
    ...(asJsonRecord(value.output) ? { output: asJsonRecord(value.output) } : {}),
    ...(error !== null ? { error } : {}),
  };
}

// --- Hook ------------------------------------------------------------------

export interface UseApiStreamResult {
  state: ApiStreamState;
  start: (args: StartArgs) => void;
  stop: () => void;
  reset: () => void;
}

// Implementation notes:
// - State updates: per-frame `setState`. SSE bursts are typically <100/s in
//   practice and React 18+ batches inside fetch microtasks anyway. Switch to
//   an rAF buffered flush (like `useMockStream`) only if INP regressions show.
// - Refs hold the authoritative accumulators so terminal handlers never read
//   stale React state — mirrors the mock's pattern.
// - `onTerminal` is captured in a ref so callers can pass an inline arrow
//   without rebinding `start`/`stop`/`reset` on every render.
export function useApiStream(
  onTerminal?: (result: TerminalResult) => void,
  // Called when a send is rejected with HTTP 409 / code "STREAM_IN_PROGRESS"
  // (a second send while a response is still generating). The hook does NOT
  // emit an error terminal in that case — so no errored bubble replaces the
  // live answer — and hands the rejection to the caller to surface a toast and
  // roll back its optimistic bubble. (P0-2)
  onStreamInProgress?: () => void,
): UseApiStreamResult {
  const [state, setState] = useState<ApiStreamState>(INITIAL);

  const controllerRef = useRef<AbortController | null>(null);
  const reasoningRef = useRef("");
  const answerRef = useRef("");
  const durationRef = useRef(0);
  // Web-search accumulators — mirror the reasoning/answer refs so terminal
  // handlers read the authoritative latest value, never stale React state.
  const searchStatusRef = useRef<SearchStatus | null>(null);
  const sourcesRef = useRef<SourceItem[]>([]);
  const sourcesRequestedRef = useRef(false);
  const toolPartsRef = useRef<ToolTranscriptPart[]>([]);
  const reasoningStartedAtRef = useRef<number | null>(null);
  // `submitted` lands the user message id; we keep it for the terminal so the
  // FE can replace its local `local-…` user id with the server uuid.
  const serverUserIdRef = useRef<string | undefined>(undefined);
  const streamIdRef = useRef<string | undefined>(undefined);
  const conversationIdRef = useRef<string | undefined>(undefined);
  const reconnectAttemptedRef = useRef(false);
  // True once `onTerminal` has fired for the current turn. The terminal can
  // fire from three places (server `terminal`, server `error`, client
  // `stop()` / abort) — we never want to deliver twice.
  const terminalEmittedRef = useRef(false);

  const onTerminalRef = useRef(onTerminal);
  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

  const onStreamInProgressRef = useRef(onStreamInProgress);
  useEffect(() => {
    onStreamInProgressRef.current = onStreamInProgress;
  }, [onStreamInProgress]);

  const computeReasoningDuration = useCallback((): number => {
    const startedAt = reasoningStartedAtRef.current;
    if (startedAt === null) return durationRef.current;
    // Mirror the mock's flooring: at least 1s once reasoning started, rounded
    // to whole seconds. Wall-clock from first reasoning_delta.
    return Math.max(1, Math.round((Date.now() - startedAt) / 1000));
  }, []);

  const freezeReasoningDuration = useCallback((): void => {
    if (reasoningStartedAtRef.current !== null) {
      durationRef.current = computeReasoningDuration();
      reasoningStartedAtRef.current = null;
    }
  }, [computeReasoningDuration]);

  const emitTerminal = useCallback(
    (
      status: "done" | "stopped" | "error" | "awaiting_approval",
      extras: {
        serverAssistantMessageId?: string;
        attribution?: ModelAttribution;
        error?: ApiError;
      } = {},
    ): void => {
      if (terminalEmittedRef.current) return;
      terminalEmittedRef.current = true;
      onTerminalRef.current?.({
        status,
        reasoning: reasoningRef.current,
        reasoningDurationSec: durationRef.current,
        answer: answerRef.current,
        searchStatus: searchStatusRef.current,
        sources: sourcesRef.current,
        sourcesRequested: sourcesRequestedRef.current,
        toolParts: toolPartsRef.current,
        serverUserMessageId: serverUserIdRef.current,
        ...extras,
      });
    },
    [],
  );

  const resetAccumulators = useCallback((): void => {
    reasoningRef.current = "";
    answerRef.current = "";
    durationRef.current = 0;
    reasoningStartedAtRef.current = null;
    searchStatusRef.current = null;
    sourcesRef.current = [];
    sourcesRequestedRef.current = false;
    toolPartsRef.current = [];
    serverUserIdRef.current = undefined;
    streamIdRef.current = undefined;
    terminalEmittedRef.current = false;
  }, []);

  const resetForReplay = useCallback((): void => {
    const streamId = streamIdRef.current;
    reasoningRef.current = "";
    answerRef.current = "";
    durationRef.current = 0;
    reasoningStartedAtRef.current = null;
    searchStatusRef.current = null;
    sourcesRef.current = [];
    sourcesRequestedRef.current = false;
    toolPartsRef.current = [];
    serverUserIdRef.current = undefined;
    streamIdRef.current = streamId;
    setState({ ...INITIAL, status: "submitted" });
  }, []);

  // Handle a single parsed SSE frame. Returns true if this frame ends the
  // stream (consumer should break the read loop afterwards).
  const handleFrame = useCallback(
    (frame: ParsedFrame): boolean => {
      let payload: unknown;
      try {
        // `reasoning_done` carries `{}` — still valid JSON.
        payload = JSON.parse(frame.data);
      } catch (cause) {
        console.warn(
          `[stream-client] Failed to parse data for event ${frame.event}`,
          cause,
        );
        const err = new ApiError(
          {
            code: "PROTOCOL",
            severity: "error",
            title: "Bad stream payload",
            body: `The server sent an unreadable ${frame.event} frame.`,
          },
          0,
        );
        setState((s) => ({ ...s, status: "error" }));
        emitTerminal("error", { error: err });
        return true;
      }

      switch (frame.event) {
        case "submitted": {
          if (isRecord(payload)) {
            const id = readStringField(payload, "messageId");
            if (id) serverUserIdRef.current = id;
            const streamId = readStringField(payload, "streamId");
            if (streamId) streamIdRef.current = streamId;
          }
          setState((s) => ({ ...s, status: "streaming" }));
          return false;
        }
        case "reasoning_delta": {
          if (!isRecord(payload)) return false;
          const text = readStringField(payload, "text");
          if (text === null) return false;
          if (reasoningStartedAtRef.current === null) {
            reasoningStartedAtRef.current = Date.now();
          }
          reasoningRef.current += text;
          const next = reasoningRef.current;
          setState((s) => ({
            ...s,
            reasoning: next,
            reasoningStreaming: true,
            reasoningDurationSec: computeReasoningDuration(),
          }));
          return false;
        }
        case "reasoning_done": {
          freezeReasoningDuration();
          const dur = durationRef.current;
          setState((s) => ({
            ...s,
            reasoningStreaming: false,
            reasoningDurationSec: dur,
          }));
          return false;
        }
        case "answer_delta": {
          if (!isRecord(payload)) return false;
          const text = readStringField(payload, "text");
          if (text === null) return false;
          // Defensive: server guarantees `reasoning_done` precedes the first
          // `answer_delta` if any reasoning fired, but freeze the clock here
          // anyway in case the server elided the sentinel for any reason.
          if (reasoningStartedAtRef.current !== null) {
            freezeReasoningDuration();
          }
          answerRef.current += text;
          const next = answerRef.current;
          setState((s) => ({
            ...s,
            answer: next,
            reasoningStreaming: false,
          }));
          return false;
        }
        case "terminal": {
          const parsed = parseTerminal(payload);
          freezeReasoningDuration();
          if (!parsed) {
            const err = new ApiError(
              {
                code: "PROTOCOL",
                severity: "error",
                title: "Bad terminal payload",
                body: "The server sent a terminal frame with an unexpected shape.",
              },
              0,
            );
            setState((s) => ({ ...s, status: "error" }));
            emitTerminal("error", { error: err });
            return true;
          }
          // Surface the frame's status (default "done"). On the HITL pause the
          // BE sends `status: "awaiting_approval"` and no attribution — the
          // bubble settles into the approval card and the cost lands on the
          // resumed turn.
          setState((s) => ({
            ...s,
            status: parsed.status,
            reasoningStreaming: false,
            reasoningDurationSec: durationRef.current,
          }));
          emitTerminal(parsed.status, {
            serverAssistantMessageId: parsed.messageId,
            ...(parsed.attribution ? { attribution: parsed.attribution } : {}),
          });
          return true;
        }
        case "error": {
          freezeReasoningDuration();
          const envelope = isErrorEnvelope(payload)
            ? payload
            : {
                code: "PROTOCOL",
                severity: "error" as const,
                title: "Stream error",
                body: "The server signalled an error with an unexpected shape.",
              };
          const err = new ApiError(envelope, 0);
          setState((s) => ({
            ...s,
            status: "error",
            reasoningStreaming: false,
            reasoningDurationSec: durationRef.current,
          }));
          emitTerminal("error", { error: err });
          return true;
        }
        case "status": {
          // Web-search status line ("Searching the web…" → "Searched the web").
          // Last write wins; the BE flips `state` to "done" when search ends.
          const parsed = parseStatus(payload);
          if (!parsed) return false;
          searchStatusRef.current = parsed;
          setState((s) => ({ ...s, searchStatus: parsed }));
          return false;
        }
        case "sources": {
          // Web-search source cards. The BE emits the full set in one frame;
          // we replace (not append) so a re-emit can't duplicate cards.
          // `requested` is sticky: once the turn is marked grounded-or-not it
          // stays so even if a later frame's items differ.
          const parsed = parseSources(payload);
          if (parsed === null) return false;
          sourcesRef.current = parsed.items;
          if (parsed.requested) sourcesRequestedRef.current = true;
          const requested = sourcesRequestedRef.current;
          setState((s) => ({
            ...s,
            sources: parsed.items,
            sourcesRequested: requested,
          }));
          return false;
        }
        case "tool_call": {
          const parsed = parseToolCall(payload);
          if (parsed === null) return false;
          toolPartsRef.current = [...toolPartsRef.current, parsed];
          setState((s) => ({ ...s, toolParts: toolPartsRef.current }));
          return false;
        }
        case "tool_result": {
          const parsed = parseToolResult(payload);
          if (parsed === null) return false;
          toolPartsRef.current = [...toolPartsRef.current, parsed];
          setState((s) => ({ ...s, toolParts: toolPartsRef.current }));
          return false;
        }
        default: {
          console.warn(`[stream-client] Unknown SSE event: ${frame.event}`);
          return false;
        }
      }
    },
    [computeReasoningDuration, emitTerminal, freezeReasoningDuration],
  );

  const consumeStream = useCallback(
    async (response: Response): Promise<void> => {
      const body = response.body;
      if (!body) {
        const err = new ApiError(
          {
            code: "PROTOCOL",
            severity: "error",
            title: "Empty response",
            body: "The server returned no response body for the stream.",
          },
          response.status,
        );
        setState((s) => ({ ...s, status: "error" }));
        emitTerminal("error", { error: err });
        return;
      }
      const reader = body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      // SSE frames are separated by a blank line. sse-starlette emits CRLF
      // (`\r\n`) line endings; the WHATWG spec also allows `\n` and `\r`. A
      // naive per-chunk `\r\n` → `\n` replace breaks when a `\r\n` straddles
      // two read chunks (chunk1 ends `\r`, chunk2 starts `\n`): the lone `\r`
      // stays in the buffer and `indexOf("\n\n")` will not find the boundary
      // because `...\r\n\n...` doesn't contain `\n\n` aligned right. Match the
      // separator at the BUFFER level with a CR-tolerant regex so spanning
      // chunks are correct by construction. parseFrame strips any trailing
      // `\r` per line internally, so no further normalization is needed.
      const FRAME_SEP = /\r?\n\r?\n/;
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let match: RegExpExecArray | null;
          while ((match = FRAME_SEP.exec(buffer)) !== null) {
            const raw = buffer.slice(0, match.index);
            buffer = buffer.slice(match.index + match[0].length);
            const frame = parseFrame(raw);
            if (frame) {
              const ended = handleFrame(frame);
              if (ended) {
                // Drain the reader so the connection closes cleanly, but stop
                // dispatching further frames — the terminal has already been
                // delivered to `onTerminal`.
                try {
                  await reader.cancel();
                } catch {
                  // Ignore cancel errors; we're done.
                }
                return;
              }
            }
          }
        }
        // Stream ended without a terminal frame. Treat as a protocol error.
        if (!terminalEmittedRef.current) {
          throw new ApiError(
            {
              code: "PROTOCOL",
              severity: "error",
              title: "Stream ended unexpectedly",
              body: "The server closed the stream without a terminal frame.",
            },
            response.status,
          );
        }
      } finally {
        try {
          reader.releaseLock();
        } catch {
          // Reader already released (e.g. after `cancel()`); ignore.
        }
      }
    },
    [emitTerminal, handleFrame],
  );

  const runStream = useCallback(
    async (args: StartArgs, controller: AbortController): Promise<void> => {
      let url: string;
      try {
        url = `${getApiBase()}/api/conversations/${encodeURIComponent(
          args.conversationId,
        )}/messages`;
      } catch (cause) {
        const err =
          cause instanceof ApiError
            ? cause
            : new ApiError(
                {
                  code: "CONFIG",
                  severity: "error",
                  title: "Stream setup failed",
                  body: cause instanceof Error ? cause.message : "Unknown error.",
                },
                0,
              );
        setState((s) => ({ ...s, status: "error" }));
        emitTerminal("error", { error: err });
        return;
      }

      // Build the request body. Only include optional fields when set so we
      // don't pin Pydantic defaults to `null` on the wire.
      const body: Record<string, unknown> = {
        clientMessageId: args.clientMessageId,
        tierId: args.tierId,
        text: args.text,
      };
      if (args.providerId !== undefined) body.providerId = args.providerId;
      if (args.isTemporary !== undefined) body.isTemporary = args.isTemporary;
      if (args.regenerate !== undefined) body.regenerate = args.regenerate;
      // Send `continueTurn` only when true (BE treats absence as false), so the
      // non-continue path is byte-identical to today's wire shape.
      if (args.continueTurn) body.continueTurn = true;
      if (args.editMessageId !== undefined)
        body.editMessageId = args.editMessageId;
      // HITL resume: send the approve/deny decision only when set (mirrors how
      // `continueTurn`/`webSearch` are conditionally added), so non-HITL turns
      // are byte-identical to today's wire shape. Mutually exclusive with
      // regenerate/continue/edit by construction (the caller sets only one).
      if (args.toolApproval) body.toolApproval = args.toolApproval;
      // Send `webSearch` only when on — the BE treats absence as false, so the
      // off path is a no-op vs today's wire shape.
      if (args.webSearch) body.webSearch = true;
      // Send `reasoningEffort` only when the user picked a concrete (non-auto)
      // value — the BE treats absence as "auto", so the default path is
      // byte-identical to today (mirrors `webSearch` above).
      if (args.reasoningEffort && args.reasoningEffort !== "auto") {
        body.reasoningEffort = args.reasoningEffort;
      }
      // Send `responseFormat` only when JSON mode is on — the BE treats absence
      // as off, so the non-JSON path is byte-identical to today's wire shape.
      if (args.responseFormat) body.responseFormat = args.responseFormat;
      if (args.attachments && args.attachments.length > 0) {
        body.attachments = args.attachments;
      }

      let response: Response;
      try {
        response = await fetch(url, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
      } catch (cause) {
        // Aborted by `stop()` / `reset()` / unmount — that path emits its own
        // terminal (status="stopped"), so don't double-fire here.
        if (controller.signal.aborted) return;
        const err = new ApiError(
          {
            code: "NETWORK",
            severity: "error",
            title: "Network error",
            body:
              cause instanceof Error
                ? cause.message
                : "The network request failed before any response was received.",
          },
          0,
        );
        setState((s) => ({ ...s, status: "error" }));
        emitTerminal("error", { error: err });
        return;
      }

      if (!response.ok) {
        // The server returns the standard `{ error: envelope }` JSON for
        // pre-stream failures (e.g. 400 INVALID_TIER, 409 DUPLICATE_IN_FLIGHT).
        let envelope: ApiErrorEnvelope | null = null;
        try {
          const parsed: unknown = await response.json();
          if (
            isRecord(parsed) &&
            isRecord(parsed.error) &&
            isErrorEnvelope(parsed.error)
          ) {
            envelope = parsed.error;
          } else if (isErrorEnvelope(parsed)) {
            envelope = parsed;
          }
        } catch {
          // Body wasn't JSON; fall through to the synthesized envelope.
        }
        // Defense-in-depth for a second send landing while a response is still
        // generating: the BE rejects it with 409 STREAM_IN_PROGRESS. Do NOT
        // turn that into an error terminal — an errored bubble would replace
        // the legitimate in-flight answer. Suppress the terminal (so the live
        // stream's commit path is untouched), drop our just-armed state back to
        // idle, and let the caller toast + roll back its optimistic bubble. The
        // P0-1 busy gate makes this near-unreachable from normal flow. (P0-2)
        if (
          response.status === 409 ||
          envelope?.code === "STREAM_IN_PROGRESS"
        ) {
          terminalEmittedRef.current = true;
          setState((s) => ({ ...s, status: "idle" }));
          onStreamInProgressRef.current?.();
          return;
        }
        const err = new ApiError(
          envelope ?? {
            code: "UNKNOWN",
            severity: "error",
            title: "Request failed",
            body: `HTTP ${response.status} starting the stream.`,
          },
          response.status,
        );
        setState((s) => ({ ...s, status: "error" }));
        emitTerminal("error", { error: err });
        return;
      }

      try {
        await consumeStream(response);
      } catch (cause) {
        if (controller.signal.aborted) return;
        const streamId = streamIdRef.current;
        if (
          streamId &&
          !reconnectAttemptedRef.current &&
          !terminalEmittedRef.current
        ) {
          reconnectAttemptedRef.current = true;
          let reconnectUrl: string;
          try {
            reconnectUrl = `${getApiBase()}/api/conversations/${encodeURIComponent(
              args.conversationId,
            )}/stream/${encodeURIComponent(streamId)}`;
          } catch {
            reconnectUrl = "";
          }
          if (reconnectUrl) {
            try {
              const replay = await fetch(reconnectUrl, {
                method: "GET",
                credentials: "include",
                signal: controller.signal,
              });
              if (replay.ok) {
                resetForReplay();
                await consumeStream(replay);
                return;
              }
              // Non-ok reconnect status. The server returns the standard
              // `{ error: envelope }` JSON for these — most notably 410
              // STREAM_REPLAY_TRUNCATED (the replay buffer expired past TTL).
              // Surface the server's typed error (title/body + Retry via
              // ErrorFooter) instead of falling through to the generic network
              // error below. Mirror the pre-stream non-ok parsing above.
              if (!controller.signal.aborted) {
                let envelope: ApiErrorEnvelope | null = null;
                try {
                  const parsed: unknown = await replay.json();
                  if (
                    isRecord(parsed) &&
                    isRecord(parsed.error) &&
                    isErrorEnvelope(parsed.error)
                  ) {
                    envelope = parsed.error;
                  } else if (isErrorEnvelope(parsed)) {
                    envelope = parsed;
                  }
                } catch {
                  // Body wasn't a parseable envelope; fall through to the
                  // generic stream-read error below.
                }
                if (envelope && !terminalEmittedRef.current) {
                  const replayErr = new ApiError(envelope, replay.status);
                  setState((s) => ({ ...s, status: "error" }));
                  emitTerminal("error", { error: replayErr });
                  return;
                }
              }
            } catch {
              if (controller.signal.aborted) return;
            }
          }
        }
        const err =
          cause instanceof ApiError
            ? cause
            : new ApiError(
                {
                  code: "NETWORK",
                  severity: "error",
                  title: "Stream read failed",
                  body:
                    cause instanceof Error
                      ? cause.message
                      : "The connection dropped while reading the stream.",
                },
                0,
              );
        if (!terminalEmittedRef.current) {
          setState((s) => ({ ...s, status: "error" }));
          emitTerminal("error", { error: err });
        }
      }
    },
    [consumeStream, emitTerminal, resetForReplay],
  );

  const start = useCallback(
    (args: StartArgs): void => {
      // If a stream is already in flight, abort it silently. The previous
      // terminal (if any) has already fired; if not, the abort will not
      // synthesize a stopped event because we reset `terminalEmittedRef`
      // below for the fresh turn.
      controllerRef.current?.abort();
      controllerRef.current = null;

      resetAccumulators();
      reconnectAttemptedRef.current = false;
      conversationIdRef.current = args.conversationId;
      setState({ ...INITIAL, status: "submitted" });

      const controller = new AbortController();
      controllerRef.current = controller;

      void runStream(args, controller);
    },
    [resetAccumulators, runStream],
  );

  const stop = useCallback((): void => {
    const controller = controllerRef.current;
    if (!controller) return;
    controllerRef.current = null;
    const conversationId = conversationIdRef.current;
    const hadStreamId = Boolean(streamIdRef.current);
    if (conversationId) {
      void postConversationStop(conversationId).catch(() => {
        // Best-effort: local abort below still gives immediate UI feedback.
      });
    }
    // Aborting the fetch tears down the SSE reader; that read loop sees
    // `signal.aborted` and exits without emitting. We synthesize the local
    // `stopped` terminal so the caller can commit the partial message — the
    // server persists `status="stopped"` server-side via its own disconnect
    // detector (no frame arrives on this socket).
    controller.abort();
    freezeReasoningDuration();
    const reasoning = reasoningRef.current;
    const answer = answerRef.current;
    const dur = durationRef.current;
    setState((s) => ({
      ...s,
      reasoning,
      answer,
      reasoningDurationSec: dur,
      status: "stopped",
      reasoningStreaming: false,
    }));
    emitTerminal("stopped");
    if (conversationId && !hadStreamId) {
      window.setTimeout(() => {
        if (
          controllerRef.current !== null ||
          conversationIdRef.current !== conversationId
        ) {
          return;
        }
        void postConversationStop(conversationId).catch(() => {
          // Best-effort retry for Stop clicks before the submitted frame arrives.
        });
      }, 250);
    }
  }, [emitTerminal, freezeReasoningDuration]);

  const reset = useCallback((): void => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    conversationIdRef.current = undefined;
    // `reset()` blows away the turn unconditionally — no terminal is fired,
    // and any in-flight callback that would have fired one is suppressed by
    // the `terminalEmittedRef` flip below.
    terminalEmittedRef.current = true;
    resetAccumulators();
    // Then re-clear so the next `start()` begins with a clean slate.
    terminalEmittedRef.current = false;
    setState(INITIAL);
  }, [resetAccumulators]);

  // Belt-and-braces cleanup: if the component unmounts mid-stream, abort the
  // underlying fetch so the reader doesn't keep the socket open. We do NOT
  // fire `onTerminal` here — the consumer is gone.
  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  return { state, start, stop, reset };
}
