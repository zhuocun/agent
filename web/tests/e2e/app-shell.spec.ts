// Responsive app shell (Flow 1) E2E.
//
// Closes the ST-4 gaps on `app-shell.tsx` — the desktop rail collapse branch
// and the mobile drawer open/close path (including the history-entry push so
// Android hardware Back closes the drawer instead of leaving the page).

import { expect, test } from "./coverage-fixture";

import { waitForBootstrap } from "./helpers";

test.describe("app shell — desktop rail", () => {
  test("Toggle sidebar collapses and restores the persistent rail", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // The rail starts open (sidebarOpen=true → aria-hidden="false").
    const aside = page.locator("aside").first();
    await expect(aside).toHaveAttribute("aria-hidden", "false");

    // Mod+Shift+S routes through handleToggleSidebar → setSidebarOpen on md+
    // widths (Desktop Chrome is 1280px). The rail collapses (inert + hidden).
    await page.keyboard.press("Control+Shift+S");
    await expect(aside).toHaveAttribute("aria-hidden", "true");

    // Toggling again restores it.
    await page.keyboard.press("Control+Shift+S");
    await expect(aside).toHaveAttribute("aria-hidden", "false");
  });
});

test.describe("app shell — mobile drawer", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the header menu opens the nav drawer; browser Back closes it", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // The touch-only header menu button (md:hidden) opens the mobile drawer.
    await page.getByRole("button", { name: "Open sidebar" }).click();
    const drawer = page.getByRole("dialog", { name: "Navigation" });
    await expect(drawer).toBeVisible();

    // Opening pushed a history entry (app-shell.tsx:69-71); the browser Back
    // button fires popstate → onPopState → the drawer closes.
    await page.goBack();
    await expect(drawer).toHaveCount(0);
  });
});
