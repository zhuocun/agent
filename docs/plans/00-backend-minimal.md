# Backend Minimal Plan

A development plan for the smallest backend that lets the existing Next.js frontend at `web/` run against real persistence and a real model provider with **zero UI changes**. Anchored to the FE wire shapes in `web/src/lib/types.ts` and the behavior already implemented in `web/src/components/chat/chat-thread.tsx`. PRDs are referenced for direction, but the cuts here are aggressive: anything the FE does not yet render or call is deferred.

## Goal & non-goals

In scope (justified by an existing FE surface):

- Bootstrap payload that replaces every `MOCK_*` constant in `web/src/lib/mock-data.ts` with one network call.
- Conversation CRUD: list, read, create, rename, pin, delete (every mutation the sidebar exposes today).
- A single streaming endpoint that produces the typed parts the FE renders: `reasoning`, `text`, and `status`. Stop = client closes the EventSource and the partial parts persist (PRD 01 §4.1).
- Terminal `ModelAttribution` emitted on the stream's last frame, so `freshAttribution()` in `chat-thread.tsx` can be deleted on the FE side without UI changes.
- Message feedback (`up`/`down`/`null`), user preferences (`UserPreferences`), and BYOK key write/delete — every settings-dialog mutation has a backend.
- Anonymous-first session via Better Auth's anonymous plugin (PRD 04 §5.5) so persistence is per-user from day one, with no FE auth surface today.
- Per-turn requested tier captured server-side from the request body (FE already sends it via `tierAtSendRef`).

Explicitly out (cut from PRDs; no FE surface today):

- Attachments and file uploads (PRD 01 §5.3, F21).
- Tools, web search, memory, citations, interactive blocks (PRD 02; PRD 01 §4.4 message part union beyond text/reasoning/status).
- Resumable replay and a server-side stop endpoint (PRD 04 §5.1 P1).
- Conversation export, share links, audit-log enforcement (PRD 01 §4.8; PRD 04 §5.8 P1).
- Sync engine / multi-device live updates (PRD 03).
- Payments, plan management, platform-vs-BYOK budget split (PRD 05; PRD 07 §6.3).
- Rate limiting, cost budget enforcement, abuse protection (PRD 04 §5.6, PRD 08).
- Observability stack: tracing, metrics, error reporting, sampling pipeline (PRD 04 §5.10) — replaced by structured `console` JSON.
- Substitution reason codes the FE does not render (`auto_route`, `budget_cap`, `policy_route` from PRD 07).
- Server-curated prompt suggestions (`MOCK_SUGGESTIONS` can remain client-static; ship a server endpoint only when product wants curation).

Known FE follow-ups (callouts, not work for this plan):

- BYOK UI in `sidebar.tsx`/`settings-dialog.tsx` reads `byokEnabled`/`byokMaskedKey` unconditionally; once anonymous sessions ship, the FE needs a tiny conditional to hide BYOK editing for `isAnonymous=true`. We will return `byokEnabled=false` for anonymous users so the current UI degrades correctly.
- `reasoningDurationSec` is FE-computed via wall clock today. The BE will not emit it. If we later emit one, the FE will need to prefer the server value.
- `freshAttribution()` is a temporary FE stub; the BE's `terminal` event replaces it. The FE change is one-line.

## Architecture overview

```
[ Next.js 16 app at web/ ]
        |
        +-- web/src/app/page.tsx --> <ChatThread />     (existing FE, untouched)
        |
        +-- web/src/app/api/**       (NEW: Route Handlers, Node runtime)
        |     |
        |     +-- bootstrap, conversations, messages (SSE), preferences, account, feedback
        |     +-- auth/[...all]   (Better Auth handler)
        |
        +-- web/src/server/         (NEW: server-only modules)
              +-- db/        Drizzle client + repositories
              +-- auth/      Better Auth config + middleware helpers
              +-- providers/ AI SDK v6 model factory + tier->model map + pricing
              +-- streaming/ SSE encoder + event types + onFinish hook
              +-- routes-shared/ zod schemas, error envelope, request context

[ Neon Postgres (or local pg for dev) ]
        - drizzle migrations
        - tables: user, session, conversation, message, vote, api_key, usage_rollup
```

Stack picks (one-line justifications):

- **BE lives inside the existing Next.js app** under `web/src/app/api/**` and `web/src/server/**`. No separate service. Cheaper deploy, shared types, and the FE is already a Next app — the docs warning in `web/AGENTS.md` about a non-standard Next applies to convention details, not to the existence of Route Handlers.
- **Node runtime for streaming routes**. Edge runtime is incompatible with the Postgres driver and adds friction for AI SDK provider SDKs; for a minimal backend the Node runtime is the boring right choice.
- **Postgres + Drizzle**. Neon for hosted (branch-per-PR is useful), or local Postgres for dev. Drizzle gives us TS-first schemas and migrations without an ORM tax.
- **Better Auth + anonymous plugin** (PRD 04 §5.5). Avoids a re-platform when real auth UI lands. The minimal BE will recommend this over single-user dev mode.
- **AI SDK v6 (`streamText`)** for provider abstraction and SSE plumbing, even at MVP. Worth it because (a) typed parts/onFinish carry the usage metadata we need for `CostBreakdown`, (b) provider swap is one-line, and (c) we get cancellation via `AbortSignal` for free.
- **Vercel AI Gateway** as the default provider front (PRD 04). One config swap to direct provider keys if needed.
- **No Upstash/Redis/QStash at MVP**. No rate limiting, no resumable streams, no queues. The conversation title autogen runs inline in the same request (or fire-and-forget on the same Node process — see Streaming).
- **No observability stack**. Structured JSON logs to stdout, keyed by `requestId` and `userId`. Wire OpenTelemetry later (PRD 04 §5.10).

Wire-format decision: **camelCase end-to-end**. The FE types are camelCase; matching that on the wire saves us an adapter layer in both directions. Inside Postgres we use snake_case columns; Drizzle maps to camelCase TS fields and JSON-encoded `jsonb` blobs (`parts`, `attribution`) are stored already-camelCase to round-trip cheaply.

## Wire contract

All endpoints are JSON over HTTPS unless noted. Mutations are scoped to the caller's user (either a Better Auth signed-in user or an anonymous session). Responses use camelCase per the FE types. Error responses use the envelope from `## Errors & limits`.

### `GET /api/bootstrap`

Replaces every `MOCK_*` import in `chat-thread.tsx` in a single round-trip. Returns:

```ts
{
  account: AccountInfo;
  preferences: UserPreferences;
  usage: UsageBudget;
  modelTiers: ModelTier[];                    // from the BE model registry
  suggestions: PromptSuggestion[];            // static set, server-owned
  conversations: ConversationSummary[];       // sidebar list, full list (sort: pinned desc, updatedAt desc)
}
```

Behavior: idempotent, must work for anonymous users (returns synthesized `AccountInfo` with empty email, `planLabel="Free"`, `byokEnabled=false`). `usage.isByok` mirrors whether any `api_key` row exists for the user. No pagination for `conversations` — the FE filters client-side. 200 on success.

### `GET /api/conversations/:id`

Returns a full `Conversation` (header info + ordered `messages[]`). Idempotent. 404 if not owned by the caller (do not leak existence). Idempotent.

### `POST /api/conversations`

Body: `{ selectedTierId: ModelTierId, isTemporary: boolean }`. Returns a new `Conversation` with empty `messages: []` and an autogenerated title (`"New chat"` until the first turn names it). For `isTemporary: true`, return a synthetic id (UUID, not persisted) and rely on the client to send it back in subsequent calls; the BE will refuse to load it later (404), and the `messages` POST handler accepts the synthetic id without a DB lookup. 201 on success.

### `PATCH /api/conversations/:id`

Body: any of `{ title?: string, pinned?: boolean }`. Returns the updated `Conversation` (200) so the FE avoids a refetch. Ownership check; 404 if not owned. No title autogen here — this is the explicit user rename path.

### `DELETE /api/conversations/:id`

204 on success. Cascades to `message`; `vote` rows cascade transitively via their FK on `message.id` (no direct FK from `vote` to `conversation`). Idempotent (204 even if already gone). Ownership check.

### `POST /api/conversations/:id/messages`

The only streaming endpoint. Request body:

```ts
{
  clientMessageId: string;        // UUID, dedupes retries
  tierId: ModelTierId;            // per-turn requested tier (FE sends `tierAtSendRef.current`)
  text: string;                   // user message body
  isTemporary?: boolean;          // mirrors the synthetic id; if true, do not persist
  regenerate?: boolean;           // drop the trailing assistant turn and re-stream
  editMessageId?: string;         // truncate at this message and re-stream
}
```

Response: `Content-Type: text/event-stream`, `Cache-Control: no-store`. SSE event names use snake_case by convention (`reasoning_delta`, `answer_delta`, etc.); event payloads remain camelCase to match the FE types. Each event is `event: <type>\ndata: <json>\n\n`:

- `submitted` — `{ messageId: string }`. Sent immediately so the FE can stop showing the "submitting" affordance.
- `reasoning_delta` — `{ text: string }`. Append-only to the reasoning channel.
- `reasoning_done` — `{}`. End of the reasoning channel; the FE switches the active target to "answer". `durationSec` intentionally omitted (FE computes from wall clock per the existing hook).
- `status` — `{ label: string, state: "active" | "done" }`. For non-reasoning interstitials (typed as the third `MessagePart` variant). MVP will only emit `status` when the provider surfaces an explicit signal; otherwise no events.
- `answer_delta` — `{ text: string }`. Append-only to the answer channel.
- `terminal` — `{ status: "done" | "stopped", messageId: string, attribution: ModelAttribution }`. Always the last frame on a successful stream (including stop).
- `error` — `{ code, severity, title, body, retryAfterMs?, meta? }`. Final frame on failure; no `terminal` follows. The FE's `StreamStatus` switches to `error`.

Behavior:

- **Idempotency**: `clientMessageId` is unique per conversation. A duplicate `POST` with the same `clientMessageId` reattaches to the prior result if it's already terminal, returning a single-frame stream replaying the persisted `terminal`. (No mid-stream resume — that's PRD 04 §5.1 P1.)
- **Persistence**: user message persists once `submitted` is sent. Assistant message persists once `terminal` (`done` or `stopped`) is emitted, with `parts` reflecting whatever streamed before stop. `error` does not persist an assistant message.
- **Stop**: when the client closes the EventSource, the AbortSignal cancels `streamText`, the BE flushes whatever is in the accumulator into `parts`, computes attribution from partial usage if available (`costConfidence: "estimate"`), and writes the message with `status: "stopped"`. No `terminal` is sent (the socket is already closed).
- **Regenerate**: drops the trailing assistant message(s) at the tail of the conversation, then proceeds as normal. The user message is not re-sent.
- **Edit-and-rerun**: truncates the conversation at `editMessageId` (exclusive of), replaces the user message at that position with the new `text`, then proceeds as normal. Same auth/ownership checks.
- **Temporary**: if `isTemporary` is true (or the synthetic conversation id is in the BE's in-memory set), the handler streams normally but skips all DB writes. The `terminal` event still carries `attribution`.
- **Title autogeneration**: on the first successful `terminal` for a conversation, fire-and-forget a single small-model call ("summarize this exchange into a 4-6 word title") and `UPDATE conversation.title`. The FE refetches the title only on its next bootstrap; this is acceptable for MVP.
- **Ownership**: 404 if the conversation is not owned by the caller. 400 if `tierId` is not in the model registry.

### `POST /api/messages/:id/feedback`

Body: `{ feedback: "up" | "down" | null }`. Upserts into `vote`. 204 on success. Ownership check (caller must own the parent conversation). Idempotent.

### `PUT /api/preferences`

Body: full `UserPreferences`. Replaces the row. 204 on success. Validated against the FE type with zod. Anonymous users can set preferences; they persist to their anonymous session record.

### `PUT /api/account/byok`

Body: `{ provider: "anthropic" | "openai" | ..., apiKey: string }`. Returns the updated `AccountInfo` (with `byokEnabled: true`, `byokMaskedKey: "sk-...XXXX"`). **Rejects 403 for anonymous users** (per PRD 04 §5.2 — anonymous accounts cannot hold BYOK keys). The key is encrypted at rest (envelope encryption with a server-side key — out of MVP scope to make this production-grade, but use a single env var as the encryption key for v0 and call it out for hardening).

### `DELETE /api/account/byok/:provider`

Returns the updated `AccountInfo`. 403 for anonymous users. Idempotent.

### Auth endpoints

Better Auth registers `/api/auth/[...all]` and handles anonymous session bootstrap (cookie issued on first hit to `/api/bootstrap` if no session exists), upgrade-to-email/passkey when real auth UI ships, and sign-out. No deep spec here — Better Auth owns the surface.

## Data model

Drizzle-style sketch. Snake_case columns; camelCase TS fields. `jsonb` columns store the FE-shaped values directly so reads round-trip without transformation.

```ts
// web/drizzle/schema.ts

// `user` and `session` are managed by Better Auth; we extend `user` with our columns.
export const user = pgTable("user", {
  id: text("id").primaryKey(),                       // Better Auth id
  email: text("email"),                              // null for anonymous
  name: text("name").notNull().default("Guest"),
  isAnonymous: boolean("is_anonymous").notNull().default(true),
  planLabel: text("plan_label").notNull().default("Free"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

// Better Auth session table — schema dictated by the lib; we read from it.

export const conversation = pgTable("conversation", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  title: text("title").notNull().default("New chat"),
  selectedTierId: text("selected_tier_id").notNull(),  // ModelTierId
  pinned: boolean("pinned").notNull().default(false),
  // No is_temporary column: temporary chats never reach this table (see Notes).
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
}, (t) => ({
  byUserUpdated: index("conversation_user_updated_idx").on(t.userId, t.updatedAt.desc()),
}));

export const message = pgTable("message", {
  id: uuid("id").primaryKey().defaultRandom(),
  conversationId: uuid("conversation_id").notNull().references(() => conversation.id, { onDelete: "cascade" }),
  clientMessageId: uuid("client_message_id"),         // unique per conversation; nullable for assistant rows
  role: text("role").notNull(),                       // "user" | "assistant"
  parts: jsonb("parts").$type<MessagePart[]>().notNull(),
  status: text("status"),                             // StreamStatus | null
  attribution: jsonb("attribution").$type<ModelAttribution | null>(),
  createdAt: timestamp("created_at").notNull().defaultNow(),
}, (t) => ({
  byConversation: index("message_conversation_idx").on(t.conversationId, t.createdAt),
  uniqClientMessage: uniqueIndex("message_client_msg_uniq").on(t.conversationId, t.clientMessageId),
}));

export const vote = pgTable("vote", {
  messageId: uuid("message_id").primaryKey().references(() => message.id, { onDelete: "cascade" }),
  feedback: text("feedback").notNull(),               // "up" | "down"
  createdAt: timestamp("created_at").notNull().defaultNow(),
});
// `feedback: null` from the API deletes the row.

export const apiKey = pgTable("api_key", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  provider: text("provider").notNull(),               // "anthropic" | "openai" | ...
  ciphertext: text("ciphertext").notNull(),           // envelope-encrypted
  maskedKey: text("masked_key").notNull(),            // e.g. "sk-...4f2a"
  createdAt: timestamp("created_at").notNull().defaultNow(),
}, (t) => ({
  uniqUserProvider: uniqueIndex("api_key_user_provider_uniq").on(t.userId, t.provider),
}));

export const usageRollup = pgTable("usage_rollup", {
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  periodStart: timestamp("period_start").notNull(),   // first of the month, UTC
  used: integer("used").notNull().default(0),         // unit: same as UsageBudget.used (turns or credits, TBD)
  limit: integer("limit_value").notNull(),            // copied from plan at period start
  isByok: boolean("is_byok").notNull().default(false),
}, (t) => ({
  pk: primaryKey({ columns: [t.userId, t.periodStart] }),
}));
```

Notes:

- Temporary chats never reach `conversation`/`message`. Their ids live in a short-lived in-memory `Set` keyed by session so subsequent `POST messages` requests within the same Node process are accepted; if the process dies, the next request 404s — acceptable for MVP. The in-memory set assumes single-process dev; production multi-instance deployment will require a Redis-backed set or moving the synthetic id into a signed cookie.
- `message.parts` is the wider FE union (`text` | `reasoning` | `status`). The PRD-04 §6 schema allows `tool-call`/`tool-result`/`citation`/`interactive-block`; the column accepts them by typing as `jsonb` but the BE does not emit them today.
- `usageRollup.used` semantics intentionally TBD — current FE shows raw integers (`used: 312`, `limit: 1000`) with no unit. The BE will increment by 1 per successful `terminal`. Refine when the FE has a meter that needs cost-based accounting.

## Streaming

The streaming endpoint runs in a Route Handler on the Node runtime. The handler:

1. Validates the request body (zod), resolves the user from Better Auth, asserts conversation ownership (or accepts the synthetic temporary id).
2. Resolves the served model from the BE registry given the requested `tierId`. If `tierId === "auto"`, picks the configured default for `auto` (no real router at MVP — that's PRD 02). If a registry-driven fallback is needed (the chosen provider is down, etc.), records the change so the substitution event can be emitted on `terminal`.
3. Loads the conversation history (skipped for temporary) and constructs the AI SDK `messages` array.
4. Calls `streamText({ model, messages, abortSignal: request.signal, onFinish: ... })`.
5. Returns a `Response` whose body is a `ReadableStream` that pulls from the AI SDK's typed text-stream and reasoning-stream, re-encoding into our SSE event format. The encoder is implemented in `web/src/server/streaming/sse.ts` and shared with future endpoints.
6. In `onFinish`, computes `CostBreakdown` and `ModelAttribution` from the provider's usage metadata, persists the assistant message, increments `usage_rollup`, fires the title-autogen for the first turn (no `await`), and pushes the `terminal` event into the SSE stream before closing.
7. On `AbortSignal` (client closed EventSource): flushes accumulators, persists the assistant message with `status: "stopped"` and an `estimate` attribution if usage metadata is partial. No `terminal` is emitted (socket already gone).

Concretely about emitting the FE's typed events:

- `streamText` returns separate streams for `text` and `reasoning`. The encoder forwards each chunk into `answer_delta` / `reasoning_delta`. When the reasoning stream closes, emit `reasoning_done` exactly once before any `answer_delta`. (If the provider does not surface a reasoning channel, skip both events — the FE renders nothing for them and that is fine.)
- `status` parts are only emitted when the BE explicitly stages an interstitial (none at MVP, so this event type ships unused but reserved).

Explicit non-features:

- **No Redis-backed resumable streams.** A dropped TCP connection means a dropped stream; the user retries via the FE's regenerate button. PRD 04 §5.1 marks resumable replay as P1.
- **No server-side stop endpoint.** Stop is the client closing the EventSource. The BE's `AbortSignal` path is the entire stop story.
- **No queue or background worker.** Title autogen runs as a detached promise on the same Node request handler; if the process dies before it completes, the title stays `"New chat"` until the next turn re-fires it. Acceptable.

## Auth seam (anonymous-first)

Better Auth is mounted at `/api/auth/[...all]` with the anonymous plugin enabled. A shared `getRequestContext(request)` helper resolves the session cookie, creates an anonymous user lazily on first hit if absent, and returns `{ userId, isAnonymous }` for every route. Ownership checks are uniform: every `conversation.userId === userId` check is the only authorization needed.

BYOK gating: `PUT/DELETE /api/account/byok/*` reject with 403 when `isAnonymous === true`. The bootstrap response sets `account.byokEnabled = false` and omits `byokMaskedKey` for anonymous users so the FE's current unconditional rendering degrades to "BYOK off, no key shown" without a code change.

FE follow-up (not BE work): once we add an upgrade-to-email/passkey flow (Better Auth supports it), the settings panel in `web/src/components/chat/settings-dialog.tsx` should gate BYOK editing behind `!isAnonymous`.

## Provider integration

Default: Vercel AI Gateway (PRD 04). One env var (`AI_GATEWAY_API_KEY`) and the AI SDK's gateway provider — gets us breadth, fallback behavior, and consistent metadata without juggling per-provider keys. Direct provider keys (Anthropic, OpenAI) work too via the same AI SDK calls; per-user BYOK keys are resolved at request time from `api_key` and passed as a provider option.

BE model registry (`web/src/server/providers/tiers.ts`) is the single source of truth for: (a) validating incoming `tierId`, (b) mapping tier to `{providerId, modelId, displayLabel, pricing}`, (c) feeding the `ModelTier[]` array in the bootstrap response. Same shape as `web/src/lib/model-tiers.ts` but BE-owned; the FE registry stays so the picker can hint cost/speed without a network call but should be flagged for removal once the FE consumes `bootstrap.modelTiers`.

Pricing math (only the fields the FE reads):

- `listPriceInPerM`, `listPriceOutPerM`: from the registry, per model.
- `inputTokens`, `outputTokens`, `reasoningTokens`, `cachedInputTokens`: from `onFinish` usage. Map provider-specific shapes (`promptTokens` / `completionTokens` / `reasoningTokens` / `cachedTokens`) into the canonical fields.
- `reasoning_tokens` is billed at the output rate and is **never** cache-eligible (PRD 07 §7 rule 7).
- `longContext.flat: true` for Anthropic models in the registry (Anthropic-style flat pricing — PRD 07 §4.1). For models with long-context tiers (Gemini, etc.), populate `appliedTier` when the input token count exceeds the threshold from the registry. Honor the mutual-exclusivity invariant: either `sessionMultiplier` or `appliedTier`, never both, and never when `flat` is true.
- `subtotalUsd`: computed from tokens, prices, and any applicable surcharge.
- `sessionSurchargeUsd`: 0 at MVP (no session-multiplier model in the registry yet — populate when we add one).
- `promoApplied: false` at MVP.
- `costConfidence: "exact"` when usage metadata is complete (i.e. `done`); `"estimate"` for `stopped` paths where usage may be partial.

Substitution callout: whenever the served `(provider, modelId)` differs from the registry's choice for the requested `tierId`, emit `attribution.substitution` with one of the six FE-rendered reason codes. The other three codes from PRD 07 (`auto_route`, `budget_cap`, `policy_route`) are not used until the FE renders them.

Skipped pricing fields from PRD 07 the FE does not read: `cost_scope`, `multipliers.{cached_input, batch, promo}`, `promo.{id, effective_until, date_valid_at_turn}`, `notes`. We can add these to `attribution` later without an FE change.

## Errors & limits

Every error response — REST and the SSE `error` frame — uses the PRD-08 envelope:

```ts
type ErrorEnvelope = {
  code: string;             // e.g. "INVALID_TIER", "OWNERSHIP", "PROVIDER_UPSTREAM"
  severity: "info" | "warning" | "error" | "fatal";
  title: string;            // short, user-visible
  body: string;             // 1-2 sentences
  actions?: { label: string; kind: "retry" | "open_settings" | "dismiss" }[];
  retryAfterMs?: number;
  meta?: Record<string, unknown>;
};
```

The FE does not render most of this today, but shipping the envelope now is cheap and avoids a v2 break. Mapping to FE behavior:

- REST errors return `{error: ErrorEnvelope}` with an HTTP status code matching `severity` (400/403/404/409/500).
- Stream errors emit `event: error` with the envelope and end the stream; the FE flips `StreamStatus` to `"error"`.
- Stream stop (client-initiated) is not an error and not a `terminal` either — the socket closes, and the BE owns the persistence write: the `AbortSignal` handler flushes accumulators and writes the assistant message with `status: "stopped"` and an `estimate` attribution. The FE's local stream-state accumulator (current `useMockStream`) is display-only; once the FE swaps to the real EventSource, there is no client-side DB equivalent and no duplicate write risk.

**No rate limiting or budget enforcement at MVP.** Deliberate deferral. PRD 04 §5.6 wants both; we will add them once the model registry has real cost data flowing into `usage_rollup` and there is a UI to surface a soft-cap warning. One-line follow-up: a per-user-per-minute counter in Postgres is sufficient to start when we need it.

## Open questions / decisions for the user

- **Hosting**: Vercel (zero-config Next 16 deploy, gateway integration) or self-host on Fly/Render (more control, cheaper at scale, more ops). **Recommendation: Vercel** for MVP, revisit when we hit volume.
- **Postgres host**: Neon (branch-per-PR, autosuspend) or a local-then-managed approach (Supabase/Render). **Recommendation: Neon for dev and prod** initially; trivial to migrate.
- **Auth from day one**: build single-user dev mode now and add auth later, or ship Better Auth + anonymous from the start. **Recommendation: Better Auth + anonymous from day one** to avoid a data-migration headache.
- **Wire format**: camelCase end-to-end (no adapter) or snake_case BE with an FE adapter. **Recommendation: camelCase end-to-end** — the FE types are camelCase, we save an adapter layer.
- **Provider for v0**: wire a real model (Anthropic via Vercel AI Gateway is the smallest path) or ship an echo bot that returns the user's text after a 1s delay. **Recommendation: real Anthropic via the gateway** — `streamText` plumbing is the same either way and the testing fidelity is much higher.
- **BYOK encryption**: single env-var key for v0 versus KMS/secret-manager envelope encryption. **Recommendation: env-var key for v0**, but call it out explicitly so it is not forgotten before public users land.
- **Usage units**: increment `usage_rollup.used` by 1 per turn (matches FE's current display) or by USD-pennies/credits (more honest). **Recommendation: per-turn counter for MVP**, switch when the FE has a real meter design.

## Milestones

### M0 — Dev scaffold + bootstrap + read-only conversation

Scope:
- `web/src/server/db` Drizzle setup with `user`, `session`, `conversation`, `message`, `vote`, `api_key`, `usage_rollup`. Initial migration.
- Better Auth wired with the anonymous plugin at `/api/auth/[...all]`.
- `GET /api/bootstrap` returning a real payload (anonymous user with empty state, but a hand-inserted seed conversation for local dev).
- `GET /api/conversations/:id` returning a seeded conversation.
- BE model registry at `web/src/server/providers/tiers.ts`.

Demo criterion: the FE runs unchanged against the BE — first paint shows the seeded conversation, sidebar list populated, settings dialog shows the seeded preferences/account. No streaming yet (Send button can be disabled in dev, or we keep the mock stream behind a feature flag for one milestone).

Effort: ~2 days for a focused engineer.

### M1 — Send + stream + persist + attribution

Scope:
- `POST /api/conversations/:id/messages` with the full SSE event set.
- AI SDK v6 `streamText` wired to a real provider (Anthropic via Vercel AI Gateway, per the recommendation).
- `onFinish` computes `CostBreakdown` + `ModelAttribution` from usage and emits `terminal`.
- Stop path: AbortSignal cancellation + persisting partial assistant message with `status: "stopped"` and `costConfidence: "estimate"`.
- `POST /api/conversations` and idempotency via `clientMessageId`.

Demo criterion: open the FE, type "hello", watch reasoning + answer stream in, see the AttributionRow show a real cost. Hit Stop mid-answer, the partial message persists. Refresh — message still there. No FE code changes.

Effort: ~3-4 days. Streaming has the most ways to be wrong.

### M2 — Mutations (rename, pin, delete, feedback, preferences, regen, edit)

Scope:
- `PATCH/DELETE /api/conversations/:id`.
- `POST /api/messages/:id/feedback`.
- `PUT /api/preferences`.
- `regenerate: true` and `editMessageId` paths on the messages endpoint.
- Title autogeneration (background promise on first `terminal`).
- Temporary chat handling (synthetic ids, no DB writes).

Demo criterion: every sidebar action (rename, pin, delete) round-trips. Settings dialog persists changes across refresh. Regenerate replaces the trailing assistant turn. Edit-and-rerun truncates and re-streams. Temporary chat sends a turn and leaves no DB trace.

Effort: ~2 days.

### M3 — Auth seam + BYOK + usage rollup

Scope:
- BYOK endpoints (`PUT /api/account/byok`, `DELETE /api/account/byok/:provider`) with anonymous gating.
- Per-user BYOK key resolution in the messages handler (use the user's key when present).
- `usage_rollup` incrementing on every successful `terminal`, surfaced via `GET /api/bootstrap`.
- Verify the FE's account/usage display works for an upgraded (non-anonymous) account.

Demo criterion: a non-anonymous account can save a BYOK key, the next turn uses it, and the cost meter increments correctly. Anonymous users get 403 on BYOK writes; bootstrap returns `byokEnabled: false`.

Effort: ~2 days, mostly the encryption-at-rest plumbing.

### M4 — Hardening (optional, ship-when-needed)

Scope:
- PRD-08 error envelope on every code path (REST + SSE).
- Structured JSON logs with `requestId`, `userId`, `conversationId`, `turn_ms`, provider/model, tokens, cost.
- BE-side model registry pricing tightened against real provider docs.
- Substitution code emission for provider fallback (gateway routes around an outage).
- Document the hardening gaps explicitly: no rate limit, no observability stack, no resumable replay.

Demo criterion: a forced provider error renders a clean error frame on the FE; a forced gateway fallback emits a `provider_fallback` substitution.

Effort: ~2 days.

## What we are explicitly NOT building (and where it lives in the PRD)

| Deferred capability | PRD reference |
| --- | --- |
| Attachments and file uploads | PRD 01 §5.3, F21 |
| Tools / tool calls | PRD 02 |
| Web search | PRD 02 |
| Memory / personalization | PRD 02 |
| Citations and interactive blocks (additional `MessagePart` variants) | PRD 01 §4.4; PRD 04 §6 |
| Resumable streaming replay | PRD 04 §5.1 (P1) |
| Server-side stop endpoint | PRD 04 §5.1 (P1) |
| Structured outputs / JSON-schema-constrained responses | PRD 02 (no FE surface yet) |
| GDPR export and delete user-data flows | PRD 04 §5.7 (no FE surface yet) |
| Payments, plan upgrades, BYOK billing split | PRD 05; PRD 07 §6.3 |
| Observability stack (OTel, metrics, error reporting) | PRD 04 §5.10 |
| Rate limiting / cost budget enforcement | PRD 04 §5.6; PRD 08 |
| Audit log enforcement and admin tools | PRD 04 §5.8 (P1) |
| Sync engine / multi-device live updates | PRD 03 |
| Conversation share/export UI | PRD 01 §4.8 (no FE surface yet) |
| Substitution codes `auto_route`, `budget_cap`, `policy_route` | PRD 07 §5 (no FE rendering yet) |
| Pricing fields `cost_scope`, `multipliers.*`, `promo.*`, `notes` | PRD 07 §4.1 (no FE rendering yet) |
| Period-end ISO + platform/BYOK budget split on `UsageBudget` | PRD 07 §6.3 (FE shape is simpler today) |
| Server-curated `PromptSuggestion` set | PRD 01 §4.3 (mock is static client-side, fine) |

## File / folder layout

All new code lives inside the existing `web/` Next app:

```
web/
  drizzle/
    schema.ts                      # tables defined above
    migrations/                    # drizzle-kit output
  src/
    app/
      api/
        bootstrap/route.ts
        conversations/
          route.ts                   # POST (create)
          [id]/
            route.ts                 # GET, PATCH, DELETE
            messages/route.ts        # POST (SSE)
        messages/
          [id]/feedback/route.ts     # POST
        preferences/route.ts         # PUT
        account/
          byok/route.ts              # PUT
          byok/[provider]/route.ts   # DELETE
        auth/[...all]/route.ts       # Better Auth handler
    server/
      db/
        client.ts                  # drizzle client
        repositories/              # one per table cluster (conversations, messages, users, votes, keys, usage)
      auth/
        config.ts                  # Better Auth config + anonymous plugin
        context.ts                 # getRequestContext(request)
      providers/
        tiers.ts                   # BE model registry (mirrors FE shape)
        gateway.ts                 # AI SDK v6 model factory
        pricing.ts                 # CostBreakdown + ModelAttribution math
      streaming/
        sse.ts                     # SSE encoder + event types
        handler.ts                 # shared stream-and-persist orchestration
      routes-shared/
        schemas.ts                 # zod request bodies
        errors.ts                  # ErrorEnvelope + helpers
```

Conventions:
- Server-only modules live under `web/src/server/**` so accidental client-side imports trip TypeScript via `server-only` markers where useful.
- Drizzle schema is the only place table shapes live; repositories return camelCase TS objects shaped like the FE types so route handlers are trivial passthroughs.
- The SSE encoder is one place; every event type's payload is a discriminated TS union so the FE and BE can share a `web/src/lib/stream-events.ts` later without a refactor.
