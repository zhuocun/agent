// Shared helpers for the FE↔BE E2E suite.
//
// Re-exports the BE base URL from `shared-config.ts` (the FE base URL is the
// Playwright `baseURL` from `playwright.config.ts`, so tests pass relative
// paths to `page.goto`) and provides two small affordances:
//   - `waitForBootstrap(page)` waits for the FE's bootstrap useEffect to
//     resolve, gated on the composer becoming visible (the shell renders an
//     aria-hidden placeholder until then — see chat-thread.tsx ~L260-305).
//   - `sessionCookie(context)` reads the BE-origin session cookie, since the
//     `sid` cookie is set by :8000 (NOT :3000) — see brief §traps
//     "Cookie origin".

import { expect, type BrowserContext, type Page } from "@playwright/test";

import { BE_URL } from "./shared-config";

export { BE_URL };

/**
 * Wait for the FE shell to finish bootstrapping. The chat thread fetches
 * /api/bootstrap on mount and renders an aria-hidden div until the response
 * resolves — once the composer textarea is on screen, the shell is live and
 * the model-tier list (etc.) has been hydrated.
 */
export async function waitForBootstrap(page: Page): Promise<void> {
  await expect(page.getByTestId("composer-textarea")).toBeVisible({ timeout: 15_000 });
}

/**
 * Return the `sid` session cookie set by the BE on its own origin, or null
 * if the BE hasn't issued one yet. The FE talks to the BE with
 * `credentials: include`, so the cookie lands in the browser's cookie jar
 * scoped to `localhost:8000`.
 */
export async function sessionCookie(
  context: BrowserContext,
): Promise<{ name: string; value: string } | null> {
  const cookies = await context.cookies(BE_URL);
  const sid = cookies.find((c) => c.name === "sid");
  return sid ? { name: sid.name, value: sid.value } : null;
}
