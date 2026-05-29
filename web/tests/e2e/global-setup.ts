// Playwright globalSetup — mints a fresh SQLite for the BE webServer.
//
// Strategy chosen (per brief §5 option-B): a clearly-namespaced sqlite file at
// `web/test-results/.playwright-db/test-<pid>.sqlite3`. We
//   (1) sweep any orphaned `test-*.sqlite3*` files from prior crashed runs,
//   (2) ensure the dir exists,
//   (3) materialize the schema via `app.scripts.init_test_db` so the BE can
//       boot without Alembic (production startup is untouched).
//
// Per-PID rationale: see shared-config.ts. The webServer config below points
// DATABASE_URL at the same file via the shared `BE_ENV`, so by the time
// Playwright launches uvicorn the DB has its tables. `init_test_db` refuses
// to run when ENV=production, so a misconfigured CI environment can't
// accidentally drop a real DB.

import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, rmSync } from "node:fs";
import path from "node:path";

import { BE_ENV, DB_DIR, DB_PATH } from "./shared-config";

const API_DIR = path.resolve(__dirname, "..", "..", "..", "api");

// Sweep any orphaned per-PID SQLite files left behind by crashed/Ctrl-C'd
// runs. Only ever touches files under `.playwright-db/` matching the
// `test-<pid>.sqlite3` pattern (incl. -journal/-wal/-shm sidecars), so we
// cannot stomp on dev DBs at `api/dev.sqlite3` or anything else.
function sweepOrphans(): void {
  let entries: string[];
  try {
    entries = readdirSync(DB_DIR);
  } catch {
    // Dir doesn't exist yet — nothing to sweep.
    return;
  }
  for (const name of entries) {
    if (!/^test-\d+\.sqlite3(-journal|-wal|-shm)?$/.test(name)) continue;
    rmSync(path.join(DB_DIR, name), { force: true });
  }
}

export default async function globalSetup(): Promise<void> {
  mkdirSync(DB_DIR, { recursive: true });
  sweepOrphans();
  // Belt-and-braces remove of our own per-PID file (in case a previous run
  // with the same PID survived sweep — extremely unlikely, but harmless).
  rmSync(DB_PATH, { force: true });
  rmSync(`${DB_PATH}-journal`, { force: true });
  rmSync(`${DB_PATH}-wal`, { force: true });
  rmSync(`${DB_PATH}-shm`, { force: true });

  // Inherit the parent env so PATH (and uv discovery) carry through, then
  // override the BE-shaped vars from the shared module so init_test_db reads
  // the right URL and assert_prod_safe() is satisfied. The same `BE_ENV` is
  // passed to the BE webServer in playwright.config.ts.
  const env = {
    ...process.env,
    ...BE_ENV,
  };

  // Synchronous invocation: globalSetup must finish before any webServer
  // launches, and the script is fast (<1s). `uv` resolves the api venv.
  // Throws on non-zero exit, which fails the entire test run with the
  // stderr surfaced — exactly what we want for a setup failure.
  execFileSync("uv", ["run", "python", "-m", "app.scripts.init_test_db"], {
    cwd: API_DIR,
    env,
    stdio: "inherit",
  });
}
