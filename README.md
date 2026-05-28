# Monorepo

Two halves and a planning folder:

- `web/` — Next.js frontend. Renders the chat UI; talks to the backend over CORS with credentials.
- `api/` — FastAPI backend. Bootstrap payload, conversation CRUD, SSE streaming, BYOK, anonymous-first sessions.
- `docs/` — PRDs in `docs/prd/`, build plans in `docs/plans/`, research notes in `docs/research/`.

## Quickstart

Backend (terminal 1):

```
cd api
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Frontend (terminal 2):

```
cd web
pnpm install
pnpm dev
```

Frontend defaults to `http://localhost:3000`; backend to `http://localhost:8000`. Point the FE at the BE via `NEXT_PUBLIC_API_BASE_URL` in `web/.env.local`.

## Pointers

- `web/README.md` — frontend setup.
- `api/README.md` — backend setup, env, tests, deploy.
- `docs/plans/00-backend-minimal.md` — full backend plan and milestone breakdown.

## Status

M0–M4 of the backend plan have shipped on branch `claude/eloquent-thompson-rxdE6`. The test suite is **121 passed + 1 xfail** (the stop-path test; see the api README). Items intentionally deferred live in the [Post-M4: deferred hardening](docs/plans/00-backend-minimal.md#post-m4-deferred-hardening) section of the plan.
