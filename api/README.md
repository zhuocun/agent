# api/

FastAPI service that backs the Next.js FE at `../web/`: bootstrap payload that
replaces every `MOCK_*` constant, conversation CRUD, a single SSE streaming
endpoint, message feedback, user preferences, BYOK key management, and an
anonymous-first session seam with an `/api/auth/upgrade` ceremony. Wire is
camelCase end-to-end. In production the browser calls same-origin `/api/*` on
Vercel and Next rewrites to this Fly service; direct cross-origin/CORS access is
for local, e2e, and diagnostic modes.

## Stack

FastAPI + SQLAlchemy 2.0 async + Postgres (Neon) + Alembic +
DeepSeek/OpenAI-compatible + Anthropic provider adapters + structlog + uv +
ruff + mypy + pytest.

## Local setup

Prereqs:
- Python 3.11 (matches `.python-version`).
- [uv](https://docs.astral.sh/uv/) installed.

Install deps:

```
uv sync
```

Copy the env template and edit:

```
cp .env.example .env
$EDITOR .env
```

Run migrations against whatever `DATABASE_URL` points at:

```
uv run alembic upgrade head
```

## Dev server

```
uv run uvicorn app.main:app --reload --port 8000
```

Verify with `http://localhost:8000/healthz`.

## Tests

```
uv run pytest
```

Tests use a per-test SQLite database — no Postgres needed. Current count:
**261 passed + 1 known xfail** (the stop-path test; ASGITransport doesn't expose
mid-stream disconnect to the server side, so we can't exercise that branch
end-to-end in-process).

## Lint and types

```
uv run ruff check .
uv run mypy app
```

Both must be clean before merging.

## Migrations

Create a new revision:

```
uv run alembic revision -m "add foo column"
```

Cross-dialect support: tests run on SQLite, prod runs on Postgres, so JSON
columns use the dialect-variant pattern:

```python
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JSONB().with_variant(JSON(), "sqlite")
```

The SQLite test path does **not** run Alembic. `tests/conftest.py` builds the
schema directly via `Base.metadata.create_all` — fast, isolated, and dodges any
Alembic-vs-SQLite quirks. Postgres migrations are exercised by hand and by
deploy.

## Provider modes

Provider route metadata lives in `app/providers/tiers.py`:
`PROVIDER_ROUTES` records the selectable backend id, runtime adapter status,
default-route eligibility, and route-level data policy shown in bootstrap
`modelTiers[*].dataPolicy`. `TIER_BINDINGS` records tier → model/pricing facts
for the active backend. A backend can be registered as `pending` without being
usable; runtime construction fails closed instead of silently substituting
DeepSeek.

`PROVIDER_BACKEND=fake` (default) — deterministic in-process provider; no API
key needed; what every test runs against. The fake route is dev/test only and
is rejected by `Settings.assert_prod_safe()` in production.

`PROVIDER_BACKEND=deepseek` — canonical production provider. DeepSeek speaks the
OpenAI-compatible API, so this uses the shared OpenAI-compatible adapter pointed
at `https://api.deepseek.com`. Requires `DEEPSEEK_API_KEY`; if unset,
`OPENAI_API_KEY` is accepted as a fallback. The canonical tier registry binds
auto/fast/smart to `deepseek-v4-flash` and pro to `deepseek-v4-pro`, with
thinking/reasoning intent and pricing in `app/providers/tiers.py`.

`PROVIDER_BACKEND=anthropic` — real Anthropic Python SDK; requires
`ANTHROPIC_API_KEY` as the platform key. Per-user BYOK keys override the
platform key per-request.

`PROVIDER_BACKEND=openai` — alternate OpenAI-compatible backend; requires
`OPENAI_API_KEY` as the platform key. `OPENAI_BASE_URL` is optional and defaults
to OpenAI's endpoint; override it for another OpenAI-compatible endpoint. This
backend uses the OpenAI tier binding table in `app/providers/tiers.py`, not the
DeepSeek production registry.

`PROVIDER_BACKEND=gemini` — registry placeholder only. The route is present so
docs/config can name the pending provider and its data-policy posture, but no
adapter exists. `build_provider()` and production startup reject it with
`MISCONFIGURED` / `RuntimeError` until a tested Gemini adapter and tier binding
table are added.

`Settings.assert_prod_safe()` runs at boot and rejects `PROVIDER_BACKEND=fake`
when `ENV=production`, rejects registered-but-unavailable routes such as Gemini,
and requires the matching API key for the selected backend, so a misconfigured
prod deploy fast-fails.

Switching provider routes:

```
# DeepSeek production route
PROVIDER_BACKEND=deepseek
DEEPSEEK_API_KEY=...

# Anthropic route
PROVIDER_BACKEND=anthropic
ANTHROPIC_API_KEY=...

# OpenAI or another OpenAI-compatible endpoint
PROVIDER_BACKEND=openai
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1  # optional; omit for SDK default
OPENAI_MODEL_FAST=gpt-4o-mini
OPENAI_MODEL_SMART=gpt-4o
OPENAI_MODEL_PRO=o1
OPENAI_MODEL_AUTO=gpt-4o
```

## BYOK

Per-user keys are AES-GCM-encrypted at rest and stored by provider id. For each
message, the backend resolves the served tier binding and looks up a key for
that binding's `provider_id` (`deepseek` in production, or `anthropic`/`openai`
on alternate backends). If found, the decrypted key is passed as a per-request
provider override and the turn is treated as BYOK. Anonymous users cannot store
BYOK keys.

The KEK (`BYOK_ENCRYPTION_KEK`) is a base64-encoded 32-byte key supplied via
env. The dev default is all-zeros and `assert_prod_safe()` refuses it in prod.
Generate a real key with:

```
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

### KEK rotation (versioned)

`BYOK_CURRENT_KEK_VERSION=0` (default) writes legacy single-KEK ciphertext —
bit-compatible with rows on disk. To rotate, set `BYOK_KEK_VERSIONS=1:<b64>` (or
`1:<b64>,2:<b64>` for staged rollouts) and bump `BYOK_CURRENT_KEK_VERSION=1`.
New writes go through the versioned format `MAGIC || version_byte || nonce ||
ciphertext` and old rows still decrypt via the legacy KEK path. See
`app/security/crypto.py` for the on-disk format.

## Passwords

argon2id (m=64 MiB, t=3, p=4) for new hashes; bcrypt verify-fallback for legacy
rows; opportunistic rehash to argon2id on successful bcrypt verify.
`app/security/passwords.py` is the single entry point.

## Rate limiting

slowapi limits on `POST /api/conversations/{id}/messages` (`RATE_LIMIT_MESSAGES`,
default `30/minute`) and `POST /api/auth/upgrade` (`RATE_LIMIT_UPGRADE`, default
`5/minute`). Per-IP, in-process storage (single-uvicorn-worker assumption — swap
to Redis when a multi-worker prod arrives). `app/middleware/ratelimit.py`
exposes the `limiter` singleton.

## Stream State

`STREAM_STATE_BACKEND=memory` is the default: resumable replay buffers and live
stop flags are process-local. `STREAM_STATE_BACKEND=redis` uses `REDIS_URL` for
cross-worker replay and stop coordination; startup pings Redis and fails fast if
the URL is missing or unreachable.

Redis replay keys use the stream reaper window while live, refresh on every
append, then expire after `RESUMABLE_BUFFER_TTL_SECONDS` once terminal. Replay
content is bounded by `RESUMABLE_BUFFER_MAX_EVENTS` and
`RESUMABLE_BUFFER_MAX_BYTES` (oldest events drop first). Redis stop flags use
`STREAM_STOP_TTL_SECONDS` so leaked live-stop keys self-clear.

## Observability

OTel auto-instrumentation (FastAPI + SQLAlchemy) when
`OTEL_EXPORTER_OTLP_ENDPOINT` is set; Sentry error reporting when `SENTRY_DSN`
is set; both no-op when unset. structlog injects `trace_id` / `span_id` into log
events when a span is active. `app/observability/{tracing,errors}.py`.

## Auth

Anonymous-first signed-cookie sessions. `itsdangerous` signs the `sid` cookie;
the cookie carries a session id (not a user id), and the session row references
the user. Sessions live 30 days.

`POST /api/auth/upgrade` promotes the current anonymous user to email/password
**in place** — the user row id does not change, so every FK on `conversation`,
`api_key`, `preferences`, etc. stays valid without a data migration. This is
the whole reason the anonymous-first seam is shaped this way.

## Routing, CORS, and cookies

Production browser traffic should stay same-origin: the FE calls `/api/*` with
`NEXT_PUBLIC_API_BASE_URL=""`, and `web/next.config.ts` rewrites those requests
server-side to Fly. This makes the BE `Set-Cookie` first-party on the Vercel
origin, which is important for iOS Safari.

Direct cross-origin access still exists for local/e2e/diagnostic modes and is
driven by `CORS_ALLOWED_ORIGINS` (comma-separated origin list). The middleware
echoes the request `Origin` against the allow-list — never `*` with credentials.

Cookies:
- Dev: `SameSite=Lax`, `Secure=false` (so localhost works without HTTPS).
- Prod: `SameSite=None; Secure` from the BE. In the normal Vercel rewrite path,
  that cookie is received as first-party on the FE origin.

Controlled by `COOKIE_SECURE` + `COOKIE_SAMESITE`.

## Streaming

`POST /api/conversations/:id/messages` returns `text/event-stream`. Event names
are snake_case (`reasoning`, `text`, `status`, `terminal`); event payloads are
camelCase JSON.

Stop is disconnect-driven: when the client closes the connection, the server
finalizes the partial assistant turn with `costConfidence="estimate"` so the
saved cost is marked as imprecise.

## Deploy

`fly.toml` is configured for Fly.io (app `olune-agent-server`, region `nrt`).
The `Dockerfile` runs `uv run alembic upgrade head` before launching uvicorn,
so each deploy brings the schema forward. Fly's health check hits `/healthz`.

**Auto-deploy**: `.github/workflows/ci.yml` → `deploy-api` job fires
`flyctl deploy --remote-only` on every push to `main`, after `api` + `web-e2e`
jobs pass. Requires the `FLY_API_TOKEN` repo secret.

For one-off manual deploys: `cd api && flyctl deploy --remote-only`. See
`../AGENTS.md` for the full Fly CLI cheat-sheet (logs, ssh, secrets,
rollback).

## Endpoints summary

- `GET /api/bootstrap` — account + conversations + preferences + tiers in one
  call; replaces every `MOCK_*` constant on the FE.
- `GET/POST /api/conversations` — list and create.
- `GET/PATCH/DELETE /api/conversations/:id` — read, rename/pin, delete.
- `POST /api/conversations/:id/share` — mint or return a public share link.
- `DELETE /api/conversations/:id/share` — revoke a public share link.
- `POST /api/conversations/:id/messages` — SSE stream + persist.
- `GET /api/conversations/:id/stream/:stream_id` — same-device stream replay
  when `RESUMABLE_STREAMS_ENABLED=true`.
- `POST /api/conversations/:id/stop` — best-effort server-side stop for an
  active stream.
- `GET /api/share/:token` — unauthenticated cost-stripped public share read.
- `POST /api/messages/:id/feedback` — thumbs up/down + optional reason.
- `PUT /api/preferences` — write user preferences, including optional
  `retentionDays` (`null`, `30`, or `90`).
- `PUT /api/account/byok` — set or replace the per-user key for the provider in the request body.
- `DELETE /api/account/byok/:provider` — clear the per-user key for a provider.
- `POST /api/auth/upgrade` — promote anonymous → email/password.
- `POST /api/auth/login` — sign in to an existing email/password account.
- `POST /api/auth/signout` — clear cookie, revoke session row.
- `GET /api/account/export` — export account metadata, preferences, BYOK
  metadata (masked only), usage rollups, conversations/messages with private
  attribution/cost, and the caller's audit events as JSON.
- `DELETE /api/account` — permanently delete the caller's account and data.
  Body must include `confirmation`: the account email for registered users, or
  `"DELETE"` for anonymous users. The active session cookie is cleared on
  success.

## Pointers

- `../docs/plans/00-backend-minimal.md` — full spec, milestones M0–M4, and the
  "Post-M4: deferred hardening" section for everything intentionally left out.
