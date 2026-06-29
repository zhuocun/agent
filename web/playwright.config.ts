// Playwright config for the FE↔BE integration suite.
//
// What this exercises that the in-process BE tests cannot:
// - real CORS preflight (FE :3000 → BE :8000, credentialed)
// - real cross-origin Set-Cookie + cookie-jar persistence in the browser
// - real SSE consumption via the browser's fetch + ReadableStream
// - real reload-survives-state on top of cookie + DB + bootstrap
//
// Boot model: two `webServer` entries (BE uvicorn + FE `next dev`) launched
// in parallel by Playwright. BE health-checks `/healthz`; FE health-checks
// the root `/` (we deliberately do NOT probe a page that itself calls the BE
// — see brief §critical-correctness-traps "Order of webServers").
//
// DB ephemerality: the BE webServer command resets a fresh SQLite schema under
// `test-results/.playwright-db/test.sqlite3` before uvicorn starts. The path
// lives under the gitignored test-results dir; `app.scripts.init_test_db`
// refuses non-test envs and avoids Alembic for this local E2E-only database.
//
// Isolation: Playwright's default is one fresh browser context per test, so
// every test starts as a brand-new anonymous user (no cookie → BE mints a
// fresh anon user + session row on the first bootstrap call). That naturally
// avoids cross-test interference even when workers run in parallel, because
// tests cannot read each other's rows (DB rows are scoped by `user_id`).
// We keep `workers` at the Playwright default (parallel locally, 1 in CI via
// `process.env.CI`).
//
// Chromium-only by design (see brief §Scope.1): keeps CI under 3 minutes.

import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

import { BE_ENV, BE_URL, FE_PORT, FE_URL } from "./tests/e2e/shared-config";

// Coverage mode (set by `pnpm test:e2e:coverage`). When on, the FE webServer is
// swapped to an istanbul-instrumented `next dev --webpack` build and COVERAGE=1
// is exported to the FE process only — the BE env (BE_ENV) is left untouched, so
// this stays FE-only E2E coverage. With COVERAGE unset the config is identical to
// the normal `pnpm test:e2e` run.
const COVERAGE = process.env.COVERAGE === "1";

export default defineConfig({
  testDir: "./tests/e2e",
  // Modest timeouts: the slowest spec is `streaming.spec.ts` (~3-4s for the
  // FakeProvider to emit ~6 deltas at 20ms each + UI propagation). 30s covers
  // boot warmups too.
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // CI: pin workers to 1 to avoid port contention with reused servers and
  // (paranoia) make trace artifacts easier to triage on failure. Locally,
  // default to the Playwright auto-detect (cpu/2).
  workers: process.env.CI ? 1 : undefined,
  // Quick local feedback on flakes; CI retries once.
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  outputDir: "./test-results/output",

  use: {
    baseURL: FE_URL,
    actionTimeout: 30_000,
    navigationTimeout: 30_000,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: [
    {
      // BE: uvicorn against the FastAPI app, pointed at the ephemeral SQLite
      // reset immediately before startup. `uv` is invoked from the api
      // directory so the venv resolves correctly.
      command:
        "uv run python -m app.scripts.init_test_db && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning",
      cwd: path.resolve(__dirname, "..", "api"),
      url: `${BE_URL}/healthz`,
      reuseExistingServer: false,
      timeout: 60_000,
      // Pass the test env explicitly. process.env stays available too (PATH
      // etc.) because Playwright merges `env` with the parent process env.
      env: { ...BE_ENV },
      stdout: "pipe",
      stderr: "pipe",
      // gracefulShutdown is a 1.60+ knob; SIGTERM lets uvicorn close its
      // listener and drain inflight requests within the grace window before
      // the SIGKILL fallback. 5s is plenty for uvicorn's single-process drain.
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
    {
      // FE: next dev. Probes the root `/` and DOES NOT trigger an API call
      // — the BE may still be warming up at this moment, so probing a page
      // that bootstraps would race. Under COVERAGE we must use the webpack
      // builder (`--webpack`) because the istanbul instrumentation lives in the
      // next.config.ts `webpack` hook, which Turbopack ignores.
      command: COVERAGE ? "pnpm exec next dev --webpack" : "pnpm dev",
      cwd: __dirname,
      url: FE_URL,
      reuseExistingServer: false,
      // Webpack + per-file istanbul instrumentation compiles slower than the
      // default Turbopack dev server, so give the coverage build more headroom.
      timeout: COVERAGE ? 240_000 : 120_000,
      env: {
        // NEXT_PUBLIC_* is inlined at module load by Next; make sure the dev
        // server picks up the same value the tests will assert against.
        NEXT_PUBLIC_API_BASE_URL: BE_URL,
        PORT: String(FE_PORT),
        // FE-only: turns on the next.config.ts istanbul webpack pass.
        ...(COVERAGE ? { COVERAGE: "1" } : {}),
      },
      stdout: "pipe",
      stderr: "pipe",
      // 5s graceful window: enough for `next dev`'s manager process to signal
      // its worker; falls back to SIGKILL if the tree is still draining.
      // Documented as tight — bump if Next's dev startup time grows.
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
  ],
});
