# Deploying `olune-agent-server` to Fly.io

This backend runs as a persistent container (SSE streaming, background
title-autogen, a pooled async Postgres connection), which is why Fly.io — not a
serverless platform — is the deploy target. The image (`Dockerfile`) runs
`alembic upgrade head` then `uvicorn` on start, and `fly.toml` health-checks
`/healthz`.

All commands run from `api/`.

## Prerequisites

- A Fly.io account.
- `flyctl` installed: `curl -L https://fly.io/install.sh | sh`
- Logged in: `fly auth login`

## Steps

1. **Create the app** (`fly.toml` already names it `olune-agent-server`):

   ```sh
   fly apps create olune-agent-server
   ```

2. **Provision Postgres and attach it** (attach sets the `DATABASE_URL` secret):

   ```sh
   fly postgres create --name olune-agent-db --region iad --vm-size shared-cpu-1x --volume-size 1
   fly postgres attach olune-agent-db -a olune-agent-server
   ```

   Attach sets `DATABASE_URL=postgres://...`. The app normalizes `postgres://`
   and `postgresql://` to `postgresql+asyncpg://` automatically, so no manual
   URL surgery is needed.

3. **Set the remaining secrets.** `SESSION_SECRET` and `BYOK_ENCRYPTION_KEK`
   are generated inline so they never touch the repo or your shell history file:

   ```sh
   fly secrets set -a olune-agent-server \
     SESSION_SECRET="$(openssl rand -hex 32)" \
     BYOK_ENCRYPTION_KEK="$(openssl rand -base64 32)" \
     ANTHROPIC_API_KEY="sk-ant-..." \
     CORS_ALLOWED_ORIGINS="https://your-frontend-domain"
   ```

   - `ANTHROPIC_API_KEY` is **required** in production — the prod-safety gate
     (`assert_prod_safe()`) refuses to boot without it. Use your real key.
   - `CORS_ALLOWED_ORIGINS` must be your deployed frontend origin(s),
     comma-separated. A literal `*` is rejected in production (credentialed CORS).
   - `ENV=production`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, and `PORT`
     are already set in `fly.toml`.

4. **Deploy** (builds the image, runs migrations on start, serves uvicorn):

   ```sh
   fly deploy -a olune-agent-server
   ```

5. **Verify:**

   ```sh
   fly status -a olune-agent-server
   curl -i https://olune-agent-server.fly.dev/healthz   # expect HTTP 200
   ```

## Notes

- Migrations run automatically on container start (the `Dockerfile` `CMD`), so
  there is no separate release step.
- Point the frontend's API base URL at `https://olune-agent-server.fly.dev`.
- `auto_stop_machines` is on (`min_machines_running = 0`), so the first request
  after an idle period pays a cold start.
- `PROVIDER_BACKEND` defaults to `anthropic` in production; the `fake` provider
  is hard-refused there by the prod-safety gate.
