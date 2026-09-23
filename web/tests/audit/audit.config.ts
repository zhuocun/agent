// Playwright config for the UI audit harness (`pnpm audit:ui`).
//
// Deliberately separate from `playwright.config.ts`: that config's testDir is
// `./tests/e2e`, so nothing here runs as part of `pnpm test:e2e`, and the
// `*.audit.ts` testMatch below means an accidental `playwright test tests/`
// with the default config still would not pick these files up.
//
// What differs from the e2e suite, and why:
// - The FE is a PRODUCTION build served by `next start`, not `next dev`. The
//   dev server lazily compiles heavy routes and renders its own Dev Tools
//   button into the page, which pollutes screenshots and the touch-target
//   probe (UI_STANDARDS.md UI-TOUCH-1 note). `pnpm audit:ui` builds first.
// - The build inlines NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 so the
//   browser talks to the BE directly, exactly like the e2e suite. Going through
//   the same-origin `/api/*` rewrite buffers the SSE body until the stream
//   closes (docs/design/audits/ISSUES.md "Harness caveats"), which would make
//   the mid-stream surface uncapturable.
// - The BE reuses the e2e env block (fake provider, fake search, tools,
//   agentic, fake billing) but points at its own ephemeral SQLite file under
//   web/test-results/audit/, so an audit run never touches the e2e database.
// - Output lands in web/test-results/audit/ (gitignored via web/.gitignore
//   `/test-results/`). `global-teardown.ts` aggregates the per-capture JSON
//   into probes.json + probes.md and fails the run if two distinct surfaces
//   produced byte-identical PNGs (a surface that never rendered).

import { chromium, defineConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { BE_ENV, BE_URL, FE_PORT, FE_URL } from "../e2e/shared-config";

const WEB_DIR = path.resolve(__dirname, "..", "..");
export const AUDIT_DIR = path.join(WEB_DIR, "test-results", "audit");
const AUDIT_DB = path.join(AUDIT_DIR, ".db", "audit.sqlite3");

// The sandbox preinstalls one Chromium under PLAYWRIGHT_BROWSERS_PATH and
// forbids `playwright install`; when that build is not the revision this
// Playwright version expects, launch it explicitly instead of failing.
// AUDIT_CHROMIUM_PATH overrides the lookup.
function resolveChromium(): string | undefined {
  if (process.env.AUDIT_CHROMIUM_PATH) return process.env.AUDIT_CHROMIUM_PATH;
  try {
    if (fs.existsSync(chromium.executablePath())) return undefined;
  } catch {
    /* fall through to the lookup */
  }
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root || !fs.existsSync(root)) return undefined;
  const candidates = fs
    .readdirSync(root)
    .filter((d) => /^chromium-\d+$/.test(d))
    .sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1]))
    .map((d) => path.join(root, d, "chrome-linux", "chrome"))
    .filter((p) => fs.existsSync(p));
  return candidates[0];
}
const CHROMIUM_PATH = resolveChromium();

export default defineConfig({
  testDir: __dirname,
  testMatch: /.*\.audit\.ts$/,
  // Each test walks one viewport × theme through ~40 surfaces with axe on
  // each; budget generously.
  timeout: 20 * 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  // The fake-provider BE is one uvicorn process over SQLite; more than a few
  // concurrent flows make streaming timing (and so mid-stream captures) flaky.
  workers: Number(process.env.AUDIT_WORKERS ?? 3),
  retries: 0,
  reporter: [["list"]],
  outputDir: path.join(AUDIT_DIR, ".pw-output"),
  globalSetup: path.join(__dirname, "global-setup.ts"),
  globalTeardown: path.join(__dirname, "global-teardown.ts"),
  use: {
    baseURL: FE_URL,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: "off",
    screenshot: "off",
    video: "off",
    // A production build registers a service worker; requests it serves are
    // invisible to page.route (used for the error-state and rich-markdown
    // fixtures), so block it.
    serviceWorkers: "block",
    launchOptions: CHROMIUM_PATH ? { executablePath: CHROMIUM_PATH } : {},
  },
  webServer: [
    {
      command:
        "uv run python -m app.scripts.init_test_db && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning",
      cwd: path.resolve(WEB_DIR, "..", "api"),
      url: `${BE_URL}/healthz`,
      reuseExistingServer: false,
      timeout: 90_000,
      env: {
        ...BE_ENV,
        DATABASE_URL: `sqlite+aiosqlite:///${AUDIT_DB}`,
      },
      stdout: "pipe",
      stderr: "pipe",
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
    {
      command: `pnpm exec next start -p ${FE_PORT}`,
      cwd: WEB_DIR,
      url: FE_URL,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { PORT: String(FE_PORT) },
      stdout: "pipe",
      stderr: "pipe",
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
  ],
});
