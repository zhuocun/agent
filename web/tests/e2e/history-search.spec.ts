// Advanced history search (D-advanced-search) — FE dialog ↔ BE filter round-trip.
//
// Mirrors projects.spec.ts: drive the real FE against the real BE on :8000.
// Covers the advanced-search dialog end-to-end:
//   - open the dialog from the sidebar "Advanced search" affordance
//   - a plain query matches conversations by title (no filters)
//   - the project filter narrows results to the filed conversation
//   - the date filter (dateFrom in the future) narrows results to none
//
// Conversations are minted via the API and given distinct, searchable titles via
// PATCH so the title-match path lights up without streaming a message. NO
// tag-filter test: the `conversation_tag` table is owned by a parallel
// workstream and is absent from this branch.
//
// Each test gets a fresh browser context => fresh anon user => clean slate.

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

// Create a conversation and set a searchable title on it. Returns its id.
async function seedConversation(
  request: import("@playwright/test").APIRequestContext,
  title: string,
): Promise<string> {
  const created = await request.post(`${BE_URL}/api/conversations`, {
    data: { selectedTierId: "smart", isTemporary: false },
  });
  expect(created.status()).toBe(201);
  const { id } = await created.json();
  const patched = await request.patch(`${BE_URL}/api/conversations/${id}`, {
    data: { title },
  });
  expect(patched.status()).toBe(200);
  return id as string;
}

// Wait for the next `/api/conversations/search` response (the dialog debounces,
// then fires this request through the FE same-origin proxy).
function waitForSearch(page: import("@playwright/test").Page) {
  return page.waitForResponse(
    (r) =>
      /\/api\/conversations\/search(\?|$)/.test(r.url()) &&
      r.request().method() === "GET",
  );
}

test.describe("advanced history search", () => {
  test("plain query, then project and date filters narrow results", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);

    // Two searchable conversations sharing a common query word ("falcon"), plus
    // a project to file one of them under.
    const filedId = await seedConversation(page.request, "falcon alpha report");
    const unfiledId = await seedConversation(page.request, "falcon beta notes");

    const projectResp = await page.request.post(`${BE_URL}/api/projects`, {
      data: { name: "Research" },
    });
    expect(projectResp.status()).toBe(201);
    const { id: projectId } = await projectResp.json();

    const assignResp = await page.request.patch(
      `${BE_URL}/api/conversations/${filedId}`,
      { data: { projectId } },
    );
    expect(assignResp.status()).toBe(200);

    await page.goto("/");
    await waitForBootstrap(page);

    // --- Open the dialog from the sidebar affordance -------------------------
    await page.getByTestId("sidebar-advanced-search").click();
    const dialog = page.getByTestId("search-dialog");
    await expect(dialog).toBeVisible();

    // --- Plain query: both conversations match by title ----------------------
    const plainSearch = waitForSearch(page);
    await page.getByTestId("search-query-input").fill("falcon");
    expect((await plainSearch).status()).toBe(200);

    const results = page.getByTestId("search-result");
    await expect(results).toHaveCount(2);
    await expect(
      dialog.locator(`[data-conversation-id="${filedId}"]`),
    ).toBeVisible();
    await expect(
      dialog.locator(`[data-conversation-id="${unfiledId}"]`),
    ).toBeVisible();

    // --- Project filter: narrows to the filed conversation -------------------
    const projectSearch = waitForSearch(page);
    await page
      .getByTestId("search-filter-project")
      .selectOption({ label: "Research" });
    const projectSearchResp = await projectSearch;
    expect(projectSearchResp.status()).toBe(200);
    // The BE applied the projectId filter.
    expect(new URL(projectSearchResp.url()).searchParams.get("projectId")).toBe(
      projectId,
    );

    await expect(results).toHaveCount(1);
    await expect(
      dialog.locator(`[data-conversation-id="${filedId}"]`),
    ).toBeVisible();
    await expect(
      dialog.locator(`[data-conversation-id="${unfiledId}"]`),
    ).toHaveCount(0);

    // Clear the project filter back to "Any project" before the date check.
    const clearProject = waitForSearch(page);
    await page.getByTestId("search-filter-project").selectOption({ value: "" });
    expect((await clearProject).status()).toBe(200);
    await expect(results).toHaveCount(2);

    // --- Date filter: a dateFrom in the future excludes everything -----------
    const dateSearch = waitForSearch(page);
    await page.getByTestId("search-filter-date-from").fill("2999-01-01");
    const dateSearchResp = await dateSearch;
    expect(dateSearchResp.status()).toBe(200);
    expect(
      new URL(dateSearchResp.url()).searchParams.get("dateFrom"),
    ).toBeTruthy();

    await expect(results).toHaveCount(0);
    await expect(dialog).toContainText("No matches");
  });

  test("clicking a result navigates to that conversation", async ({ page }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const convoId = await seedConversation(page.request, "navigable kestrel log");

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("sidebar-advanced-search").click();
    await expect(page.getByTestId("search-dialog")).toBeVisible();

    const search = waitForSearch(page);
    await page.getByTestId("search-query-input").fill("kestrel");
    expect((await search).status()).toBe(200);

    const result = page.locator(
      `[data-testid="search-result"][data-conversation-id="${convoId}"]`,
    );
    await expect(result).toBeVisible();
    await result.click();

    // The dialog closes and the conversation's messages load (the active thread
    // fetch fires for the clicked conversation).
    await expect(page.getByTestId("search-dialog")).toHaveCount(0);
    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row.first()).toBeVisible();
  });
});
