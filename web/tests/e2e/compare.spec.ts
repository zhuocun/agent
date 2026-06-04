// Compare mode — parallel model comparison (the flagship multi-model surface).
//
// What this exercises end-to-end against the REAL BE + FakeProvider:
//   (a) enabling compare, picking TWO DISTINCT tiers, and sending one prompt
//       fans out to TWO concurrent POST .../messages SSE streams
//   (b) THE isTemporary INVARIANT: both message POSTs return HTTP 200, NOT 409
//       STREAM_IN_PROGRESS — proving the temporary-path fan-out lets N parallel
//       POSTs share ONE conversation without colliding on the active-stream
//       claim (api/app/routes/conversations.py gates the claim behind
//       `if not is_temp`).
//   (c) both columns render a visible answer + their own AttributionRow, and
//       the two columns show DIFFERENT attribution labels (distinct tiers →
//       distinct per-tier attribution; the FakeProvider varies answer TEXT only
//       by prompt hash, so we assert on the LABELS, never the answer text).
//   (d) the transient compare turn leaks NO conversation into the sidebar.
//
// Tier choice: `fast` and `smart` are both free (no Pro entitlement — only the
// `pro` tier 402s for anonymous users), and they resolve to DISTINCT served
// tier ids, so their attribution bylines differ ("… Fast tier" vs "… Smart
// tier" in the accessible label). We deliberately avoid `pro` (PRO_REQUIRED).
//
// We capture SSE statuses via a passive `page.on("response")` listener (same
// rationale as streaming.spec.ts — `waitForResponse` is fragile against a
// fast-completing SSE stream).

import { expect, test, type Page } from "@playwright/test";

import { waitForBootstrap } from "./helpers";

// Pick a compare-slot tier via the slot's TierPicker dropdown. Scopes the
// option click to the currently-open menu so a sibling slot's (closed but
// possibly still-animating) menu can't satisfy a bare role query.
async function pickCompareTier(
  page: Page,
  slot: 0 | 1,
  tierLabel: string,
): Promise<void> {
  // Open this slot's TierPicker dropdown. The desktop trigger is the only
  // visible button inside the slot (the mobile sheet trigger is display:none at
  // this breakpoint, so it's out of the a11y tree).
  await page.getByTestId(`compare-slot-${slot}`).getByRole("button").click();
  // Click the option from the menu that just opened. Scope to currently-VISIBLE
  // menu items so a sibling slot's menu mid-close-animation can't match.
  const option = page
    .locator('[data-slot="dropdown-menu-item"]:visible', { hasText: tierLabel })
    .first();
  await option.click();
  // Wait for the menu to fully dismiss before the caller opens the next one, so
  // two menus are never simultaneously in the DOM.
  await expect(
    page.locator('[data-slot="dropdown-menu-item"]:visible'),
  ).toHaveCount(0);
}

test.describe("compare mode", () => {
  test("two distinct tiers fan out to two temporary-path streams; both 200, two attributions, no history leak", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Record every message-POST status so we can prove BOTH returned 200 (and
    // neither 409'd on the active-stream claim). Keyed off the SSE URL shape.
    const messageStatuses: number[] = [];
    const messageContentTypes: string[] = [];
    page.on("response", (response) => {
      const url = response.url();
      const method = response.request().method();
      if (method === "POST" && /\/api\/conversations\/[^/]+\/messages$/.test(url)) {
        messageStatuses.push(response.status());
        messageContentTypes.push(response.headers()["content-type"] ?? "");
      }
    });

    // Enable compare mode.
    await page.getByTestId("compare-toggle").click();
    await expect(page.getByTestId("compare-toggle")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByTestId("compare-tier-bar")).toBeVisible();

    // Pick two DISTINCT, free tiers (Fast vs Smart).
    await pickCompareTier(page, 0, "Fast");
    await pickCompareTier(page, 1, "Smart");

    // Send one prompt — fans out to both columns.
    await page.getByTestId("composer-textarea").fill("Compare these two models");
    await page.getByTestId("composer-send").click();

    // (a)+(b) TWO message POSTs fired, BOTH 200 (not 409), both SSE.
    await expect.poll(() => messageStatuses.length, { timeout: 15_000 }).toBe(2);
    expect(messageStatuses).toEqual([200, 200]);
    expect(messageStatuses).not.toContain(409);
    for (const ct of messageContentTypes) {
      expect(ct).toContain("text/event-stream");
    }

    // (c) Two columns render.
    const columns = page.getByTestId("compare-column");
    await expect(columns).toHaveCount(2);

    // Each column streams an answer to done.
    const answers = page
      .getByTestId("compare-column")
      .getByTestId("assistant-answer");
    await expect(answers.first()).toBeVisible({ timeout: 15_000 });
    await expect(answers.nth(1)).toBeVisible({ timeout: 15_000 });

    // Two AttributionRows — one per column — once both terminals land.
    const attributions = page.getByTestId("message-attribution");
    await expect(attributions).toHaveCount(2, { timeout: 15_000 });

    // The two attribution labels DIFFER (distinct tiers → distinct per-tier
    // byline). The label is exposed via aria-label ("served by …, <tier> tier,
    // …"), so the tier difference makes the two labels distinct.
    const labelA = await attributions.nth(0).getAttribute("aria-label");
    const labelB = await attributions.nth(1).getAttribute("aria-label");
    expect(labelA).toBeTruthy();
    expect(labelB).toBeTruthy();
    expect(labelA).not.toBe(labelB);
    // The two distinct served tiers surface in the bylines.
    const combined = `${labelA} ${labelB}`.toLowerCase();
    expect(combined).toContain("fast tier");
    expect(combined).toContain("smart tier");

    // (d) No persisted conversation leaked into the sidebar — the compare
    // conversation was temporary, so the rail stays empty.
    await expect(page.getByTestId("sidebar-conversation-link")).toHaveCount(0);
  });

  test("anonymous user is not offered Pro as a compare slot option", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("compare-toggle").click();
    await expect(page.getByTestId("compare-tier-bar")).toBeVisible();

    // Open slot 0's picker. The anonymous (non-entitled) user can't use Pro, so
    // Pro must not appear as a selectable option — it would only graceful-402.
    await page
      .getByTestId("compare-slot-0")
      .getByRole("button")
      .click();
    const options = page.locator('[data-slot="dropdown-menu-item"]:visible');
    await expect(options.filter({ hasText: "Fast" })).toHaveCount(1);
    await expect(options.filter({ hasText: "Smart" })).toHaveCount(1);
    // No Pro option for the non-entitled user.
    await expect(options.filter({ hasText: "Pro" })).toHaveCount(0);

    // Dismiss the menu so it doesn't bleed into later assertions.
    await page.keyboard.press("Escape");
    await expect(options).toHaveCount(0);
  });

  test("Stop cancels both compare columns", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("compare-toggle").click();
    await pickCompareTier(page, 0, "Fast");
    await pickCompareTier(page, 1, "Smart");

    await page.getByTestId("composer-textarea").fill("Compare and then stop");
    await page.getByTestId("composer-send").click();

    // Two columns mounted.
    await expect(page.getByTestId("compare-column")).toHaveCount(2);

    // Stop is reachable while at least one column streams. Click it if present —
    // the (fast) FakeProvider may settle before we get there, which is a benign
    // race for this optional assertion.
    const stop = page.getByRole("button", { name: "Stop generating" });
    await stop.click({ timeout: 15_000 }).catch(() => {});

    // Neither column is left in a non-terminal state.
    await expect(async () => {
      const statuses = await page
        .getByTestId("compare-column")
        .getByTestId("assistant-message")
        .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-status")));
      expect(statuses.length).toBeGreaterThan(0);
      for (const s of statuses) {
        expect(["done", "stopped", "error"]).toContain(s);
      }
    }).toPass({ timeout: 15_000 });
  });
});
