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

test.describe("app shell — mobile drawer surface", () => {
  test.use({ viewport: { width: 390, height: 844 }, colorScheme: "dark" });

  test("the drawer's bottom safe-area inset matches the sidebar surface", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await page.getByRole("button", { name: "Open sidebar" }).click();
    const drawer = page.getByRole("dialog", { name: "Navigation" });
    await expect(drawer).toBeVisible();
    // Let the slide-in transition settle so hit-testing sees the resting box.
    await page
      .locator('[data-slot="drawer-content"]')
      .evaluate((el) =>
        Promise.all(el.getAnimations().map((a) => a.finished.catch(() => {}))),
      );

    // Whatever paints the bottom inset (below the sidebar's own box) must be
    // the sidebar color, not the translucent drawer glass behind it.
    const colors = await page.evaluate(() => {
      const nav = document.querySelector(
        '[data-slot="drawer-content"] nav[aria-label="Conversation history"]',
      ) as HTMLElement;
      const navBottom = nav.getBoundingClientRect().bottom;
      // Horizontal centre of the drawer: clear of the dev-build indicator
      // that `next dev` pins to the bottom-left corner.
      const box = nav.closest('[data-slot="drawer-content"]')!.getBoundingClientRect();
      let el = document.elementFromPoint(
        box.left + box.width / 2,
        (navBottom + window.innerHeight) / 2,
      ) as HTMLElement | null;
      let inset = "rgba(0, 0, 0, 0)";
      while (el && inset === "rgba(0, 0, 0, 0)") {
        inset = getComputedStyle(el).backgroundColor;
        el = el.parentElement;
      }
      return {
        gap: window.innerHeight - navBottom,
        nav: getComputedStyle(nav).backgroundColor,
        inset,
      };
    });
    expect(colors.gap).toBeGreaterThan(0);
    expect(colors.inset).toBe(colors.nav);
  });
});

test.describe("app shell — smallest phone welcome", () => {
  test.use({
    viewport: { width: 320, height: 640 },
    hasTouch: true,
    isMobile: true,
  });

  test("the welcome hero starts below the header instead of under it", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const connect = page.getByRole("button", { name: /Connect your API key/ });
    await expect(connect).toBeVisible();
    const header = await page
      .locator('header[aria-label="Chat toolbar"]:visible')
      .first()
      .boundingBox();
    const connectBox = await connect.boundingBox();
    expect(header).not.toBeNull();
    expect(connectBox).not.toBeNull();
    expect(connectBox!.y).toBeGreaterThanOrEqual(header!.y + header!.height);
  });
});
