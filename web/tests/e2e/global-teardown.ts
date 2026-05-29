// Playwright globalTeardown — remove the per-PID ephemeral SQLite (+ sidecars).
//
// The file lives under `web/test-results/.playwright-db/`, which is
// gitignored. Failing to clean up isn't fatal — the next globalSetup sweeps
// any orphaned `test-*.sqlite3*` files matching the per-PID pattern. But
// tidying up keeps repeated local runs from leaving artifacts that show up
// in `ls`.

import { rmSync } from "node:fs";

import { DB_PATH } from "./shared-config";

export default async function globalTeardown(): Promise<void> {
  rmSync(DB_PATH, { force: true });
  rmSync(`${DB_PATH}-journal`, { force: true });
  rmSync(`${DB_PATH}-wal`, { force: true });
  rmSync(`${DB_PATH}-shm`, { force: true });
}
