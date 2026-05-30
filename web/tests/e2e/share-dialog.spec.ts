// Share dialog — create / copy / revoke a public share link.
//
// Test approach (mirrors auth-dialog.spec.ts): the share *routes* are exercised
// via page.route() stubs rather than the live BE. This spec owns the FE dialog
// behaviour (open, create→show-URL, copy, revoke→back-to-create, error
// mapping) and the absolute-URL assembly from the relative `sharePath` the BE
// returns. Stubbing keeps it green regardless of whether the BE share routes
// have shipped, and avoids depending on share-token seeding.
//
// To reach the dialog we still drive the REAL shell + real bootstrap: the
// Share menu item is gated on a real, persisted (non-temporary) ACTIVE
// conversation, so we mint a conversation via the BE API (same pattern as
// conversation.spec.ts), reload, select its sidebar row to make it active, then
// open the header Chat menu → Share chat.
//
// Clipboard: we grant the clipboard-write permission to the Chromium context so
// the Clipboard API happy path runs (and assert the copied value), exercising
// the same code path real users hit on a secure origin.

import { expect, test, type Page } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

const SHARE_TOKEN = "tok_abc123";
const SHARE_PATH = `/share/${SHARE_TOKEN}`;

// Mint a real, persisted conversation via the BE, load the shell, select it so
// it becomes the active conversation, then open the header Chat menu and click
// "Share chat" — landing in the share dialog with its initial "create" state.
async function openShareDialog(page: Page): Promise<string> {
  // Mint the session, then a conversation (same pattern as conversation.spec.ts).
  await page.request.get(`${BE_URL}/api/bootstrap`);
  const created = await page.request.post(`${BE_URL}/api/conversations`, {
    data: { selectedTierId: "smart", isTemporary: false },
  });
  expect(created.status()).toBe(201);
  const { id: convoId } = await created.json();

  await page.goto("/");
  await waitForBootstrap(page);

  // Select the conversation so it becomes active (the Share item is gated on a
  // real, non-temporary active conversation).
  const row = page.locator(`[data-conversation-id="${convoId}"]`);
  await expect(row).toBeVisible();
  await row.getByTestId("sidebar-conversation-link").click();

  await page.getByRole("button", { name: "Chat menu" }).click();
  await page.getByRole("menuitem", { name: "Share chat" }).click();

  await expect(
    page.getByRole("heading", { name: "Share chat" }),
  ).toBeVisible();

  return convoId;
}

test.describe("share dialog", () => {
  test("creates a link and shows the absolute URL built from origin + sharePath", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);

    let createBody: unknown = "unset";
    await page.route("**/api/conversations/*/share", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      createBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          shareToken: SHARE_TOKEN,
          sharePath: SHARE_PATH,
        }),
      });
    });

    await openShareDialog(page);

    await page
      .getByRole("button", { name: "Create share link" })
      .click();

    // The dialog assembles the absolute URL from the FE origin + the relative
    // sharePath. The origin is whatever Playwright's baseURL resolves to.
    const origin = new URL(page.url()).origin;
    const expectedUrl = `${origin}${SHARE_PATH}`;

    const field = page.getByRole("textbox", { name: "Public share link" });
    await expect(field).toHaveValue(expectedUrl);

    // POST carries no body (idempotent mint keyed by the path param).
    expect(createBody).toBeNull();

    // Copy → clipboard holds the absolute URL and the button confirms.
    await page.getByRole("button", { name: "Copy", exact: true }).click();
    await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
    const clip = await page.evaluate(() => navigator.clipboard.readText());
    expect(clip).toBe(expectedUrl);
  });

  test("revoking returns the dialog to the create state", async ({ page }) => {
    await page.route("**/api/conversations/*/share", async (route) => {
      const method = route.request().method();
      if (method === "POST") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            shareToken: SHARE_TOKEN,
            sharePath: SHARE_PATH,
          }),
        });
      }
      if (method === "DELETE") {
        return route.fulfill({ status: 204, body: "" });
      }
      return route.fallback();
    });

    await openShareDialog(page);

    await page.getByRole("button", { name: "Create share link" }).click();
    await expect(
      page.getByRole("textbox", { name: "Public share link" }),
    ).toBeVisible();

    // Revoke → the link field disappears and the create button comes back.
    const deletePromise = page.waitForResponse(
      (r) =>
        /\/api\/conversations\/[^/]+\/share$/.test(r.url()) &&
        r.request().method() === "DELETE",
    );
    await page.getByRole("button", { name: "Remove link" }).click();
    const deleteResponse = await deletePromise;
    expect(deleteResponse.status()).toBe(204);

    await expect(
      page.getByRole("textbox", { name: "Public share link" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Create share link" }),
    ).toBeVisible();
  });

  test("shows an inline error when the conversation can't be shared", async ({
    page,
  }) => {
    await page.route("**/api/conversations/*/share", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "NOT_FOUND",
            severity: "error",
            title: "Not found",
            body: "No such conversation.",
          },
        }),
      });
    });

    await openShareDialog(page);

    await page.getByRole("button", { name: "Create share link" }).click();

    await expect(
      page.getByRole("alert"),
    ).toHaveText("This conversation can't be shared.");
    // Stays on the create state so the user can retry.
    await expect(
      page.getByRole("button", { name: "Create share link" }),
    ).toBeVisible();
  });
});
