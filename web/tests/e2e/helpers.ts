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

import { expect, type BrowserContext, type Locator, type Page } from "@playwright/test";

import { BE_URL } from "./shared-config";

export { BE_URL };

/**
 * Cold-render a conversation: reload the shell, then open the conversation from
 * the sidebar so the thread renders purely from persisted parts. Every reload
 * site in the suite repeats this, so the parity assertions share one path.
 */
export async function reloadIntoConversation(
  page: Page,
  conversationId: string,
): Promise<void> {
  await page.reload();
  await waitForBootstrap(page);
  const row = page.locator(`[data-conversation-id="${conversationId}"]`);
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.getByTestId("sidebar-conversation-link").click();
}

/**
 * The contract surfaces where a live-streamed agentic turn and the same turn
 * re-derived from persisted parts can diverge (FE audit's live-vs-reload table):
 * the run-cost meter (value + honesty attributes), the partial-synthesis chip
 * copy, the per-row (label, role, outcome) tuples, the resolved citation ids,
 * and the reasoning duration clause.
 *
 * `reasoningDuration` is opt-in because the backend does not persist
 * `durationSec` yet (FL-37): including it unconditionally would assert a field
 * only the live path can produce. Flip it on once the persist lands.
 */
export interface AgenticTurnSnapshot {
  meter: {
    text: string;
    confidence: string | null;
    phase: string | null;
    ariaLabel: string | null;
  } | null;
  partialChip: string | null;
  rows: Array<{
    subagentId: string | null;
    label: string;
    role: string;
    outcome: string;
  }>;
  citationIds: number[];
  answer: string;
  reasoningDuration?: string | null;
}

/**
 * Snapshot one agentic assistant turn's contract surfaces for reload parity.
 *
 * `scope` is the assistant-message locator (private thread) or the
 * public-assistant-message locator (share view). Take one snapshot live and one
 * after a cold render, then compare them with `toEqual` — anything the two
 * render paths disagree about shows up as a diff instead of passing because
 * both sides merely rendered *something*.
 */
export async function snapshotAgenticTurn(
  scope: Locator,
  options: { reasoningDuration?: boolean } = {},
): Promise<AgenticTurnSnapshot> {
  const meterLocator = scope.getByTestId("run-cost-meter").first();
  const meter =
    (await scope.getByTestId("run-cost-meter").count()) > 0
      ? {
          text: ((await meterLocator.textContent()) ?? "").trim(),
          confidence: await meterLocator.getAttribute("data-confidence"),
          phase: await meterLocator.getAttribute("data-phase"),
          ariaLabel: await meterLocator.getAttribute("aria-label"),
        }
      : null;

  const chip = scope.getByTestId("partial-synthesis-warning");
  const partialChip =
    (await chip.count()) > 0
      ? ((await chip.first().textContent()) ?? "").trim()
      : null;

  const rows = await scope.getByTestId("subagent-row").evaluateAll((els) =>
    els.map((el) => {
      const icon = el.querySelector("[data-testid^='subagent-outcome-']");
      const testid = icon?.getAttribute("data-testid") ?? null;
      return {
        subagentId: el.getAttribute("data-subagent-id"),
        label:
          el
            .querySelector("[data-testid='subagent-label']")
            ?.textContent?.trim() ?? "",
        role:
          el
            .querySelector("[data-testid='subagent-role-badge']")
            ?.textContent?.trim() ?? "",
        // No settled icon means the row is still spinning — a live-only state
        // that must never survive into a committed or reloaded turn.
        outcome: testid ? testid.replace("subagent-outcome-", "") : "running",
      };
    }),
  );

  const citationIds = (
    await scope
      .getByTestId("citation-marker")
      .evaluateAll((els) =>
        els.map((el) => Number(el.getAttribute("data-citation-id"))),
      )
  ).filter((id) => Number.isFinite(id));

  const answerLocator = scope
    .locator('[data-testid="assistant-answer"], [data-testid="public-assistant-answer"]')
    .first();
  const answer =
    (await answerLocator.count()) > 0
      ? ((await answerLocator.textContent()) ?? "").trim()
      : "";

  const snapshot: AgenticTurnSnapshot = {
    meter,
    partialChip,
    rows,
    citationIds,
    answer,
  };
  if (options.reasoningDuration) {
    const panel = scope.getByTestId("reasoning-panel").first();
    const text =
      (await scope.getByTestId("reasoning-panel").count()) > 0
        ? ((await panel.textContent()) ?? "")
        : "";
    const match = /Thought for [^\n]+/.exec(text);
    snapshot.reasoningDuration = match ? match[0] : null;
  }
  return snapshot;
}

/** Desktop + mobile each render a model-mode trigger; only one is visible. */
export function modelModeTrigger(page: Page | { locator: Page["locator"] }): Locator {
  return page.locator('[data-testid="model-mode-trigger"]:visible');
}

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
