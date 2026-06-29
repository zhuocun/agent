// Account-data + suggestions surfaces — runtime coverage against the live BE.
//
// Three independent concerns, each in a fresh browser context (=> fresh anon
// user, clean slate):
//   1. Bootstrap prompt suggestions render in the welcome list and clicking a
//      row inserts the suggestion's FULL prompt into the composer draft.
//   2. "Export your data" downloads `account-export.json` whose JSON carries the
//      documented top-level keys.
//   3. "Delete account" wipes the caller's data and reloads as a brand-new
//      anonymous user (the prior conversation is gone, and the new session is a
//      different signed cookie).
//
// We drive the REAL shell + real bootstrap throughout (no route stubbing): these
// features are wired end-to-end (FE → BE on :8000 with PROVIDER_BACKEND=fake),
// so stubbing would defeat the point. Suggestion copy is read from the live
// /api/bootstrap payload rather than hardcoded, so the test tracks the BE's
// source of truth.
//
// Settings is opened via the sidebar account menu: the desktop sidebar footer
// renders a `aria-label="Account menu"` trigger (same trigger the auth-dialog
// spec uses) whose dropdown carries a "Settings" item. The suite runs Chromium
// desktop, so the sidebar footer menu is the canonical path.

import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./coverage-fixture";

import { BE_URL, sessionCookie, waitForBootstrap } from "./helpers";

// Open the settings dialog from the sidebar account menu (desktop path) and
// wait for the dialog's "Settings" title to confirm it's on screen.
async function openSettings(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
}

test.describe("account data + suggestions", () => {
  test("welcome suggestions render and clicking one inserts its full prompt", async ({
    page,
  }) => {
    // Read the actual suggestion set from the live BE rather than hardcoding
    // copy — the welcome list is rendered from exactly this payload.
    const bootstrap = await page.request.get(`${BE_URL}/api/bootstrap`);
    expect(bootstrap.status()).toBe(200);
    const { suggestions } = (await bootstrap.json()) as {
      suggestions: Array<{ id: string; title: string; prompt: string }>;
    };
    expect(suggestions.length).toBeGreaterThan(0);

    await page.goto("/");
    await waitForBootstrap(page);

    const list = page.getByRole("list", { name: "Suggested prompts" });
    await expect(list).toBeVisible();

    // Each suggestion's TITLE shows as a row label.
    for (const s of suggestions) {
      await expect(list.getByText(s.title, { exact: true })).toBeVisible();
    }

    // Clicking the first row sets the composer draft to that suggestion's FULL
    // prompt (not its title). Titles and prompts differ in the BE fixture, so
    // this distinguishes "inserted the prompt" from "inserted the label".
    const first = suggestions[0]!;
    expect(first.prompt).not.toBe(first.title);

    await list.getByText(first.title, { exact: true }).click();

    await expect(page.getByTestId("composer-textarea")).toHaveValue(
      first.prompt,
    );
  });

  test("export downloads account-export.json with the documented shape", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await openSettings(page);

    // Arm the download listener BEFORE the click that triggers the Blob anchor.
    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("export-data-button").click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe("account-export.json");

    // Read the downloaded bytes and assert the top-level envelope keys.
    const path = await download.path();
    expect(path).toBeTruthy();
    const raw = await readFile(path, "utf8");
    const data = JSON.parse(raw) as Record<string, unknown>;

    expect(data).toHaveProperty("account");
    expect(data).toHaveProperty("preferences");
    expect(data).toHaveProperty("usage");
    expect(data).toHaveProperty("conversations");
    expect(data).toHaveProperty("exportedAt");
  });

  test("delete account wipes data and reloads as a fresh anonymous user", async ({
    page,
    context,
  }) => {
    // Establish identity: mint the session, then a persisted conversation so the
    // caller has owned data and a sidebar row (same pattern as conversation.spec).
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    expect(created.status()).toBe(201);
    const { id: convoId } = await created.json();

    await page.goto("/");
    await waitForBootstrap(page);

    // The conversation is listed in the sidebar — proof this is the owning user.
    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();

    // Capture the pre-delete session cookie to confirm identity rotates.
    const before = await sessionCookie(context);
    expect(before).not.toBeNull();

    // Open settings → click "Delete account" (closes settings, opens the confirm
    // dialog) → confirm via the destructive button.
    await openSettings(page);
    await page.getByTestId("delete-account-button").click();

    const confirm = page.getByTestId("confirm-delete-account");
    await expect(confirm).toBeVisible();

    // The delete dialog requires typing the confirmation value — the account
    // email, or "DELETE" for an anonymous caller (this test's fresh user).
    await page.getByTestId("delete-account-confirm-input").fill("DELETE");

    // Confirming fires DELETE /api/account then window.location.reload(). Wait
    // for the DELETE so we don't race the navigation teardown.
    const deletePromise = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/account` &&
        r.request().method() === "DELETE",
    );
    await confirm.click();
    const deleteResponse = await deletePromise;
    expect(deleteResponse.status()).toBe(204);

    // The reload bootstraps a fresh anonymous user. Wait for the shell again.
    await waitForBootstrap(page);

    // (1) The previously-created conversation is gone from the sidebar.
    await expect(page.locator(`[data-conversation-id="${convoId}"]`)).toHaveCount(
      0,
    );

    // (2) The fresh session is a NEW anonymous user: a different signed cookie
    // (the BE cleared `sid`, so the reload minted a new session row).
    const after = await sessionCookie(context);
    expect(after).not.toBeNull();
    expect(after?.value).not.toBe(before?.value);

    // (3) The old conversation isn't visible to the fresh user — a direct GET
    // 404s (not-found / not-owned), the per-user isolation guarantee.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convoId}`,
    );
    expect(fetched.status()).toBe(404);
  });
});
