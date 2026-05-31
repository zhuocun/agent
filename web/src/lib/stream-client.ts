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
//   event: submitted          data: { messageId }
//   event: reasoning_delta    data: { text }
//   event: reasoning_done     data: {}
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
// EventSource cannot send credentials cross-origin reliably and has no header
// configuration (per AGENTS.md / plan §"Architecture overview"). sse-starlette
// emits keep-alive comment lines (`:`-prefixed) every ~15s; the parser drops
// them. `data:` is always single-line JSON (Pydantic `model_dump_json`), so we
// don't bother stitching multi-line `data:` values.

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, type ApiErrorEnvelope } from "@/lib/apiClient";
import type {
  ModelAttribution,
  ModelTierId,
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
}

export interface TerminalResult {
  status: "done" | "stopped" | "error";
  reasoning: string;
  reasoningDurationSec: number;
  answer: string;
  // Final web-search status line (if any) so finalized messages keep the
  // "Searched the web" part. Null when web search was off.
  searchStatus: SearchStatus | null;
  // Final web-search sources (if any) so finalized messages keep their cards.
  sources: SourceItem[];
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
  text: string;
  isTemporary?: boolean;
  regenerate?: boolean;
  editMessageId?: string;
  // Toggled on in the composer; sent only when true (the BE treats absence as
  // false). Gated upstream on the selected tier's `supportsWebSearch`.
  webSearch?: boolean;
}

const INITIAL: ApiStreamState = {
  status: "idle",
  reasoning: "",
  reasoningStreaming: false,
  reasoningDurationSec: 0,
  answer: "",
  searchStatus: null,
  sources: [],
};

// --- Base URL --------------------------------------------------------------

// Local helper: apiClient.ts does not export its `resolveUrl` so we duplicate
// the same `process.env.NEXT_PUBLIC_API_BASE_URL` read here. The value is
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
          "NEXT_PUBLIC_API_BASE_URL is not set. Define it in web/.env.local " +
          "(or your deploy env) before sending messages.",
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

// `terminal` payload narrows to `{ status: "done", messageId, attribution }`.
interface TerminalPayload {
  messageId: string;
  attribution: ModelAttribution;
}

function parseTerminal(value: unknown): TerminalPayload | null {
  if (!isRecord(value)) return null;
  const messageId = readStringField(value, "messageId");
  const attribution = value.attribution;
  if (!messageId || !isRecord(attribution)) return null;
  // We don't deep-validate ModelAttribution here — the BE owns its wire
  // shape via Pydantic, and the FE renders it through `AttributionRow`
  // which tolerates partial shapes. A bad attribution is a contract bug,
  // not a recoverable client-side error.
  return { messageId, attribution: attribution as unknown as ModelAttribution };
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

// `sources` payload narrows to `{ items: SourceItem[] }`. Each item must carry
// a numeric id plus string title + url; `snippet` / `domain` are optional.
// Malformed items are dropped rather than failing the whole stream — sources
// are a non-essential enrichment, not load-bearing answer content.
function parseSources(value: unknown): SourceItem[] | null {
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
    out.push({
      id,
      title,
      url,
      ...(snippet !== null ? { snippet } : {}),
      ...(domain !== null ? { domain } : {}),
    });
  }
  return out;
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
  const reasoningStartedAtRef = useRef<number | null>(null);
  // `submitted` lands the user message id; we keep it for the terminal so the
  // FE can replace its local `local-…` user id with the server uuid.
  const serverUserIdRef = useRef<string | undefined>(undefined);
  // True once `onTerminal` has fired for the current turn. The terminal can
  // fire from three places (server `terminal`, server `error`, client
  // `stop()` / abort) — we never want to deliver twice.
  const terminalEmittedRef = useRef(false);

  const onTerminalRef = useRef(onTerminal);
  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

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
      status: "done" | "stopped" | "error",
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
    serverUserIdRef.current = undefined;
    terminalEmittedRef.current = false;
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
          setState((s) => ({
            ...s,
            status: "done",
            reasoningStreaming: false,
            reasoningDurationSec: durationRef.current,
          }));
          emitTerminal("done", {
            serverAssistantMessageId: parsed.messageId,
            attribution: parsed.attribution,
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
          const parsed = parseSources(payload);
          if (parsed === null) return false;
          sourcesRef.current = parsed;
          setState((s) => ({ ...s, sources: parsed }));
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
          const err = new ApiError(
            {
              code: "PROTOCOL",
              severity: "error",
              title: "Stream ended unexpectedly",
              body: "The server closed the stream without a terminal frame.",
            },
            response.status,
          );
          setState((s) => ({ ...s, status: "error" }));
          emitTerminal("error", { error: err });
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
      if (args.isTemporary !== undefined) body.isTemporary = args.isTemporary;
      if (args.regenerate !== undefined) body.regenerate = args.regenerate;
      if (args.editMessageId !== undefined)
        body.editMessageId = args.editMessageId;
      // Send `webSearch` only when on — the BE treats absence as false, so the
      // off path is a no-op vs today's wire shape.
      if (args.webSearch) body.webSearch = true;

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
        const err = new ApiError(
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
    [consumeStream, emitTerminal],
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
  }, [emitTerminal, freezeReasoningDuration]);

  const reset = useCallback((): void => {
    controllerRef.current?.abort();
    controllerRef.current = null;
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
