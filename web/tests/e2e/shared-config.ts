// Shared config for the FE↔BE E2E suite.
//
// Single source of truth for ports, URLs, the ephemeral SQLite path, and the BE
// env block.
//
// DB path rationale: Playwright starts webServer processes before tests run, so
// DB setup must happen in the API webServer command itself. Use a fixed file
// under gitignored test-results and always launch fresh web servers (see
// playwright.config.ts) so the API process and DB file stay coupled.

import path from "node:path";

export const FE_PORT = Number(process.env.FE_PORT ?? 3000);
export const BE_PORT = Number(process.env.BE_PORT ?? 8000);
export const FE_URL = `http://localhost:${FE_PORT}`;
export const BE_URL = `http://localhost:${BE_PORT}`;

// Resolved against the repo `web/` dir so the file lands under
// web/test-results/.playwright-db/ regardless of where the playwright command
// is invoked from. `__dirname` here is `web/tests/e2e/`, so `../..` is `web/`.
const WEB_DIR = path.resolve(__dirname, "..", "..");
export const DB_DIR = path.join(WEB_DIR, "test-results", ".playwright-db");
// Stable filename for one E2E invocation. The API webServer command resets it
// before uvicorn starts.
export const DB_PATH = path.join(DB_DIR, "test.sqlite3");
// SQLAlchemy sqlite+aiosqlite URL — note the FOUR slashes for an absolute path.
export const DATABASE_URL = `sqlite+aiosqlite:///${DB_PATH}`;

// Env that both init_test_db and the BE webServer must see. Centralized here so
// the two stay in lock-step.
export const BE_ENV = {
  ENV: "test",
  PROVIDER_BACKEND: "fake",
  // Enable web search against the deterministic FakeSearchProvider so the
  // capability lights up (supportsWebSearch=true) and the fake provider emits
  // the status/sources frames the web-search e2e asserts. Mirrors the
  // SEARCH_BACKEND=fake set in api/tests/conftest.py for the pytest suite.
  SEARCH_BACKEND: "fake",
  // Enable tools so the HITL tool-approval e2e (tool-approval.spec.ts) can
  // drive the fake provider's tool markers (TOOL_APPROVE / TOOL_TIME). The fake
  // provider only emits tool calls on those markers, so this is a no-op for
  // every other test — no stray tool parts without a marker.
  TOOLS_ENABLED: "true",
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
