// Command palette + slash-command popover (Flows 6, 19) E2E.
//
// Drives the real fake-provider BE on :8000 through the FE. Closes the ST-4
// coverage gaps on `command-palette.tsx` and `slash-commands-popover.tsx`:
//   - palette summon (Cmd/Ctrl+K), arrow-key navigation, Enter-to-dispatch
//   - type-to-search conversations (the debounced `searchConversations` path)
//     and click-to-navigate
//   - the in-palette filter-mode toggle (enter via the slider button AND the
//     "Advanced search" action row) and the "Back to commands" exit
//   - the composer slash popover: open on "/", filter, pick (prefill),
//     no-match empty state, and outside-click dismissal
//
// Each test gets a fresh browser context => fresh anon user => clean slate.

import { expect, test } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

// Create a conversation with a searchable title; returns its id. Mirrors the
// seed helper in history-search.spec.ts.
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

const PALETTE_PLACEHOLDER = "Search actions & chats…";

test.describe("command palette", () => {
  test("arrow-key navigation moves the active option, Enter dispatches an action", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page.keyboard.press("ControlOrMeta+k");
    const input = page.getByPlaceholder(PALETTE_PLACEHOLDER);
    await expect(input).toBeVisible();

    // The combobox input points at the active option via aria-activedescendant;
    // ArrowDown/ArrowUp must move it (the keyboard-nav branch the gap report
    // flagged at command-palette.tsx:480-491).
    const first = await input.getAttribute("aria-activedescendant");
    expect(first).toBeTruthy();
    await input.press("ArrowDown");
    const afterDown = await input.getAttribute("aria-activedescendant");
    expect(afterDown).not.toBe(first);
    await input.press("ArrowUp");
    const afterUp = await input.getAttribute("aria-activedescendant");
    expect(afterUp).toBe(first);

    // Type-to-filter, then Enter dispatches the highlighted action. "Open
    // settings" routes through runItem -> action.run() -> the Settings hub.
    await input.fill("Open settings");
    await expect(
      page.getByRole("option", { name: "Open settings" }),
    ).toBeVisible();
    await input.press("Enter");

    await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
  });

  test("typing a query runs a remote conversation search; a result navigates", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const convoId = await seedConversation(page.request, "peregrine launch plan");

    await page.goto("/");
    await waitForBootstrap(page);

    // Watch the debounced /api/conversations/search round-trip the palette fires
    // (command-palette.tsx:254-265 — the `searchConversations` effect).
    const searchResponse = page.waitForResponse(
      (r) =>
        /\/api\/conversations\/search(\?|$)/.test(r.url()) &&
        r.request().method() === "GET",
    );

    await page.keyboard.press("ControlOrMeta+k");
    const input = page.getByPlaceholder(PALETTE_PLACEHOLDER);
    await expect(input).toBeVisible();
    await input.fill("peregrine");
    expect((await searchResponse).status()).toBe(200);

    const result = page.getByRole("option", { name: /peregrine launch plan/ });
    await expect(result).toBeVisible();
    await result.click();

    // Palette closes and the clicked conversation becomes active (its row shows
    // in the sidebar). runItem's conversation branch + onSelectConversation.
    await expect(page.getByPlaceholder(PALETTE_PLACEHOLDER)).toHaveCount(0);
    await expect(
      page.locator(`[data-conversation-id="${convoId}"]`).first(),
    ).toBeVisible();
  });

  test("the filter toggle enters advanced-search mode and Back returns to commands", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page.keyboard.press("ControlOrMeta+k");
    await expect(page.getByPlaceholder(PALETTE_PLACEHOLDER)).toBeVisible();

    // Slider button → in-place filter mode (enterFilterMode). The popup now
    // carries the `search-dialog` testid and the native filter form renders.
    await page.getByTestId("palette-filter-toggle").click();
    await expect(page.getByTestId("search-dialog")).toBeVisible();
    await expect(page.getByTestId("search-query-input")).toBeVisible();
    await expect(page.getByTestId("search-filter-model")).toBeVisible();

    // Back to commands (exitFilterMode) → the listbox combobox returns.
    await page.getByRole("button", { name: "Back to commands" }).click();
    await expect(page.getByPlaceholder(PALETTE_PLACEHOLDER)).toBeVisible();
    await expect(page.getByTestId("search-dialog")).toHaveCount(0);
  });

  test("the 'Advanced search' action row also enters filter mode", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page.keyboard.press("ControlOrMeta+k");
    const input = page.getByPlaceholder(PALETTE_PLACEHOLDER);
    await expect(input).toBeVisible();

    // Selecting the row whose action carries `entersFilterMode` swaps the
    // palette into filter mode in place (runItem:458-462) rather than closing.
    await input.fill("Advanced search");
    await page.getByRole("option", { name: "Advanced search" }).click();
    await expect(page.getByTestId("search-dialog")).toBeVisible();
    await expect(page.getByTestId("search-query-input")).toBeVisible();
  });
});

test.describe("slash commands popover", () => {
  const SLASH_LISTBOX = "Slash commands";

  test("opens on '/', filters, and picking a command prefills the composer", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const textarea = page.getByTestId("composer-textarea");
    await textarea.click();
    await textarea.fill("/");

    // Popover opens with the full command set.
    const listbox = page.getByRole("listbox", { name: SLASH_LISTBOX });
    await expect(listbox).toBeVisible();
    await expect(page.getByRole("option")).not.toHaveCount(0);

    // Filtering narrows to the matching command (filterCommands).
    await textarea.fill("/sum");
    const summarize = page.getByRole("option", { name: /summarize/i });
    await expect(summarize).toBeVisible();

    // Picking prefills the composer with the command's prompt body and closes.
    await summarize.click();
    await expect(textarea).toHaveValue(/Summarize the following text/);
    await expect(page.getByRole("listbox", { name: SLASH_LISTBOX })).toHaveCount(
      0,
    );
  });

  test("shows the no-match hint for an unknown command", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const textarea = page.getByTestId("composer-textarea");
    await textarea.click();
    await textarea.fill("/zzzznope");

    await expect(
      page.getByText("No commands match — keep typing for a regular message."),
    ).toBeVisible();
  });

  test("an outside click dismisses the popover", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const textarea = page.getByTestId("composer-textarea");
    await textarea.click();
    await textarea.fill("/");
    await expect(
      page.getByRole("listbox", { name: SLASH_LISTBOX }),
    ).toBeVisible();

    // A pointerdown outside the popup AND its composer anchor closes it
    // (slash-commands-popover.tsx:91-104). Click high in the thread area, well
    // clear of the bottom-pinned composer capsule.
    await page.mouse.click(400, 180);
    await expect(
      page.getByRole("listbox", { name: SLASH_LISTBOX }),
    ).toHaveCount(0);
  });
});
