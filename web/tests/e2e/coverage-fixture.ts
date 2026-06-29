// E2E coverage collection fixture.
//
// This module is a drop-in replacement for `@playwright/test`: it re-exports the
// entire public surface (including `expect`, `devices`, and all types) and only
// overrides `test` with an instrumented variant. Every spec imports `test` from
// here, so each one contributes coverage with no per-spec code.
//
// When COVERAGE=1 the FE is served from an istanbul-instrumented `next --webpack`
// build (see next.config.ts) that maintains `window.__coverage__`. An automatic
// `context` fixture drains that object after every test and writes one JSON file
// per flush into web/coverage/.nyc_output/, which `pnpm coverage:report` merges.
//
// When COVERAGE is unset the fixture is a pure passthrough, so the normal
// `pnpm test:e2e` run is behaviourally identical to importing `@playwright/test`
// directly.

import crypto from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

import { test as base } from "@playwright/test";

const COVERAGE = process.env.COVERAGE === "1";

// tests/e2e/ -> web/coverage/.nyc_output
const NYC_OUTPUT_DIR = path.resolve(__dirname, "..", "..", "coverage", ".nyc_output");

const FLUSH_FN = "__flushPlaywrightCoverage__";

async function writeCoverage(json: string | undefined): Promise<void> {
  if (!json) return;
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(json) as Record<string, unknown>;
  } catch {
    return;
  }
  if (!data || Object.keys(data).length === 0) return;
  await fs.mkdir(NYC_OUTPUT_DIR, { recursive: true });
  const file = path.join(
    NYC_OUTPUT_DIR,
    `playwright_${crypto.randomBytes(16).toString("hex")}.json`,
  );
  await fs.writeFile(file, JSON.stringify(data), "utf8");
}

/* The `use` calls below are the Playwright fixture callback, not React's
   `use()` hook — opt this fixture file out of the React hooks lint rule. */
/* eslint-disable react-hooks/rules-of-hooks */
export const test = base.extend({
  context: async ({ context }, use) => {
    if (!COVERAGE) {
      await use(context);
      return;
    }

    // Flush on every navigation/teardown via beforeunload, plus an explicit
    // drain of any still-open pages after the test body finishes.
    await context.exposeFunction(FLUSH_FN, (json: string) => writeCoverage(json));
    await context.addInitScript((fnName: string) => {
      window.addEventListener("beforeunload", () => {
        const w = window as unknown as Record<string, unknown>;
        const flush = w[fnName] as ((c: string) => void) | undefined;
        flush?.(JSON.stringify(w.__coverage__ ?? {}));
      });
    }, FLUSH_FN);

    await use(context);

    for (const page of context.pages()) {
      await page
        .evaluate((fnName) => {
          const w = window as unknown as Record<string, unknown>;
          const flush = w[fnName] as ((c: string) => void) | undefined;
          flush?.(JSON.stringify(w.__coverage__ ?? {}));
        }, FLUSH_FN)
        .catch(() => {
          /* page already closed — beforeunload handled the flush */
        });
    }
  },
});

export * from "@playwright/test";
