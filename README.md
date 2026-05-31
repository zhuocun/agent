# Monorepo

Two halves and a planning folder:

- `web/` — Next.js frontend. Renders the chat UI; in production it calls same-origin `/api/*`, which Next rewrites to the Fly backend.
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

Frontend defaults to `http://localhost:3000`; backend to `http://localhost:8000`.
Production uses `NEXT_PUBLIC_API_BASE_URL=""` so browser requests stay
same-origin and flow through the Next rewrite. For local/direct-backend testing,
set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `web/.env.local` and use
the backend CORS settings.

## Pointers

- `AGENTS.md` — deployment platform, DB, debugging via CLI, repo conventions. Read this first.
- `web/README.md` — frontend setup.
- `api/README.md` — backend setup, env, tests, deploy.
- `docs/plans/00-backend-minimal.md` — full backend plan and milestone breakdown.

## Status

M0–M4 + Post-M4 hardening have shipped on `main`. Test suite: **261 passed + 1 xfail** (the stop-path test; see `api/README.md`).

- FE: https://olune-agent-zhuocuns-projects.vercel.app (Vercel)
- BE: https://olune-agent-server.fly.dev (Fly.io, `nrt`)
- DB: Neon Postgres (`ap-southeast-1`)

Both halves auto-deploy on push to `main`. See `AGENTS.md` for the deploy model and operational details.
