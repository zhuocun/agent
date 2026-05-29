// Conversation CRUD path — sidebar ↔ BE round-trip.
//
// Why we create via API rather than the UI "new chat" button:
//   `handleNewChat` in chat-thread.tsx is a client-only reset (no BE call) —
//   the BE row is minted lazily on the FIRST send (`beginTurn` calls
//   POST /api/conversations). Driving a streaming send just to land a row in
//   the sidebar would conflate this test's concern (conversation CRUD) with
//   the streaming spec. Creating via API + reload covers the BE→FE wire and
//   leaves the streaming spec to own SSE.
//
// Each test gets a fresh browser context => fresh anon user => clean slate
// for `/api/conversations` listings (per-user filtered in the repo).

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

test.describe("conversation CRUD", () => {
  test("a conversation created via the API appears in the sidebar after bootstrap", async ({
    page,
  }) => {
    // Mint the session by hitting bootstrap first — the FE's bootstrap useEffect
    // would do this for us, but doing it explicitly keeps the test ordering
    // obvious. Cookies persist on the browser context.
    const bs = await page.request.get(`${BE_URL}/api/bootstrap`);
    expect(bs.status()).toBe(200);

    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    expect(created.status()).toBe(201);
    const convo = await created.json();
    expect(convo.id).toBeTruthy();
    expect(convo.title).toBe("New chat");
    expect(convo.isTemporary).toBe(false);

    await page.goto("/");
    await waitForBootstrap(page);

    const row = page.locator(`[data-conversation-id="${convo.id}"]`);
    await expect(row).toBeVisible();
    await expect(row.getByTestId("sidebar-conversation-title")).toHaveText(
      convo.title,
    );
  });

  test("renaming a conversation via the UI persists to the BE", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    const { id: convoId } = await created.json();

    await page.goto("/");
    await waitForBootstrap(page);

    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();

    // Open the row's kebab menu. There's exactly one "Conversation actions"
    // button per row; scoping by `row` keeps us off any other row.
    await row.getByRole("button", { name: "Conversation actions" }).click();

    // base-ui DropdownMenu items render with role="menuitem"; the visible
    // text is the most stable selector (we don't have testids on items and
    // the brief asks to add them only where role/text isn't stable).
    await page.getByRole("menuitem", { name: "Rename" }).click();

    const renameInput = row.getByTestId("sidebar-conversation-rename-input");
    await expect(renameInput).toBeFocused();
    await renameInput.fill("");
    await renameInput.fill("Renamed via E2E");

    // Watch the PATCH in flight before committing so we don't race on the
    // optimistic UI write vs the BE round-trip.
    const patchPromise = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "PATCH",
    );
    await renameInput.press("Enter");
    const patchResponse = await patchPromise;
    expect(patchResponse.status()).toBe(200);

    // UI reflects the new title.
    await expect(row.getByTestId("sidebar-conversation-title")).toHaveText(
      "Renamed via E2E",
    );

    // BE round-trip: GET /api/conversations/:id returns the new title.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convoId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = await fetched.json();
    expect(body.title).toBe("Renamed via E2E");
  });

  test("deleting a conversation via the UI removes it from the sidebar and the BE", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    const { id: convoId } = await created.json();

    await page.goto("/");
    await waitForBootstrap(page);

    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();

    await row.getByRole("button", { name: "Conversation actions" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();

    // Confirmation dialog (data-loss guard). The dialog's destructive button
    // says "Delete".
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    const deletePromise = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "DELETE",
    );
    await dialog.getByRole("button", { name: "Delete" }).click();
    const deleteResponse = await deletePromise;
    expect(deleteResponse.status()).toBe(204);

    // Sidebar row gone from the DOM.
    await expect(row).toHaveCount(0);

    // BE round-trip: the conversation is no longer fetchable. The route is
    // documented as 404 on not-found / not-owned.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convoId}`,
    );
    expect(fetched.status()).toBe(404);
  });
});
