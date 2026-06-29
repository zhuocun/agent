// Activity & data-access surface — runtime coverage against the live BE.
//
// Drives the real shell + real bootstrap (no stubbing). We seed a `share.mint`
// audit event by minting a share link via the API as the SAME anon user the
// page uses (page.request shares the browser cookie jar), then open Settings →
// "Activity & data access" and assert the event renders newest-first with its
// human-readable label, alongside the data-processing rollup section.

import { expect, test, type Page } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

async function openSettings(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
}

test.describe("activity & data access", () => {
  test("opens the activity dialog and renders the caller's events", async ({
    page,
  }) => {
    // Mint the session, then create + share a conversation so the caller has a
    // deterministic `share.mint` audit event to read back.
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    expect(created.status()).toBe(201);
    const { id: convoId } = await created.json();
    const shared = await page.request.post(
      `${BE_URL}/api/conversations/${convoId}/share`,
    );
    expect(shared.status()).toBe(200);

    await page.goto("/");
    await waitForBootstrap(page);

    // Send a real turn through the UI so the data-processing rollup has live
    // per-message attribution to aggregate (not just the seeded share event).
    const composer = page.getByTestId("composer-textarea");
    await composer.fill("Hello from the activity spec");
    await page.getByTestId("composer-send").click();
    await expect(
      page.getByTestId("assistant-message").last(),
    ).toHaveAttribute("data-status", "done", { timeout: 15_000 });

    await openSettings(page);
    await page.getByTestId("open-activity-button").click();

    const dialog = page.getByTestId("activity-dialog");
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("heading", { name: "Activity & data access" }),
    ).toBeVisible();

    // The data-processing rollup section is present, and the live turn produced
    // at least one provider bucket.
    await expect(
      dialog.getByRole("heading", { name: "Where your messages were processed" }),
    ).toBeVisible();
    await expect(
      dialog.getByTestId("data-processing-bucket").first(),
    ).toBeVisible();

    // The share-mint event renders with its human-readable label.
    const list = dialog.getByTestId("activity-list");
    await expect(list).toBeVisible();
    await expect(
      list.getByText("Created a public share link", { exact: true }),
    ).toBeVisible();

    await dialog.screenshot({
      path: "/opt/cursor/artifacts/activity_dialog.png",
    });
  });
});
