// Customizable keyboard shortcuts (D23) E2E.
//
// Drives the real fake-provider BE: open Settings -> "Customize" -> the editable
// shortcuts dialog, rebind one action by capturing a new combo, and assert the
// override is (a) persisted to /api/preferences via the optimistic flow and
// (b) reflected on a fresh bootstrap. Also asserts the reserved-combo guard
// rejects a composer-invariant key inline. Deterministic — gated on the PUT
// request body, not on timing.

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

async function openShortcutsDialog(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings).toBeVisible();
  await settings.getByTestId("open-shortcuts-button").click();
  // Shortcuts is now a tab inside the Settings hub (not a standalone dialog):
  // assert the Shortcuts heading and return the Settings dialog handle so the
  // shortcut-* testids resolve within it.
  await expect(
    settings.getByRole("heading", { name: "Keyboard shortcuts" }),
  ).toBeVisible();
  return settings;
}

test.describe("keyboard shortcuts customization", () => {
  test("rebinding an action persists the override", async ({ page }) => {
    const putBodies: Array<Record<string, unknown>> = [];
    page.on("request", (request) => {
      if (
        request.url() === `${BE_URL}/api/preferences` &&
        request.method() === "PUT"
      ) {
        putBodies.push(request.postDataJSON() as Record<string, unknown>);
      }
    });

    await page.goto("/");
    await waitForBootstrap(page);

    const dialog = await openShortcutsDialog(page);

    // Enter capture for "Toggle sidebar" (default Ctrl/Cmd+Shift+S) and rebind
    // it to Ctrl+Shift+B. On the Linux CI runner `mod` resolves to Control.
    const rebind = dialog.getByTestId("shortcut-rebind-toggle-sidebar");
    await rebind.click();
    await expect(rebind).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("Control+Shift+B");

    // The composer stores the raw `event.key`; with Shift held that's the
    // uppercase letter ("B"), matching the built-in KEY_BINDINGS convention
    // (e.g. new-chat is "O"). The live matcher lower-cases both sides anyway.
    await expect
      .poll(() =>
        putBodies.some((body) => {
          const ks = body.keyboardShortcuts as
            | Record<string, { key?: string; mod?: boolean; shift?: boolean }>
            | undefined;
          const combo = ks?.["toggle-sidebar"];
          return (
            combo?.key?.toLowerCase() === "b" &&
            combo.mod === true &&
            combo.shift === true
          );
        }),
      )
      .toBe(true);

    // Persisted: a fresh bootstrap echoes the override back.
    const persisted = await page.request.get(`${BE_URL}/api/bootstrap`);
    expect(persisted.status()).toBe(200);
    const body = await persisted.json();
    const persistedCombo =
      body.preferences.keyboardShortcuts["toggle-sidebar"];
    expect(persistedCombo.key.toLowerCase()).toBe("b");
    expect(persistedCombo.mod).toBe(true);
    expect(persistedCombo.shift).toBe(true);
  });

  test("reserved-combo guard rejects a composer-invariant key inline", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const dialog = await openShortcutsDialog(page);

    // Try to bind "Toggle sidebar" to Enter — reserved for the composer send
    // invariant. The guard must reject it with an inline message and NOT change
    // the displayed combo.
    const rebind = dialog.getByTestId("shortcut-rebind-toggle-sidebar");
    await rebind.click();
    await page.keyboard.press("Enter");

    await expect(
      dialog.getByTestId("shortcut-error-toggle-sidebar"),
    ).toBeVisible();
  });
});
