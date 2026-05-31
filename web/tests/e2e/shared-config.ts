// Shared config for the FE↔BE E2E suite.
//
// Single source of truth for ports, URLs, the per-process ephemeral SQLite
// path, and the BE env block. Imported from both `playwright.config.ts` and
// `tests/e2e/global-setup.ts` so the two stay in lock-step.
//
// Why per-PID DB path: `playwright.config.ts` sets `reuseExistingServer: true`
// on the local dev path so a developer can re-run `pnpm test:e2e` without
// waiting for the BE to boot each time. The risk is that globalSetup
// unconditionally recreates the SQLite file BEFORE Playwright decides whether
// to reuse the running BE — a reused BE would then hold open aiosqlite
// connections + cached sqlalchemy state pointing at the recreated empty file,
// surfacing as "no such table" errors. Minting a fresh per-PID file sidesteps
// that hazard entirely (a new Playwright invocation gets a new PID → new file
// → the reused BE's URL no longer matches what globalSetup just touched, so a
// fresh `pnpm test:e2e` always restarts the BE if the DB path changed).

import path from "node:path";

export const FE_PORT = 3000;
export const BE_PORT = 8000;
export const FE_URL = `http://localhost:${FE_PORT}`;
export const BE_URL = `http://localhost:${BE_PORT}`;

// Resolved against the repo `web/` dir so the file lands under
// web/test-results/.playwright-db/ regardless of where the playwright command
// is invoked from. `__dirname` here is `web/tests/e2e/`, so `../..` is `web/`.
const WEB_DIR = path.resolve(__dirname, "..", "..");
export const DB_DIR = path.join(WEB_DIR, "test-results", ".playwright-db");
// Per-PID filename: defeats the reuseExistingServer-vs-stale-DB-handle hazard
// described in the file header. Each fresh `pnpm test:e2e` invocation gets a
// fresh DB; globalTeardown removes the file by name. Stale orphans (from
// Ctrl-C exits) accumulate as `test-<pid>.sqlite3*` and are swept on the next
// globalSetup via a glob (see global-setup.ts).
export const DB_PATH = path.join(DB_DIR, `test-${process.pid}.sqlite3`);
// SQLAlchemy sqlite+aiosqlite URL — note the FOUR slashes for an absolute path.
export const DATABASE_URL = `sqlite+aiosqlite:///${DB_PATH}`;

// Env that BOTH globalSetup (init_test_db) and the BE webServer must see.
// Centralized here so the two stay in lock-step.
export const BE_ENV = {
  ENV: "test",
  PROVIDER_BACKEND: "fake",
  // Enable web search against the deterministic FakeSearchProvider so the
  // capability lights up (supportsWebSearch=true) and the fake provider emits
  // the status/sources frames the web-search e2e asserts. Mirrors the
  // SEARCH_BACKEND=fake set in api/tests/conftest.py for the pytest suite.
  SEARCH_BACKEND: "fake",
  DATABASE_URL,
  CORS_ALLOWED_ORIGINS: FE_URL,
  // Long-and-fixed; assert_prod_safe() requires >=32 chars in prod, dev/test
  // accepts anything but we use a deterministic value so a flaky test cannot
  // be blamed on cookie-signature drift.
  SESSION_SECRET: "playwright-e2e-session-secret-fixed-and-long-enough",
  COOKIE_SECURE: "false",
  COOKIE_SAMESITE: "lax",
  // All-zeros dev KEK; assert_prod_safe() rejects it when ENV=production but
  // is happy with ENV=test. See api/app/config.py.
  BYOK_ENCRYPTION_KEK: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
} as const;
