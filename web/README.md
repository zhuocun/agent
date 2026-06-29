Next.js frontend for Olune Agent.

## Getting Started

Install dependencies, then run the development server:

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## API Routing

Production should keep `NEXT_PUBLIC_API_BASE_URL` set to an empty string. The
browser then calls same-origin `/api/*`, and `next.config.ts` rewrites those
requests server-side to the Fly backend. This keeps session cookies first-party
on the Vercel origin.

For local development, choose one of these modes:

- Same-origin proxy: leave `NEXT_PUBLIC_API_BASE_URL` empty and set
  `BE_ORIGIN=http://localhost:8000` so the Next rewrite points at local FastAPI.
- Direct CORS: set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` so browser
  requests go straight to the FastAPI dev server. The e2e setup may use this to
  exercise the backend CORS path.

See `.env.example` for the environment variable examples.

## Build

```bash
pnpm build
```

## Tests

End-to-end Playwright suite under `web/tests/e2e/`. Boots the real FastAPI BE
(uvicorn, `PROVIDER_BACKEND=fake`) and the real Next.js dev server together,
then drives Chromium against the FE on `http://localhost:3000` while the BE
runs on `http://localhost:8000`.

Prereqs (first run only):

- Python 3.11 + [uv](https://docs.astral.sh/uv/) on PATH so the `webServer`
  config can launch uvicorn from `../api/`.
- One-time browser install:

  ```bash
  pnpm test:e2e:install
  ```

Run the suite:

```bash
pnpm test:e2e          # headless
pnpm test:e2e:ui       # interactive runner
```

The BE uses an ephemeral SQLite at `test-results/.playwright-db/test.sqlite3`
for tests — your `api/dev.sqlite3` is never touched. The API webServer command
resets the schema via `python -m app.scripts.init_test_db` before uvicorn
starts.

### Coverage

FE coverage is collected through the same Playwright suite. When `COVERAGE=1`,
`next.config.ts` adds a `babel-plugin-istanbul` webpack pass (so the run uses
`next dev --webpack`, not Turbopack) and the `coverage-fixture.ts` drains
`window.__coverage__` after every test into `coverage/.nyc_output/`.

```bash
pnpm test:e2e:coverage   # COVERAGE=1 run of every spec, then writes coverage/
pnpm coverage:report     # merge → text/lcov/html/json-summary, then enforce floor
```

`coverage:report` ends in `nyc check-coverage`, so it exits non-zero if any
metric drops below the floor in `.nycrc.json` (statements 73, lines 77,
functions 75, branches 64 — set ~3 pts under the suite's achieved numbers to
absorb run-to-run noise). The config excludes `src/app/**` (RSC server
entries the browser collector can't see) so the gate scores only
browser-reachable code. Artifacts land in `web/coverage/` (`lcov.info`,
`coverage-summary.json`, `index.html`). CI runs this in the `web-coverage` job
and uploads the lcov report.

## Deploy

Production deploys are handled by the Vercel GitHub integration for this repo,
with `web/` as the project root. Keep `NEXT_PUBLIC_API_BASE_URL` empty in the
production environment so the `/api/*` rewrite remains the browser-facing path.
