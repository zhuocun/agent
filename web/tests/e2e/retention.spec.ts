// Per-conversation retention override (D31) — sidebar kebab ↔ BE round-trip.
//
// Mirrors conversation.spec.ts: create a conversation via the API (the BE row
// is otherwise minted lazily on first send), reload, then drive the sidebar
// kebab's "Retention" submenu. Setting a window PATCHes `retentionDays`, surfaces
// an "expires in ~N days" hint, and round-trips via GET; clearing it ("Use
// default") sends `retentionDays: null` and removes the hint.
//
// Each test gets a fresh browser context => fresh anon user => clean slate.

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

test.describe("per-conversation retention", () => {
  test("setting then clearing a conversation's retention persists to the BE", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    expect(created.status()).toBe(201);
    const { id: convoId } = await created.json();

    await page.goto("/");
    await waitForBootstrap(page);

    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();

    // Open the row's kebab and hover into the Retention submenu.
    await row.getByRole("button", { name: "Conversation actions" }).click();
    await page.getByTestId("sidebar-conversation-retention").click();

    // Pick "30 days" and watch the PATCH in flight before asserting the UI.
    const setPatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "PATCH",
    );
    await page.getByRole("menuitemradio", { name: "30 days" }).click();
    const setResponse = await setPatch;
    expect(setResponse.status()).toBe(200);
    expect((await setResponse.json()).retentionDays).toBe(30);

    // The "expires in ~N days" hint appears on the row.
    await expect(
      row.getByTestId("sidebar-conversation-retention-hint"),
    ).toContainText(/expires in ~\d+ days/);

    // BE round-trip: GET reflects the override.
    const afterSet = await page.request.get(
      `${BE_URL}/api/conversations/${convoId}`,
    );
    expect((await afterSet.json()).retentionDays).toBe(30);

    // Now clear it back to "Use default" (sends retentionDays: null).
    await row.getByRole("button", { name: "Conversation actions" }).click();
    await page.getByTestId("sidebar-conversation-retention").click();
    const clearPatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "PATCH",
    );
    await page.getByRole("menuitemradio", { name: "Use default" }).click();
    const clearResponse = await clearPatch;
    expect(clearResponse.status()).toBe(200);
    expect((await clearResponse.json()).retentionDays).toBeNull();

    // Hint gone; BE round-trip shows the override cleared.
    await expect(
      row.getByTestId("sidebar-conversation-retention-hint"),
    ).toHaveCount(0);
    const afterClear = await page.request.get(
      `${BE_URL}/api/conversations/${convoId}`,
    );
    expect((await afterClear.json()).retentionDays).toBeNull();
  });
});
