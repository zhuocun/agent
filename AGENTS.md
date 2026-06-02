# Agent operations brief

Operational source of truth for anyone (human or agent) shipping changes to this
repo. PRDs and design docs explain *what* and *why* — this explains *where it
lives*, *how to deploy it*, *how to debug it*. Read once before touching prod;
re-read when something breaks.

## What ships from this repo

| Surface | Source | Hosted on | Live URL |
| --- | --- | --- | --- |
| Web (FE) | `web/` | Vercel (project `olune-agent`, root dir `web/`) | https://olune-agent-zhuocuns-projects.vercel.app |
| API (BE) | `api/` | Fly.io (app `olune-agent-server`, region `nrt`) | https://olune-agent-server.fly.dev |
| DB | n/a | Neon Postgres (region `ap-southeast-1`) | private connection string |

Vercel apex alias `olune-agent.vercel.app` resolves to the same FE.

## Deploy model

**Auto-deploy on push to `main`.** Both halves go out from the same push.

- **FE**: Vercel GitHub integration — every push to `main` produces a production
  deploy. PR branches get preview deploys.
- **BE**: `.github/workflows/ci.yml` → `deploy-api` job. Runs only on
  `push: main`, after `api` + `web-e2e` jobs pass, using `flyctl deploy
  --remote-only`. Needs the `FLY_API_TOKEN` repo secret (Fly deploy-scoped
  token — `flyctl tokens create deploy -a olune-agent-server`).

No manual deploy is required for normal merges. The FE proxies `/api/*` through
Next.js to the BE (see `web/next.config.ts`) so the BE's `Set-Cookie` is
first-party against the Vercel origin — critical for iOS Safari ITP.

## Where secrets live

Never commit secrets. Each platform owns its own.

| Secret | Lives in | Used by |
| --- | --- | --- |
| `FLY_API_TOKEN` | GitHub repo secret (`Settings → Secrets and variables → Actions`) | `deploy-api` job |
| `DATABASE_URL` (Neon) | `flyctl secrets` on `olune-agent-server` | BE runtime |
| `SESSION_SECRET` | `flyctl secrets` | BE cookie signer |
| `BYOK_ENCRYPTION_KEK` (and `BYOK_KEK_VERSIONS` once rotation begins) | `flyctl secrets` | BE BYOK at-rest crypto |
| Provider key (`DEEPSEEK_API_KEY` for prod `PROVIDER_BACKEND=deepseek`; `OPENAI_API_KEY` is accepted as a DeepSeek fallback and is required only for `PROVIDER_BACKEND=openai`; `ANTHROPIC_API_KEY` only if you switch the backend) | `flyctl secrets` | BE provider |
| `SENTRY_DSN`, `OTEL_EXPORTER_OTLP_ENDPOINT` (optional) | `flyctl secrets` | BE observability |
| `NEXT_PUBLIC_API_BASE_URL` | Vercel env (set to empty for prod — same-origin via rewrite) | FE build |

To list current Fly secrets without revealing values:

```
flyctl secrets list -a olune-agent-server
```

## CLI cheat-sheet

Install once. Tokens come from the platform UIs.

### Fly (BE)

```
# install
curl -L https://fly.io/install.sh | sh

# auth
flyctl auth login                                # opens browser; on sandbox use a token instead
FLY_API_TOKEN=<token> flyctl ...

# status / logs / ssh
flyctl status -a olune-agent-server
flyctl logs   -a olune-agent-server              # tail
flyctl ssh console -a olune-agent-server         # shell on the running machine

# secrets
flyctl secrets list -a olune-agent-server
flyctl secrets set  KEY=value -a olune-agent-server         # immediate deploy
flyctl secrets set --stage KEY=value -a olune-agent-server  # queue, deploy later

# manual deploy (auto-deploy via CI is the default path)
cd api
flyctl deploy --remote-only                      # uses Fly's depot builder
flyctl deploy --local-only                       # builds locally; needs docker daemon

# rollback to a previous release
flyctl releases -a olune-agent-server
flyctl deploy --image registry.fly.io/olune-agent-server:deployment-<id> -a olune-agent-server
```

### Vercel (FE)

```
# install + auth
pnpm add -g vercel
vercel login

# link a working copy to the project (run once per checkout)
vercel link                                      # from repo root — the project's Root Directory is set to web/ in Vercel

# env
vercel env ls
vercel env add VAR_NAME production               # interactive

# deploys
vercel deploy                                    # preview
vercel deploy --prod                             # production (rare; merges are auto-deployed)
vercel promote <deployment-url>                  # promote a preview to prod
vercel logs <deployment-url>                     # build + runtime logs
```

### Neon (DB)

```
# install
pnpm add -g neonctl                              # or npm i -g neonctl

# auth — pick one
neonctl auth                                     # browser OAuth (won't work from headless sandbox)
NEON_API_KEY=<key> neonctl ...                   # API key from https://console.neon.tech/app/settings/api-keys

# inspect
neonctl projects list
neonctl branches list --project-id <id>
neonctl connection-string --project-id <id> --branch-name main --role-name neondb_owner

# psql against the prod DB — from your workstation. psql is NOT in the Fly
# image (python:3.11-slim), so this won't work inside `flyctl ssh console`.
# Get the URL from `neonctl connection-string` and never commit it.
psql "$DATABASE_URL"

# branches for migrations rehearsal
neonctl branches create --project-id <id> --name preview-migration
# point Fly at the branch's URL temporarily, run migrations, then point back
```

### GitHub (PRs / CI)

The MCP-restricted scope here is `zhuocun/agent`. `gh` CLI is not available in
the sandbox; use the GitHub MCP tools or `git push` + GitHub web.

```
# CI status for a commit
# Use the github MCP `pull_request_read` with method=get_check_runs.

# Re-run a failed workflow: GitHub UI → Actions → run → "Re-run jobs".
```

## Database

- **Engine**: Neon Postgres, serverless (scales to zero).
- **Driver**: SQLAlchemy 2.0 async + asyncpg. Connection string uses
  `postgresql+asyncpg://...?ssl=require` (asyncpg uses `ssl`, not `sslmode`).
- **Migrations**: Alembic under `api/alembic/versions/`. Head as of this writing
  is `0010_active_stream_unique`. The Dockerfile runs `uv run alembic upgrade
  head` before launching uvicorn, so each deploy brings the schema forward.
- **Tests** run on SQLite (`aiosqlite`) — `tests/conftest.py` builds the schema
  via `Base.metadata.create_all`, not Alembic, for speed. Use the SQLAlchemy
  `JSONB().with_variant(JSON(), "sqlite")` pattern when adding JSON columns.
- **Connecting from local dev to Neon prod**: not recommended. Point local at
  SQLite (`sqlite+aiosqlite:///./dev.sqlite3`) and let CI exercise the Postgres
  path. If you must, get the URL from `neonctl connection-string` and never
  commit it.

## Debugging in production

In order from cheapest to most invasive.

1. **Hit `/healthz`** — `curl https://olune-agent-server.fly.dev/healthz`.
   Cold start ~5–20 s (min_machines_running=0), warm ~0.5 s.
2. **Read Fly logs** — `flyctl logs -a olune-agent-server`. Structured JSON via
   structlog. Filter for the request id from the FE's response header
   `X-Request-ID`.
3. **Reproduce against the FE proxy** — `curl -i
   https://olune-agent-zhuocuns-projects.vercel.app/api/bootstrap`. Confirms
   the `vercel.app` → `fly.dev` rewrite is live (look for `via: fly.io` in
   response headers and a 1st-party `Set-Cookie`).
4. **Shell into the BE machine** — `flyctl ssh console -a olune-agent-server`
   for env/process inspection (`env | grep ...`, `ps`, file checks). The
   `python:3.11-slim` image has no `psql` client; for ad-hoc SQL run
   `psql "$DATABASE_URL"` from your workstation using a Neon
   connection-string from `neonctl connection-string`. (`flyctl ssh`
   requires a WireGuard peer; if the session 503's, run `flyctl ssh issue`
   first.)
5. **Sentry + OTel** — when wired (`SENTRY_DSN` / `OTEL_EXPORTER_OTLP_ENDPOINT`
   secrets set on Fly), exceptions go to Sentry and traces go to the OTel
   collector. Both no-op when unset.
6. **iOS Safari cookie issue?** — The FE *must* talk to itself, not directly to
   the BE. The Next.js rewrite (`web/next.config.ts`) is the load-bearing
   piece. Symptoms of breakage: `POST /api/conversations` returns 201, then
   `POST .../messages` 404 because each request mints a fresh anon user.

## Repo conventions

- **Branch names** for AI-authored work: `claude/<short-topic>` —
  `claude/burst-post-m4-hardening`, `claude/resolve-auto-tier-in-attribution`,
  `claude/fly-auto-deploy`.
- **Commits**: imperative subject, concise body explaining *why*, footer
  `https://claude.ai/code/session_01Hvw3QNjvo9XwVycsq7tFd8` per the precedent in
  the log. Never include AI model identifiers in commits, PR titles/bodies, or
  code comments.
- **PRs**: small, one concern each, squash-merge for clean main history.
  Multi-concern bursts are OK as one PR with logical commits if the changes
  share an integration story (see PR #75 — 5 commits, one per concern, one
  cleanup commit).
- **Open a PR before wrapping up**: a task isn't finished until its changes
  are up for review — don't leave finished work stranded on a pushed branch
  with no PR. Before declaring a task complete, check whether an open PR
  already covers the work (GitHub MCP `pull_request_read` /
  `list_pull_requests`); if there isn't one, create it (`create_pull_request`)
  off the working branch. One caveat when following up on a branch that
  already had a PR: first check whether that PR is already merged (`git cherry
  origin/main HEAD`, or `pull_request_read`). If it's merged, don't push onto
  the dead branch — branch off the latest `main` and open a fresh PR. (Still
  don't open one while the user has explicitly asked you to hold off, or for
  throwaway/experimental branches.)
- **Watch CI, then auto-merge on green**: after opening a PR, watch its CI
  (subscribe to PR activity, or poll checks via `pull_request_read`
  `get_check_runs`). Once all required checks pass, merge it automatically
  (squash). If CI goes red, diagnose and push a fix rather than leaving it
  stranded. The PR-activity subscription only wakes the session on CI
  *failures* and review comments — a green pass emits no wake event, so
  confirm success by polling `get_check_runs` rather than waiting to be
  notified. Note merging `main` triggers the FE + BE auto-deploy, so green
  CI is the gate.
- **Workflow file changes**: never skip CI hooks (`--no-verify`,
  `--no-gpg-sign`). If pre-commit fails, fix and create a new commit; don't
  amend.

## Architecture quick map

```
[ Next.js FE on Vercel (web/) ]
  /api/* rewrites server-side to:
[ FastAPI BE on Fly nrt (api/) ]
  ├── routes/ — bootstrap, conversations, auth, messages SSE, feedback, prefs, account
  ├── streaming/ — sse-starlette + DeepSeek/OpenAI-compatible provider wiring
  ├── auth/ — itsdangerous signed-cookie sessions, anonymous-first
  ├── providers/ — DeepSeek (main, via OpenAI-compatible binding) + Anthropic + fake; tier registry; pricing math
  ├── db/ — SQLAlchemy 2.0 async + repositories
  ├── observability/ — Sentry + OTel (both env-gated)
  ├── middleware/ — request_id, ratelimit (slowapi)
  ├── schemas/ — Pydantic v2 wire shapes (camelCase aliases)
  ├── scripts/ — one-off helpers (e.g., init_test_db for Playwright fixtures)
  └── security/ — AES-GCM BYOK + versioned KEK + argon2id passwords
        |
        v
[ Neon Postgres (ap-southeast-1) ]
```

- M0–M4 of `docs/plans/00-backend-minimal.md` shipped on `main`.
- Post-M4 hardening (10 items: versioned KEK, slowapi, OTel+Sentry,
  partial UNIQUE email, responds_to_message_id, ON CONFLICT usage,
  argon2id, cookie re-sign, provider client LRU) shipped via PR #75.

## When you need to ship something new

1. Branch off `main`, name it `claude/<topic>`.
2. Run `uv sync` in `api/` and `pnpm install` in `web/` if deps drift.
3. Make changes. Tests + types must stay green:
   - `cd api && uv run ruff check . && uv run mypy app && uv run pytest`
   - `cd web && pnpm test:e2e` (boots a full BE+FE locally; uses ephemeral
     SQLite; expects port 3000 + 8000 free).
4. Push branch, open PR via GitHub MCP `create_pull_request`.
5. After CI passes, merge to `main` (squash). Both halves auto-deploy.
6. Smoke-test prod: `curl /healthz`, hit `/api/bootstrap` through the FE
   proxy, confirm `Set-Cookie sid=...` is on the vercel.app origin.

If you make a change that requires a new Fly secret, set it *before* the deploy
fires (`flyctl secrets set --stage KEY=value`), otherwise the new machine boots
without it and may fail `assert_prod_safe()`.

## Cursor Cloud specific instructions

Monorepo quickstart is in the root `README.md`. Cloud VMs need **[uv](https://docs.astral.sh/uv/)** on `PATH` (`$HOME/.local/bin` after the install script); the API pins **Python 3.11** via `api/.python-version` (`requires-python = ">=3.11,<3.12"`).

### One-time per checkout (not in the VM update script)

- `cd api && cp .env.example .env` then `uv run alembic upgrade head` (SQLite at `api/dev.sqlite3`).
- `cd web && cp .env.example .env.local` and set `BE_ORIGIN=http://localhost:8000` when using the same-origin `/api/*` rewrite (leave `NEXT_PUBLIC_API_BASE_URL` empty).

### Starting dev servers

Use **tmux** so processes survive the session. Example session names: `api-dev-server`, `web-dev-server`.

| Service | Command | Port |
| --- | --- | --- |
| API | `cd api && uv run uvicorn app.main:app --reload --port 8000` | 8000 |
| Web | `cd web && pnpm dev` | 3000 |

Health: `curl http://localhost:8000/healthz`. Browser: `http://localhost:3000`.

### Lint / test / build

Standard commands are in `api/README.md` and `web/README.md`. Summary:

- API: `cd api && uv run ruff check . && uv run mypy app && uv run pytest`
- Web: `cd web && pnpm lint && pnpm build`
- E2E: `cd web && pnpm test:e2e` (starts BE+FE; ports **3000** and **8000** must be free; first run `pnpm test:e2e:install`)

### Provider keys and pytest

The API defaults to `PROVIDER_BACKEND=fake` in `.env.example`. If the VM has `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` set, bootstrap tier metadata and a few provider-routing tests expect **unavailable** DeepSeek/OpenAI routes and will fail. For CI-parity pytest, unset those variables:

`env -u DEEPSEEK_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_API_KEY uv run pytest`

With keys present, local chat can hit the real DeepSeek route instead of the fake provider.

### No separate DB or Docker

SQLite is embedded in the API process. Redis/Neon are optional and not required for local dev or Playwright.
