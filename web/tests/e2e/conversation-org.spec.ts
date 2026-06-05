// Conversation Org v2 (tags + archive + bulk actions) — sidebar ↔ BE round-trip.
//
// Mirrors projects.spec.ts: drive the real FE against the real BE on :8000.
// Covers the full vertical slice end-to-end:
//   - create a tag from the sidebar (POST /api/tags)
//   - assign it to a conversation via the row kebab (PATCH tagIds), see a chip
//   - filter the list by the tag (sidebar-tag-filter)
//   - archive a conversation -> it appears in the Archived section -> unarchive
//   - multi-select two conversations + bulk archive + bulk delete
//   - the account export includes the tag
//
// Each test gets a fresh browser context => fresh anon user => clean slate.

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

async function createConversation(
  page: import("@playwright/test").Page,
): Promise<string> {
  const created = await page.request.post(`${BE_URL}/api/conversations`, {
    data: { selectedTierId: "smart", isTemporary: false },
  });
  expect(created.status()).toBe(201);
  return (await created.json()).id as string;
}

test.describe("conversation org v2", () => {
  test("create tag, assign to a conversation, filter by it", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const convoId = await createConversation(page);
    const otherId = await createConversation(page);

    await page.goto("/");
    await waitForBootstrap(page);

    // --- Create a tag from the sidebar ---------------------------------------
    const createTagPost = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/tags` && r.request().method() === "POST",
    );
    await page.getByTestId("sidebar-new-tag").click();
    const tagNameInput = page.getByTestId("sidebar-tag-name-input");
    await expect(tagNameInput).toBeVisible();
    await tagNameInput.fill("Work");
    await page.getByTestId("sidebar-tag-save").click();
    expect((await createTagPost).status()).toBe(201);

    const tagsSection = page.getByTestId("sidebar-tags");
    await expect(tagsSection).toContainText("Work");

    // --- Assign the tag to the conversation via the row kebab ----------------
    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Conversation actions" }).click();
    await page.getByTestId("sidebar-conversation-assign-tags").click();

    const assignPatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "PATCH",
    );
    await page.getByRole("menuitem", { name: "Work" }).click();
    const assignResponse = await assignPatch;
    expect(assignResponse.status()).toBe(200);
    expect((await assignResponse.json()).tagIds).toHaveLength(1);

    // Close the still-open submenu (closeOnClick=false keeps it open).
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");

    // The conversation row shows a tag chip.
    await expect(
      row.getByTestId("sidebar-conversation-tag-chip"),
    ).toContainText("Work");

    // --- Filter by the tag ---------------------------------------------------
    await page.getByTestId("sidebar-tag-filter").click();
    // The tagged conversation stays; the untagged one is filtered out.
    await expect(
      page.locator(`[data-conversation-id="${convoId}"]`),
    ).toBeVisible();
    await expect(
      page.locator(`[data-conversation-id="${otherId}"]`),
    ).toHaveCount(0);

    // Clicking the active tag again clears the filter; both reappear.
    await page.getByTestId("sidebar-tag-filter").click();
    await expect(
      page.locator(`[data-conversation-id="${otherId}"]`),
    ).toBeVisible();
  });

  test("archive a conversation, see it in Archived, then unarchive", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const convoId = await createConversation(page);

    await page.goto("/");
    await waitForBootstrap(page);

    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();

    // --- Archive via the row kebab -------------------------------------------
    await row.getByRole("button", { name: "Conversation actions" }).click();
    const archivePatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "PATCH",
    );
    await page.getByTestId("sidebar-conversation-archive").click();
    const archiveResponse = await archivePatch;
    expect(archiveResponse.status()).toBe(200);
    expect((await archiveResponse.json()).archived).toBe(true);

    // The Archived section appears; expand it and find the row inside.
    const archivedSection = page.getByTestId("sidebar-archived");
    await expect(archivedSection).toBeVisible();
    await page.getByTestId("sidebar-archived-toggle").click();
    await expect(
      archivedSection.locator(`[data-conversation-id="${convoId}"]`),
    ).toBeVisible();

    // --- Unarchive it --------------------------------------------------------
    const archivedRow = archivedSection.locator(
      `[data-conversation-id="${convoId}"]`,
    );
    await archivedRow
      .getByRole("button", { name: "Conversation actions" })
      .click();
    const unarchivePatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "PATCH",
    );
    await page.getByTestId("sidebar-conversation-archive").click();
    const unarchiveResponse = await unarchivePatch;
    expect(unarchiveResponse.status()).toBe(200);
    expect((await unarchiveResponse.json()).archived).toBe(false);

    // The Archived section is gone (no more archived rows).
    await expect(page.getByTestId("sidebar-archived")).toHaveCount(0);
  });

  test("multi-select two conversations, bulk archive, then bulk delete", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const c1 = await createConversation(page);
    const c2 = await createConversation(page);

    await page.goto("/");
    await waitForBootstrap(page);

    // Enter selection mode via the explicit "Select" toggle — only then do the
    // per-row checkboxes render.
    await page.getByTestId("sidebar-select-toggle").click();
    const row1 = page.locator(`[data-conversation-id="${c1}"]`);
    const row2 = page.locator(`[data-conversation-id="${c2}"]`);
    await row1.getByTestId("sidebar-conversation-checkbox").click();
    await row2.getByTestId("sidebar-conversation-checkbox").click();

    const bulkBar = page.getByTestId("sidebar-bulk-bar");
    await expect(bulkBar).toBeVisible();
    await expect(page.getByTestId("sidebar-bulk-count")).toContainText(
      "2 selected",
    );

    // --- Bulk archive --------------------------------------------------------
    const bulkArchive = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/bulk` &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sidebar-bulk-archive").click();
    const archiveResp = await bulkArchive;
    expect(archiveResp.status()).toBe(200);
    expect((await archiveResp.json()).affected).toBe(2);

    // Both land in the Archived section.
    await page.getByTestId("sidebar-archived-toggle").click();
    const archivedSection = page.getByTestId("sidebar-archived");
    await expect(
      archivedSection.locator(`[data-conversation-id="${c1}"]`),
    ).toBeVisible();
    await expect(
      archivedSection.locator(`[data-conversation-id="${c2}"]`),
    ).toBeVisible();

    // --- Bulk delete (re-select inside the Archived section) -----------------
    await page.getByTestId("sidebar-select-toggle").click();
    await archivedSection
      .locator(`[data-conversation-id="${c1}"]`)
      .getByTestId("sidebar-conversation-checkbox")
      .click();
    await archivedSection
      .locator(`[data-conversation-id="${c2}"]`)
      .getByTestId("sidebar-conversation-checkbox")
      .click();

    const bulkDelete = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/bulk` &&
        r.request().method() === "POST",
    );
    await page.getByTestId("sidebar-bulk-delete").click();
    const deleteResp = await bulkDelete;
    expect(deleteResp.status()).toBe(200);
    expect((await deleteResp.json()).affected).toBe(2);

    // Both conversations are gone from the BE.
    expect(
      (await page.request.get(`${BE_URL}/api/conversations/${c1}`)).status(),
    ).toBe(404);
    expect(
      (await page.request.get(`${BE_URL}/api/conversations/${c2}`)).status(),
    ).toBe(404);
  });

  test("account export includes tags", async ({ page }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);

    await page.goto("/");
    await waitForBootstrap(page);

    // Create a tag from the sidebar.
    const createTagPost = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/tags` && r.request().method() === "POST",
    );
    await page.getByTestId("sidebar-new-tag").click();
    await page.getByTestId("sidebar-tag-name-input").fill("Exported");
    await page.getByTestId("sidebar-tag-save").click();
    expect((await createTagPost).status()).toBe(201);

    // The export payload carries the tag.
    const exportResp = await page.request.get(`${BE_URL}/api/account/export`);
    expect(exportResp.status()).toBe(200);
    const payload = await exportResp.json();
    const names = (payload.tags ?? []).map((t: { name: string }) => t.name);
    expect(names).toContain("Exported");
  });
});
