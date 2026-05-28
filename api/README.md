# api/

FastAPI service that backs the Next.js FE at `../web/`. The FE expects a real BE
on a different origin: bootstrap payload that replaces every `MOCK_*` constant,
conversation CRUD, a single SSE streaming endpoint, message feedback, user
preferences, BYOK key management, and an anonymous-first session seam with an
`/api/auth/upgrade` ceremony. Wire is camelCase end-to-end; cookies are
credentialed cross-origin.

## Stack

FastAPI + SQLAlchemy 2.0 async + Postgres (Neon) + Alembic + Anthropic Python
SDK + structlog + uv + ruff + mypy + pytest.

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
**121 passed + 1 known xfail** (the stop-path test; ASGITransport doesn't expose
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

`PROVIDER_BACKEND=fake` (default) — deterministic in-process provider; no API
key needed; what every test runs against.

`PROVIDER_BACKEND=anthropic` — real Anthropic Python SDK; requires
`ANTHROPIC_API_KEY` as the platform key. Per-user BYOK keys override the
platform key per-request.

`Settings.assert_prod_safe()` runs at boot and rejects `PROVIDER_BACKEND=fake`
when `ENV=production`, so a misconfigured prod deploy fast-fails.

## BYOK

Per-user Anthropic keys are AES-GCM-encrypted at rest. The KEK
(`BYOK_ENCRYPTION_KEK`) is a base64-encoded 32-byte key supplied via env. The
dev default is all-zeros and `assert_prod_safe()` refuses it in prod. Generate
a real key with:

```
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

Rotate by re-encrypting rows under a new KEK; versioned-KEK lookup is on the
post-M4 list.

## Auth

Anonymous-first signed-cookie sessions. `itsdangerous` signs the `sid` cookie;
the cookie carries a session id (not a user id), and the session row references
the user. Sessions live 30 days.

`POST /api/auth/upgrade` promotes the current anonymous user to email/password
**in place** — the user row id does not change, so every FK on `conversation`,
`api_key`, `preferences`, etc. stays valid without a data migration. This is
the whole reason the anonymous-first seam is shaped this way.

## CORS

Driven by `CORS_ALLOWED_ORIGINS` (comma-separated origin list). The middleware
echoes the request `Origin` against the allow-list — never `*` with
credentials.

Cookies:
- Dev: `SameSite=Lax`, `Secure=false` (so localhost works without HTTPS).
- Prod: `SameSite=None; Secure` (cross-origin BE on its own host).

Controlled by `COOKIE_SECURE` + `COOKIE_SAMESITE`.

## Streaming

`POST /api/conversations/:id/messages` returns `text/event-stream`. Event names
are snake_case (`reasoning`, `text`, `status`, `terminal`); event payloads are
camelCase JSON.

Stop is disconnect-driven: when the client closes the connection, the server
finalizes the partial assistant turn with `costConfidence="estimate"` so the
saved cost is marked as imprecise.

## Deploy

`fly.toml` is configured for Fly.io. The `Dockerfile` runs
`uv run alembic upgrade head` before launching uvicorn, so each deploy
brings the schema forward. Fly's health check hits `/healthz`.

## Endpoints summary

- `GET /api/bootstrap` — account + conversations + preferences + tiers in one
  call; replaces every `MOCK_*` constant on the FE.
- `GET/POST /api/conversations` — list and create.
- `GET/PATCH/DELETE /api/conversations/:id` — read, rename/pin, delete.
- `POST /api/conversations/:id/messages` — SSE stream + persist.
- `POST /api/messages/:id/feedback` — thumbs up/down + optional reason.
- `PUT /api/preferences` — write user preferences.
- `PUT /api/account/byok` — set the per-user Anthropic key.
- `DELETE /api/account/byok` — clear it.
- `POST /api/auth/upgrade` — promote anonymous → email/password.
- `POST /api/auth/signout` — clear cookie, revoke session row.

## Pointers

- `../docs/plans/00-backend-minimal.md` — full spec, milestones M0–M4, and the
  "Post-M4: deferred hardening" section for everything intentionally left out.
