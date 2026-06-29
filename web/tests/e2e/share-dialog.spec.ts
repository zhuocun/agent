// Share dialog — create / copy / revoke a public share link.
//
// Test approach: a first group drives the dialog against the LIVE BE share API
// (no stubs) — create → show-URL → copy → navigate the minted link → revoke →
// re-create — so the real wire path (POST/DELETE /api/conversations/:id/share +
// the GET /api/share/:token public read it produces) is exercised end-to-end.
// A second group keeps page.route() stubs for the branches the live BE can't be
// coerced into cheaply: the error-copy mapping (404 / 429 / 5xx / network) and
// the clipboard-unavailable manual-copy fallback. Together they own the FE
// dialog behaviour and the absolute-URL assembly from the relative `sharePath`
// the BE returns.
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

import { expect, test, type Page } from "./coverage-fixture";

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

test.describe("share dialog (live BE)", () => {
  test("creates a link against the live BE and the minted URL opens the public view", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);

    await openShareDialog(page);

    // No route stub here — the click hits the real POST share route.
    await page.getByRole("button", { name: "Create share link" }).click();

    const field = page.getByRole("textbox", { name: "Public share link" });
    await expect(field).toBeVisible();

    // The dialog assembled an absolute URL on our own origin from the relative
    // sharePath the BE returned.
    const origin = new URL(page.url()).origin;
    const shareUrl = await field.inputValue();
    expect(shareUrl.startsWith(`${origin}/share/`)).toBe(true);

    // Copy happy path against the real URL.
    await page.getByRole("button", { name: "Copy", exact: true }).click();
    await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
      shareUrl,
    );

    // End-to-end: navigate the minted link and confirm the public read-only
    // view renders. The conversation was minted empty (no turns), so this also
    // exercises the public view's empty-conversation branch.
    const sharePath = new URL(shareUrl).pathname;
    await page.goto(sharePath);
    await expect(page.getByTestId("public-conversation-title")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByText("This conversation has no messages yet."),
    ).toBeVisible();
    // Read-only chrome — no composer on the public page.
    await expect(page.getByTestId("composer-textarea")).toHaveCount(0);
  });

  test("revokes against the live BE and can re-create the link", async ({
    page,
  }) => {
    await openShareDialog(page);

    await page.getByRole("button", { name: "Create share link" }).click();
    const field = page.getByRole("textbox", { name: "Public share link" });
    await expect(field).toBeVisible();

    // Revoke → real DELETE returns 204; the dialog returns to the create state.
    const deletePromise = page.waitForResponse(
      (r) =>
        /\/api\/conversations\/[^/]+\/share$/.test(r.url()) &&
        r.request().method() === "DELETE",
    );
    await page.getByRole("button", { name: "Remove link" }).click();
    expect((await deletePromise).status()).toBe(204);

    await expect(field).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Create share link" }),
    ).toBeVisible();

    // Re-minting after a revoke issues a fresh token and lands back in the
    // ready state.
    await page.getByRole("button", { name: "Create share link" }).click();
    await expect(
      page.getByRole("textbox", { name: "Public share link" }),
    ).toBeVisible();
  });
});

test.describe("share dialog (stubbed branches)", () => {
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

  test("maps a 429 to a rate-limit message", async ({ page }) => {
    await page.route("**/api/conversations/*/share", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "RATE_LIMITED",
            severity: "error",
            title: "Slow down",
            body: "Too many requests.",
          },
        }),
      });
    });

    await openShareDialog(page);
    await page.getByRole("button", { name: "Create share link" }).click();

    await expect(page.getByRole("alert")).toHaveText(
      "Too many attempts. Try again in a minute.",
    );
  });

  test("maps a network failure to a connection message", async ({ page }) => {
    await page.route("**/api/conversations/*/share", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      // Abort so the browser's fetch rejects → apiClient ApiNetworkError.
      await route.abort();
    });

    await openShareDialog(page);
    await page.getByRole("button", { name: "Create share link" }).click();

    await expect(page.getByRole("alert")).toHaveText(
      "Couldn't reach the server. Check your connection and try again.",
    );
  });

  test("falls back to the server's own copy for an unexpected error", async ({
    page,
  }) => {
    await page.route("**/api/conversations/*/share", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "INTERNAL",
            severity: "error",
            title: "Server error",
            body: "The server tripped over itself.",
          },
        }),
      });
    });

    await openShareDialog(page);
    await page.getByRole("button", { name: "Create share link" }).click();

    // Non-404/429 falls through to the server's own body copy.
    await expect(page.getByRole("alert")).toHaveText(
      "The server tripped over itself.",
    );
  });

  test("falls back to manual copy when the clipboard API is unavailable", async ({
    page,
  }) => {
    // Make navigator.clipboard.writeText present-but-rejecting so the dialog
    // takes the catch → select-the-field fallback (insecure origin / denied
    // permission path), set BEFORE the shell loads so it survives navigation.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText: () => Promise.reject(new Error("denied")) },
      });
    });

    await page.route("**/api/conversations/*/share", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
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
    await page.getByRole("button", { name: "Create share link" }).click();

    const field = page.getByRole("textbox", { name: "Public share link" });
    await expect(field).toBeVisible();

    await page.getByRole("button", { name: "Copy", exact: true }).click();

    // Fallback focuses + selects the field so the user can copy manually, and
    // the button never flips to its "Copied" confirmation.
    await expect(field).toBeFocused();
    await expect(
      page.getByRole("button", { name: "Copy", exact: true }),
    ).toBeVisible();
  });

  test("re-opening the dialog after closing resets to the create state", async ({
    page,
  }) => {
    await page.route("**/api/conversations/*/share", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
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
    await page.getByRole("button", { name: "Create share link" }).click();
    await expect(
      page.getByRole("textbox", { name: "Public share link" }),
    ).toBeVisible();

    // Close → the close path clears transient state (URL/copied/error/status).
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Share chat" }),
    ).toHaveCount(0);

    // Re-open the same conversation's dialog — it must start clean in "create".
    await page.getByRole("button", { name: "Chat menu" }).click();
    await page.getByRole("menuitem", { name: "Share chat" }).click();
    await expect(
      page.getByRole("heading", { name: "Share chat" }),
    ).toBeVisible();

    await expect(
      page.getByRole("textbox", { name: "Public share link" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Create share link" }),
    ).toBeVisible();
  });
});
