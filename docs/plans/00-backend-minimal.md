# Backend Minimal Plan (Python / FastAPI)

> **Implementation status**: M0–M4 + all Post-M4 hardening items shipped on `main`. 261 tests pass + 1 known xfail (stop-path). The [Post-M4: deferred hardening](#post-m4-deferred-hardening) section below is preserved as a record; each item is now checked off with its landing PR.

The smallest Python backend that lets the existing Next.js FE at `web/` run against real persistence and a real model provider with **zero UI changes**. The BE is a **separate service** — FastAPI + Postgres, deployed independently, talking to the FE over CORS. Anchored to the FE wire shapes in `web/src/lib/types.ts` and the behavior in `web/src/components/chat/chat-thread.tsx`. PRDs guide direction; anything the FE does not yet render or call is deferred.

"Zero UI changes" caveat: because the BE is no longer co-located, the FE needs a small `apiClient` follow-up to learn the BE origin (`NEXT_PUBLIC_API_BASE_URL`) and send `credentials: 'include'`. No visual changes, no component edits, no new buttons.

## Goal & non-goals

In scope (justified by existing FE surface):

- Bootstrap payload replacing every `MOCK_*` constant in `web/src/lib/mock-data.ts` with one network call.
- Conversation CRUD: list, read, create, rename, pin, delete.
- Single streaming endpoint producing the FE-rendered parts: `reasoning`, `text`, `status`. Stop = client closes the connection; partial parts persist (PRD 01 §4.1).
- Terminal `ModelAttribution` on the last frame, replacing FE's `freshAttribution()` stub.
- Message feedback, `UserPreferences`, BYOK write/delete — every settings-dialog mutation has a backend.
- Anonymous-first sessions via custom minimal seam (PRD 04 §5.5) — per-user persistence from day one, no FE auth surface.
- Per-turn requested tier captured from the request body (FE already sends `tierAtSendRef`).
- **CORS configuration** first-class: different origin in dev and prod means CORS headers, allowed methods, credentialed cookies, SSE headers are BE's job.

Explicitly out (no FE surface today):

- Attachments / uploads (PRD 01 §5.3, F21); tools, web search, memory, citations, interactive blocks (PRD 02; PRD 01 §4.4).
- Resumable replay and server-side stop (PRD 04 §5.1 P1).
- Conversation export, share links, audit log (PRD 01 §4.8; PRD 04 §5.8 P1).
- Sync engine / multi-device (PRD 03); payments / plans / BYOK budget split (PRD 05; PRD 07 §6.3).
- Rate limiting, cost budget enforcement, abuse protection (PRD 04 §5.6, PRD 08).
- Full observability stack (PRD 04 §5.10) — replaced by structured JSON logs.
- Substitution codes the FE does not render (`auto_route`, `budget_cap`, `policy_route`).
- Server-curated prompt suggestions (`MOCK_SUGGESTIONS` stays client-static).

Known FE follow-ups (callouts, not BE work):

- **API base URL** via `NEXT_PUBLIC_API_BASE_URL`.
- **`apiClient`**: thin `web/src/lib/apiClient.ts` that prepends the base URL and sets `credentials: 'include'` + JSON content-type.
- **SSE consumer**: `fetch` + ReadableStream parser; native `EventSource` rejected (no header config, unreliable cross-origin credentials).
- **Conversation create**: FE switches from client-only to `POST /api/conversations` (one-line call site change).
- **BYOK gating**: once upgrade flow exists, `settings-dialog.tsx` gates BYOK editing behind `!isAnonymous`. BE returns `byokEnabled=false` for anonymous so today's unconditional UI degrades cleanly.
- `reasoningDurationSec` stays FE-computed; BE does not emit it.
- `freshAttribution()` stub deleted once `terminal` ships (one-line FE change).

## Architecture overview

```
[ Next.js 16 FE at web/  (Vercel or any static host) ]
        |
        |  fetch(NEXT_PUBLIC_API_BASE_URL + "/api/...", { credentials: "include" })
        |  EventSource-style stream via fetch + ReadableStream
        v
   [ CORS preflight + credentialed request ]
        |
        v
[ FastAPI service at api/  (Fly.io / Render / self-hosted) ]
        |
        +-- main.py            (FastAPI app + CORS + lifespan)
        +-- routes/            (bootstrap, conversations, messages SSE, feedback, preferences, account, auth)
        +-- streaming/         (sse-starlette wiring + stream-and-persist orchestration)
        +-- auth/              (signed-cookie sessions, anonymous-first dependency)
        +-- providers/         (DeepSeek/OpenAI-compatible + Anthropic SDK wrappers, BE tier registry, pricing math)
        +-- db/                (SQLAlchemy 2.0 async + repositories)
        +-- schemas/           (Pydantic v2 with camelCase aliases for the wire)
        |
        v
[ Neon Postgres (or local Postgres for dev), Alembic migrations ]
   tables: users, sessions, conversation, message, vote, api_key, usage_rollup
```

Stack picks (one-line justifications):

- **FastAPI** — async, native SSE, Pydantic v2 alias generators, type-first ergonomics.
- **ASGI server** — `uvicorn` for dev; `uvicorn --workers N` in prod. No separate reverse proxy beyond Fly/Render's edge.
- **Pydantic v2** with `model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)` plus explicit `Field(alias=...)` where needed. Python stays snake_case; wire JSON is camelCase, matching `web/src/lib/types.ts`.
- **Postgres + SQLAlchemy 2.0 async** with `asyncpg` and `Mapped[...]` / `mapped_column(...)`. **Alembic** under `api/alembic/versions/`.
- **Custom minimal anonymous-first sessions** — no clean Python equivalent of Better Auth's anonymous plugin (see Auth seam). Cookie signed with `itsdangerous`, server-side session row, anonymous user row created on first hit. Upgrade stubbed at `/api/auth/*`.
- **DeepSeek via the OpenAI-compatible SDK** is the main provider — `client.chat.completions.create(..., stream=True)` against `base_url=https://api.deepseek.com` yields token deltas with usage on the final chunk. The Anthropic SDK ships as an alternate backend (`client.messages.stream(...)`). **LiteLLM** is the future option for broader multi-provider normalization; Vercel AI Gateway is reachable via plain HTTPS but not default.
- **SSE** via `sse-starlette`'s `EventSourceResponse` — built-in keep-alive matters for idle tabs.
- **Cancellation** — poll `Request.is_disconnected()` inside the SSE generator AND wrap the SDK consumer in a task cancelled on disconnect.
- **Background work** — `asyncio.create_task` fire-and-forget on the same worker for title autogen. No Celery/Arq/Redis at MVP; **`arq`** is the future pick for durable jobs.
- **Encryption** — `cryptography` library, AES-GCM with env-var KEK for v0 (KMS envelope deferred).
- **Logging** — structured JSON via `structlog`: `request_id`, `user_id`, `conversation_id`, `turn_ms` per request, plus `prompt_tokens`, `completion_tokens`, `cost_usd` on terminal (internal log field names; wire stays camelCase).
- **Dev tooling** — **`uv`** for env/deps, `ruff`, `mypy --strict`. Tests: `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, `respx` for mocking the provider SDK transport (DeepSeek/OpenAI-compatible and Anthropic).
- **Deployment** — **Fly.io** (Docker, autoscale-to-zero, fast deploys). Render is a fine alternative. FE stays on Vercel.

Wire-format decision: **camelCase end-to-end**. The FE types are camelCase; emitting/accepting camelCase JSON from Pydantic via `alias_generator=to_camel` keeps both sides honest without an adapter layer.

## Architectural shifts vs the Node plan

The biggest change: the BE is **no longer co-located with the FE**. Python fits streaming/providers/pricing; a separate deploy keeps the FE footprint identical. Knock-on effects:

- **CORS + cross-origin cookies** at `CORSMiddleware`: origins from `CORS_ALLOWED_ORIGINS` env list, echo the request `Origin` (**never `*`** with credentials), preflight TTL 600s. Session cookie is `HttpOnly; Secure; SameSite=None; Path=/` in prod, `SameSite=Lax` without `Secure` in dev. FE switches SSE consumption to `fetch`+ReadableStream (`EventSource` rejected); FE base URL via `NEXT_PUBLIC_API_BASE_URL`.
- **Deploy split** — FE on Vercel, BE on Fly.io. Independent scaling: streaming wants long-lived processes that don't fit Vercel's serverless model.
- **Type sharing** — TS and Pydantic diverge by hand for now. Future: OpenAPI → `openapi-typescript`. Defer until drift bites.

## Wire contract

All endpoints are JSON over HTTPS unless noted. CORS headers from `CORSMiddleware` on every response. The SSE endpoint uses `text/event-stream` via `EventSourceResponse`. Mutations are scoped to the caller's user. Responses are camelCase. Errors use the envelope from `## Errors & limits`.

### `GET /api/bootstrap`

Replaces every `MOCK_*` import in `chat-thread.tsx` in one round-trip:

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

Behavior: idempotent, works for anonymous users (synthesized `AccountInfo` with empty email, `planLabel="Free"`, `byokEnabled=false`). `usage.isByok` mirrors whether any `api_key` row exists. No pagination — the FE filters client-side. 200 on success. **First-hit side effect**: creates anonymous user + session row if no cookie (see Auth seam).

### `GET /api/conversations/:id`

Returns a full `Conversation`. 404 if not owned (do not leak existence).

### `POST /api/conversations`

Body: `{ selectedTierId, isTemporary }`. Returns a new `Conversation` with `messages: []` and title `"New chat"`. For `isTemporary: true`, returns a synthetic (un-persisted) id; subsequent `GET` 404s, but `messages` POST accepts it without a DB lookup. 201.

### `PATCH /api/conversations/:id`

Body: `{ title?, pinned? }`. Returns the updated `Conversation` (no FE refetch). Ownership-checked. The explicit user rename path — no title autogen.

### `DELETE /api/conversations/:id`

204. Cascades to `message`; `vote` cascades transitively. Idempotent. Ownership-checked.

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

Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-store`, `X-Accel-Buffering: no` (defeats nginx/CDN buffering). Event names are snake_case; payloads are camelCase. Each event is `event: <type>\ndata: <json>\n\n`:

- `submitted` — `{ messageId }`. Sent immediately.
- `reasoning_delta` — `{ text }`. Append-only.
- `reasoning_done` — `{}`. FE switches target to "answer". `durationSec` omitted (FE wall-clock).
- `status` — `{ label, state: "active" | "done" }` (camelCase, mirrors `MessagePart` `status` variant). Only emitted when the provider surfaces an explicit signal — not at MVP.
- `answer_delta` — `{ text }`. Append-only.
- `terminal` — `{ status: "done", messageId, attribution: ModelAttribution }`. Last frame on success. A `stopped` terminal is never emitted (socket already closed; see Behavior).
- `error` — `{ code, severity, title, body, retryAfterMs?, meta? }`. Final frame on failure; FE flips `StreamStatus` to `error`.

Behavior:

- **Idempotency**: `clientMessageId` unique per conversation. Duplicate POST with same id reattaches to the prior terminal result and replays it as a single frame. (No mid-stream resume — PRD 04 §5.1 P1.)
- **Persistence**: user message persists on `submitted`. Assistant message persists on `terminal` (always `done`) OR on client disconnect (`status: "stopped"`; see Stop). `error` does not persist.
- **Stop**: client disconnect → `Request.is_disconnected()` → cancel SDK task, flush accumulator into `parts`, compute attribution from partial usage (`costConfidence: "estimate"`), write with `status: "stopped"`. No `terminal` (socket closed).
- **Regenerate**: drop trailing assistant message(s), proceed. User message not re-sent.
- **Edit-and-rerun**: truncate at `editMessageId` (exclusive), replace the user message at that position, proceed.
- **Temporary**: stream normally, skip all DB writes. `terminal` still carries `attribution`.
- **Title autogen**: on first `terminal`, `asyncio.create_task` a small-model call ("summarize into a 4-6 word title") and `UPDATE conversation.title`. FE picks it up on next bootstrap.
- **Ownership**: 404 if not owned. 400 if `tierId` not in registry.

### `POST /api/messages/:id/feedback`

Body: `{ feedback: "up" | "down" | null }`. Upserts into `vote`. 204. Ownership-checked. Idempotent.

### `PUT /api/preferences`

Body: full `UserPreferences`. Replaces the row. 204. Validated by Pydantic. Anonymous users can set preferences.

### `PUT /api/account/byok`

Body: `{ provider, apiKey }`. Returns updated `AccountInfo` (`byokEnabled: true`, `byokMaskedKey: "sk-...XXXX"`). **403 for anonymous users** (PRD 04 §5.2). Key encrypted at rest with AES-GCM (env-var KEK for v0; KMS envelope deferred).

### `DELETE /api/account/byok/:provider`

Returns updated `AccountInfo`. 403 for anonymous. Idempotent.

### Auth endpoints

- `POST /api/auth/upgrade` — body `{ email, password?, ...passkey-stub }`. Mutates the current user row in place (`is_anonymous=False`, sets `email`), re-signs the cookie, returns updated `AccountInfo`. Stubbed for MVP; ships behind a feature flag.
- `POST /api/auth/signout` — clears cookie, revokes session row. Ships when the FE has a sign-out button.

No deep auth semantics yet (no OAuth, no email verification, no passkey ceremony). Shape is stubbed so the contract is in place when the FE catches up.

## Data model

SQLAlchemy 2.0 sketch. Snake_case columns and attributes; Pydantic handles camelCase at the wire boundary. `JSONB` columns store FE-shaped payloads directly so reads round-trip without transformation.

```python
# api/app/db/models.py (sketch)

from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, Integer, ForeignKey, Index, UniqueConstraint, PrimaryKeyConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="Guest")
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    plan_label: Mapped[str] = mapped_column(String, nullable=False, default="Free")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False, default="New chat")
    selected_tier_id: Mapped[str] = mapped_column(String, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # No is_temporary column: temporary chats never reach this table.
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("conversation_user_pinned_updated_idx", "user_id", "pinned", "updated_at"),
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    client_message_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    parts: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    attribution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("message_conversation_idx", "conversation_id", "created_at"),
        UniqueConstraint("conversation_id", "client_message_id", name="message_client_msg_uniq"),
    )


class Vote(Base):
    __tablename__ = "vote"

    message_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("message.id", ondelete="CASCADE"), primary_key=True)
    feedback: Mapped[str] = mapped_column(String, nullable=False)  # "up" | "down"
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class ApiKey(Base):
    __tablename__ = "api_key"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    ciphertext: Mapped[str] = mapped_column(String, nullable=False)
    masked_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="api_key_user_provider_uniq"),
    )


class UsageRollup(Base):
    __tablename__ = "usage_rollup"

    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_value: Mapped[int] = mapped_column(Integer, nullable=False)
    is_byok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "period_start", name="usage_rollup_pk"),
    )
```

Alembic's `env.py` targets `Base.metadata`; a deterministic `naming_convention` keeps constraint names stable across autogen.

Notes:

- Temporary chats never hit `conversation`/`message`. Their ids live in an in-process `set[UUID]` keyed by user (TTL-cleared); a dead worker drops them (404 next time) — fine for MVP. Multi-worker prod will need a Redis-backed set or a signed-cookie id.
- `message.parts` is the FE union (`text` | `reasoning` | `status`). The `JSONB` column accepts the wider PRD-04 §6 schema (`tool-call` etc.) but the BE emits none of those.
- `usage_rollup.used` semantics TBD — FE shows raw integers with no unit. Increment by 1 per `terminal` for now; switch to cost-based when the FE has a real meter.

## Streaming

The streaming endpoint is a FastAPI route returning an `EventSourceResponse` (from `sse-starlette`). The route:

1. Validates the body, resolves the user, asserts conversation ownership (or accepts the synthetic temporary id).
2. Resolves the served model from the BE registry given `tierId` (`auto` → configured default). Records any registry-driven substitution for `terminal`.
3. Loads history (skipped for temporary), persists the user message, yields `submitted` (with the DB id).
4. Calls the provider stream and maps its events. For the main DeepSeek/OpenAI-compatible path: `delta.reasoning_content` → `reasoning_delta` / `reasoning_done` (DeepSeek exposes raw thinking tokens via `deepseek-reasoner`); `delta.content` → `answer_delta`; the final chunk's `usage` is accumulated and finalizes the turn. The Anthropic backend maps the equivalent `thinking` / `text` blocks and `message_delta` / `message_stop`.
5. Post-stream: compute `CostBreakdown` + `ModelAttribution`, persist the assistant message, increment `usage_rollup`, fire title autogen via `asyncio.create_task(...)` on first turn, yield `terminal`.
6. **Cancellation**: an `asyncio.Task` wraps the SDK iteration; the generator polls `request.is_disconnected()` between yields. On disconnect: cancel, flush accumulators, persist with `status="stopped"` and `costConfidence="estimate"`. No `terminal` (socket already closed).

**Invariant**: exactly one `reasoning_done` precedes any `answer_delta`. If there is no thinking block, no `reasoning_*` events are emitted at all.

Other notes:

- `status` parts are only emitted when the BE explicitly stages an interstitial (none at MVP — event type reserved).
- Keep-alive pings every 15s via `sse-starlette`; the FE only listens for named events, so they are invisible to the handler.

Explicit non-features:

- **No Redis-backed resumable streams.** Dropped TCP = dropped stream; user retries via regenerate. PRD 04 §5.1 marks this P1.
- **No server-side stop endpoint.** Stop is the client closing the connection.
- **No queue or background worker.** Title autogen runs as a detached `asyncio.Task`; if the worker dies, title stays `"New chat"` until next turn re-fires.

## Auth seam (anonymous-first)

No clean Python equivalent of Better Auth's anonymous plugin exists. `fastapi-users` requires a fully registered user or an unauthenticated request; stitching anonymous-then-upgrade onto it is more code than rolling our own. Build-don't-buy wins because the surface is tiny (no FE auth UI today) and the contract is just "issue a session cookie on first hit, look it up on every request, allow in-place upgrade later." See PRD 04 §5.5.

The seam is a FastAPI dependency:

```python
# api/app/auth/dependency.py (pseudocode)

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from itsdangerous import URLSafeSerializer, BadSignature

from app.config import settings
from app.deps import get_db
from app.db.models import User, Session as DbSession

signer = URLSafeSerializer(settings.session_secret, salt="session")

COOKIE_NAME = "sid"
COOKIE_KW = dict(
    httponly=True,
    secure=settings.cookie_secure,           # True in prod
    samesite=settings.cookie_samesite,       # "none" in prod, "lax" in dev
    path="/",
    max_age=60 * 60 * 24 * 30,
)


async def current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        try:
            session_id = signer.loads(raw)
            session = await db.get(DbSession, session_id)
            if session and session.expires_at > now_utc():
                user = await db.get(User, session.user_id)
                if user:
                    return user
        except BadSignature:
            pass  # fall through to create new

    # Create anonymous user + session, set cookie.
    user = User(is_anonymous=True, name="Guest")
    db.add(user)
    await db.flush()
    session = DbSession(user_id=user.id, expires_at=now_utc() + timedelta(days=30))
    db.add(session)
    await db.commit()
    response.set_cookie(COOKIE_NAME, signer.dumps(str(session.id)), **COOKIE_KW)
    return user
```

Every route depends on `current_user`. Authorization is uniform: `conversation.user_id == user.id`.

Upgrade-to-email/passkey is `POST /api/auth/upgrade`: mutate the current (anonymous) user row in place (`is_anonymous=False`, `email`, `name`), re-sign the cookie. Spike: confirm existing conversations re-parent for free — the row id is unchanged, so every FK still points at the right user. No data migration. This is the whole reason the seam is shaped this way.

Sign-in is `POST /api/auth/login` (email + password, both required). Where upgrade *merges* the current anonymous identity in place, login is a **handoff** to an existing registered account: the current session row is repointed at the target user (`session.user_id = target.id`, flush) and re-signed onto the cookie; if no usable session arrived, a fresh session row is minted for the target. The previous user is then reclaimed — if it was anonymous, `delete_user_and_data` erases it and its guest scratch (repoint-then-delete ordering keeps the repointed session out of the cascade); an account switch (previous user is itself registered) leaves the other account untouched. So **guest work is discarded on login but preserved on upgrade** — pick the verb deliberately. Every failure mode — unknown email, `password_hash IS NULL`, wrong password — collapses into one uniform `401 INVALID_CREDENTIALS` whose title/body never reveal whether the email exists (no account enumeration); a dummy `verify_password` runs on the missing-user branch to flatten the timing side-channel. Both `/login` and `/upgrade` are IP-rate-limited (`RATE_LIMIT_LOGIN` / `RATE_LIMIT_UPGRADE`, default `5/minute`) via slowapi.

BYOK gating: `PUT/DELETE /api/account/byok/*` reject with 403 when `user.is_anonymous`. Bootstrap returns `account.byokEnabled=False` and omits `byokMaskedKey` for anonymous users, so the FE's unconditional rendering degrades cleanly. `AccountInfo` carries `isAnonymous` so the FE can gate BYOK editing behind `!isAnonymous` and choose the sign-in vs. sign-out affordance without a second round-trip.

## Provider integration

Main provider: **DeepSeek via the OpenAI-compatible Python SDK**. `PROVIDER_BACKEND=openai` with `OPENAI_BASE_URL=https://api.deepseek.com` and the platform `OPENAI_API_KEY`; tiers bind to `deepseek-chat` (fast/smart/auto) and `deepseek-reasoner` (pro). DeepSeek is the cost-leading default for the whole tier ladder and exposes raw thinking tokens on `deepseek-reasoner`. Token streaming via `chat.completions.create(..., stream=True)`, usage on the final chunk, clean cancellation. The **Anthropic SDK** is wired as an alternate backend (`PROVIDER_BACKEND=anthropic`, `ANTHROPIC_API_KEY`). Per-user BYOK keys decrypted from `api_key` at request time, passed into a per-request client (`OpenAI(api_key=..., base_url=...)` or `Anthropic(api_key=...)`).

Future paths (not MVP): **LiteLLM** for broader multi-provider normalization; **Vercel AI Gateway** via an OpenAI/Anthropic-compatible `base_url`. Both deferred — gateway-style routing/fallback isn't needed at v0.

BE model registry (`api/app/providers/tiers.py`) is the single source of truth for: (a) validating incoming `tierId`, (b) mapping tier to `{provider_id, model_id, display_label, pricing}`, (c) feeding `ModelTier[]` in bootstrap. Frozen `BaseModel` per tier. Same shape as `web/src/lib/model-tiers.ts` but BE-owned; the FE registry stays as a cost/speed hint, flagged for removal once the FE consumes `bootstrap.modelTiers`.

Pricing math (`api/app/providers/pricing.py`) — only fields the FE reads:

- `listPriceInPerM`, `listPriceOutPerM`: from the registry, per model.
- `inputTokens`, `outputTokens`, `reasoningTokens`, `cachedInputTokens`: from accumulated usage. Map the DeepSeek/OpenAI-compatible shapes (`prompt_tokens`, `completion_tokens`, `completion_tokens_details.reasoning_tokens`, `prompt_tokens_details.cached_tokens`) and the equivalent Anthropic shapes (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`) to canonical. Per PRD 07 §7 rule 7: reasoning tokens bill at output rate and are never cache-eligible — enforced in the pricing function.
- `longContext.flat: True` for DeepSeek and Anthropic (PRD 07 §4.1). For tiered models (Gemini etc.), populate `appliedTier` past the registry threshold. Invariant: either `sessionMultiplier` or `appliedTier`, never both, never when `flat` is True. Asserted, not silent.
- `subtotalUsd`: tokens × prices + surcharges.
- `sessionSurchargeUsd`: 0 at MVP. `promoApplied: False` at MVP.
- `costConfidence: "exact"` on `done`; `"estimate"` on stopped/partial.

Substitution: whenever the served `(provider, model_id)` differs from the registry's choice for `tierId`, emit `attribution.substitution` with one of the six FE-rendered reasons (`auto_downgrade`, `provider_fallback`, `rate_limited`, `capacity_reroute`, `deprecated_model`, `gateway_route`). The three unused PRD 07 codes (`auto_route`, `budget_cap`, `policy_route`) ship when the FE renders them.

Skipped pricing fields the FE does not read: `cost_scope`, `multipliers.*`, `promo.*`, `notes`. Addable to `attribution` later without FE change.

## Errors & limits

Every error response — REST and the SSE `error` frame — uses the PRD-08 envelope, expressed as a Pydantic model:

```python
# api/app/errors.py
class ErrorAction(CamelModel):
    label: str
    kind: Literal["retry", "open_settings", "dismiss"]

class ErrorEnvelope(CamelModel):
    code: str                                          # "INVALID_TIER", "OWNERSHIP", "PROVIDER_UPSTREAM", ...
    severity: Literal["info", "warning", "error", "fatal"]
    title: str
    body: str
    actions: list[ErrorAction] | None = None
    retry_after_ms: int | None = None        # serialized as retryAfterMs (alias_generator=to_camel)
    meta: dict | None = None
```

The FE does not render most of this today, but shipping the envelope now is cheap and avoids a v2 break. Mapping to FE behavior:

- REST errors raise a typed `AppError(envelope, status_code)`. A FastAPI exception handler catches `AppError` and returns `JSONResponse({"error": envelope.model_dump(by_alias=True)}, status_code=...)` with HTTP status matching `severity` (400/403/404/409/500). A separate handler catches `RequestValidationError` (Pydantic) and produces an `INVALID_INPUT` envelope at 400. A catch-all handler maps unhandled exceptions to a `FATAL` envelope at 500 (and logs at error level with the full traceback).
- Stream errors emit `event: error\ndata: <envelope>\n\n` and end the stream; the FE flips `StreamStatus` to `"error"`.
- Stream stop (client-initiated) is not an error and not a `terminal` either — the disconnect-detect handler flushes accumulators and persists with `status: "stopped"` and an `estimate` attribution.

**No rate limiting or budget enforcement at MVP.** Deliberate. When added, **`slowapi`** (Redis-backed, decorator-style, plays with `Depends(current_user)`) is the pick. PRD 04 §5.6; ship once `usage_rollup` carries real cost data and the FE has a soft-cap warning.

## Open questions / decisions for the user

- **Hosting**: **Fly.io** (Docker, autoscale-to-zero, cheap).
- **Postgres host**: **Neon** for dev and prod.
- **Auth approach**: **custom minimal seam** (`fastapi-users` lacks anonymous-then-upgrade).
- **Provider abstraction**: **DeepSeek via the OpenAI-compatible SDK as the main provider**, Anthropic SDK as an alternate backend; LiteLLM when broader multi-provider routing lands.
- **SSE library**: **`sse-starlette`** for built-in keep-alive.
- **Schema sharing**: **hand-keep for MVP**; OpenAPI codegen when drift bites.
- **Env / package manager**: **`uv`** — fastest, single tool.
- **CORS in dev**: **Next rewrites in dev, cross-origin in prod**.
- **BYOK encryption**: **env-var KEK for v0**; KMS envelope before public users.
- **Usage units**: **per-turn counter for MVP**; switch when the FE has a real meter.

## Milestones

### M0 — Scaffold + Alembic + bootstrap + read-only conversation + CORS

Scope: `api/` scaffolded (`uv`, `ruff`, `mypy`, `pytest`, Dockerfile, Fly config); SQLAlchemy async engine + Alembic with naming conventions; initial migration for all tables; FastAPI app with env-driven `CORSMiddleware`; custom session-cookie auth (anonymous on first hit); `GET /api/bootstrap`; `GET /api/conversations/:id`; BE model registry.

Demo: FE runs unchanged — first paint shows seeded conversation, sidebar populated, settings dialog hydrated. No streaming yet (Send disabled in dev). FE adds `apiClient` + `NEXT_PUBLIC_API_BASE_URL` as a one-line follow-up.

Effort: ~2-3 days (cross-origin/cookie config eats half a day).

### M1 — Send + stream + persist + attribution

Scope: `POST /api/conversations/:id/messages` with the full SSE event set via `EventSourceResponse`; DeepSeek/OpenAI-compatible SDK wired (Anthropic alternate); deltas mapped; post-stream `CostBreakdown` + `ModelAttribution` emit `terminal`; stop path via disconnect-detect + `asyncio.Task.cancel`, persisting `status: "stopped"` + `costConfidence: "estimate"`; `POST /api/conversations` and `clientMessageId` idempotency.

Demo: type "hello", watch reasoning + answer stream, AttributionRow shows real cost. Hit Stop, partial persists. Refresh — message still there.

Effort: ~4 days (streaming + disconnect + provider mapping is the high-risk area).

### M2 — Mutations + temporary chats + title autogen

Scope: `PATCH/DELETE /api/conversations/:id`; `POST /api/messages/:id/feedback`; `PUT /api/preferences`; `regenerate` and `editMessageId` paths; title autogen via `asyncio.create_task`; temporary chats (synthetic ids, in-process set).

Demo: rename/pin/delete round-trip; settings persist; regenerate replaces trailing turn; edit-and-rerun truncates; temporary leaves no DB trace.

Effort: ~2 days.

### M3 — Anonymous sessions + BYOK + usage rollup

Scope: `POST /api/auth/upgrade` (stub) + `signout`; BYOK PUT/DELETE with anonymous gating, AES-GCM with env-var KEK; per-request BYOK resolution in messages handler; `usage_rollup` increment on each `terminal`; verify spike (upgrade preserves conversation FKs).

Demo: non-anonymous saves BYOK, next turn uses it, meter increments. Anonymous → 403. Upgrade flow preserves history.

Effort: ~2-3 days (encryption plumbing is the slow part).

### M4 — Hardening (optional)

Scope: PRD-08 envelope on every path; structlog with request/user/turn keys + tokens/cost; tighten registry pricing; substitution emission for provider fallback; document remaining gaps.

Demo: forced provider error renders clean; forced fallback emits `provider_fallback`.

Effort: ~2 days.

## Post-M4: deferred hardening

All 10 items shipped via PR #75 (5-worker burst, one commit per concern):

- [x] **Versioned-KEK rotation seam** replacing the single-KEK BYOK path (`app/security/crypto.py`, `app/config.py`). KMS-ready: registry-keyed `MAGIC || version || nonce || ciphertext` format; v0 legacy bytes preserved. (Subsumes the original "KMS envelope encryption" and "Versioned-KEK lookup in `_CIPHER_CACHE`" items.)
- [x] `slowapi` rate limiting on `/messages` (`RATE_LIMIT_MESSAGES`, default 30/min) and `/auth/upgrade` (`RATE_LIMIT_UPGRADE`, default 5/min). Custom `RateLimitMiddleware` subclass works around slowapi's missing `_dynamic_route_limits` exemption (`app/middleware/ratelimit.py`).
- [x] OTel tracing + Sentry error reporting, both env-driven no-op (`app/observability/{tracing,errors}.py`, `app/logging_setup.py`). structlog injects `trace_id` / `span_id` when a span is active.
- [x] Partial UNIQUE INDEX on `users.email WHERE email IS NOT NULL` (`alembic/0004`); IntegrityError → `EMAIL_TAKEN` retry in `app/auth/routes.py`.
- [x] `responds_to_message_id` column on `message` for explicit reply pairing (`alembic/0005`); `_maybe_replay` reads the column first, pair-by-index as legacy fallback.
- [x] `ON CONFLICT (user_id, period_start) DO UPDATE` for `usage_rollup` increments, dialect-aware (`app/db/repositories/usage.py`).
- [x] argon2id password hashing (m=64 MiB, t=3, p=4) replacing bcrypt for new hashes; bcrypt verify-fallback + opportunistic rehash on login (`app/security/passwords.py`, `app/auth/routes.py`).
- [x] Cookie re-sign on `/auth/upgrade` even though the session id is unchanged — defensive against `SESSION_SECRET` rotation (`app/auth/routes.py::upgrade`).
- [x] LRU cache (`maxsize=256`) for per-user provider clients, keyed by `(api_key, base_url)` (`app/providers/anthropic.py`, and the DeepSeek/OpenAI-compatible client in `app/providers/openai.py`).

Residual notes (non-blocking, captured during PR #75 review):
- Migration `0004` doesn't pre-check for duplicate non-NULL emails — would surface as a generic IntegrityError on prod data with dupes. Today's prod has no upgraded users yet.
- `_maybe_replay` fallback is correct for uniform legacy conversations; a mixed conversation (some NULL pointers, some not) could in theory mispair under regen-on-non-trailing-user-messages, which today's UI doesn't expose.
- Rate-limit storage is in-process (single uvicorn worker). Multi-worker prod would need Redis.

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
| Rate limiting / cost budget enforcement (no `slowapi` at MVP) | PRD 04 §5.6; PRD 08 |
| Background job queue (no Celery/arq/Redis at MVP) | PRD 04 §5.10 |
| Audit log enforcement and admin tools | PRD 04 §5.8 (P1) |
| Sync engine / multi-device live updates | PRD 03 |
| Conversation share/export UI | PRD 01 §4.8 (no FE surface yet) |
| Substitution codes `auto_route`, `budget_cap`, `policy_route` | PRD 07 §5 (no FE rendering yet) |
| Pricing fields `cost_scope`, `multipliers.*`, `promo.*`, `notes` | PRD 07 §4.1 (no FE rendering yet) |
| Period-end ISO + platform/BYOK budget split on `UsageBudget` | PRD 07 §6.3 (FE shape is simpler today) |
| Server-curated `PromptSuggestion` set | PRD 01 §4.3 (mock is static client-side, fine) |
| Broader multi-provider routing/fallback (no LiteLLM at MVP) | PRD 02 (DeepSeek main + Anthropic alternate at v0) |
| OpenAPI -> FE codegen | (FE TS truth and BE Pydantic truth diverge by hand for now) |

## File / folder layout

`api/` is a sibling of `web/`, not inside it. Separate deploy, separate tooling — co-locating under `web/` would confuse the Next build. The FE finds it via `NEXT_PUBLIC_API_BASE_URL`.

```
api/
  pyproject.toml
  .python-version
  Dockerfile
  fly.toml                              # or render.yaml
  alembic.ini
  alembic/
    env.py
    versions/
  app/
    __init__.py
    main.py                             # FastAPI app + CORSMiddleware + lifespan + exception handlers
    config.py                           # pydantic-settings: env vars, dev vs prod, CORS origins, cookie flags
    deps.py                             # dependency providers: get_db, current_user
    db/
      __init__.py
      base.py                           # SQLAlchemy declarative base + naming convention
      session.py                        # async engine + AsyncSessionFactory
      models.py                         # ORM models
      repositories/
        conversations.py
        messages.py
        users.py
        votes.py
        api_keys.py
        usage.py
    schemas/                            # Pydantic v2 models, camelCase via alias_generator=to_camel
      common.py                         # CamelModel base, shared enums
      message.py                        # MessagePart union, ChatMessage, ModelAttribution, CostBreakdown
      conversation.py
      account.py
      preferences.py
      bootstrap.py                      # BootstrapResponse
      stream_events.py                  # SSE event payload models
    auth/
      cookies.py                        # itsdangerous signer wrapper
      dependency.py                     # current_user dependency
      routes.py                         # /api/auth/upgrade, /api/auth/signout
    providers/
      tiers.py                          # ModelTier registry (BE-owned, mirrors FE shape)
      openai.py                         # DeepSeek/OpenAI-compatible SDK wrapper + streaming adapter (main provider)
      anthropic.py                      # Anthropic SDK wrapper + streaming adapter (alternate backend)
      pricing.py                        # CostBreakdown + attribution computation; PRD 07 invariants enforced
    streaming/
      sse.py                            # event encoders, sse-starlette wiring helpers
      handler.py                        # stream-and-persist orchestration shared by send/regen/edit
    routes/
      bootstrap.py                      # GET /api/bootstrap
      conversations.py                  # CRUD + messages SSE
      feedback.py                       # POST /api/messages/:id/feedback
      preferences.py                    # PUT /api/preferences
      account.py                        # /api/account/byok PUT/DELETE
      auth.py                           # /api/auth/*
    errors.py                           # ErrorEnvelope, AppError, exception handlers
    logging_setup.py                    # structlog configuration
  tests/
    conftest.py                         # httpx.AsyncClient fixture, sqlite-or-pg fixture, respx fixture
    test_bootstrap.py
    test_conversations.py
    test_messages_stream.py             # uses respx to mock Anthropic SDK transport
    test_auth.py
    test_pricing.py
```

Conventions:
- Pydantic schemas are the wire-boundary truth; ORM models are the DB truth; repositories return schemas (not ORM rows) so handlers are trivial passthroughs and tests skip a DB to validate shapes.
- SSE encoder is one module; every event payload is a Pydantic model under `app/schemas/stream_events.py`.
- `app/config.py` uses `pydantic-settings`; env vars validated at boot — misconfigured CORS or cookie flags fail fast.
- The repo gains a top-level `api/`; `web/` is untouched beyond the `apiClient` + `next.config.ts` rewrite follow-ups.
