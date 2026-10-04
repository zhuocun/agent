// Status/temporary/offline banners + install-app row (Flow 19) E2E.
//
// Closes the ST-4 gaps on `temporary-chat-banner.tsx` (its dismiss callback was
// at 0% function coverage), `degraded-status-banner.tsx` (the degraded render +
// dismiss branch — driven here by a mocked degraded `/api/status`), and
// `install-app-row.tsx` (the iOS-Safari-tab path, reached by spoofing the UA),
// and `offline-banner.tsx`.

import { expect, test } from "./coverage-fixture";

import { waitForBootstrap } from "./helpers";

test.describe("temporary chat banner", () => {
  test("enabling temporary mode shows the banner; Turn off dismisses it", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Enable temporary mode from the header chat menu.
    await page.getByRole("button", { name: "Chat menu" }).click();
    await page
      .getByRole("menuitemcheckbox", { name: "Temporary chat" })
      .click();

    const banner = page.getByRole("note").filter({ hasText: "Temporary chat" });
    await expect(banner).toBeVisible();

    // The banner's own "Turn off" affordance fires onTurnOff (the previously
    // uncovered dismiss callback) → temporary mode off → banner unmounts.
    await banner.getByRole("button", { name: "Turn off" }).click();
    await expect(banner).toHaveCount(0);
  });
});

test.describe("degraded status banner", () => {
  test("a degraded platform status renders the banner, which can be dismissed", async ({
    page,
  }) => {
    // Force the public status poll to report `degraded` so the banner's
    // degraded branch renders (it normally only shows during a real incident).
    await page.route("**/api/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "degraded",
          windowSeconds: 300,
          sampleSize: 120,
          errorCount: 40,
          updatedAt: new Date().toISOString(),
        }),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    const banner = page.getByTestId("degraded-status-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("Service degraded");

    // Dismiss collapses it (setDismissed → active=false → null render).
    await banner.getByRole("button", { name: "Dismiss" }).click();
    await expect(page.getByTestId("degraded-status-banner")).toHaveCount(0);
  });

  test("an operational status renders no banner", async ({ page }) => {
    await page.route("**/api/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "operational",
          windowSeconds: 300,
          sampleSize: 120,
          errorCount: 0,
          updatedAt: new Date().toISOString(),
        }),
      });
    });

    const statusPoll = page.waitForResponse((r) =>
      /\/api\/status(\?|$)/.test(r.url()),
    );
    await page.goto("/");
    await waitForBootstrap(page);
    // The on-mount poll resolved operational → the degraded branch stays false.
    await statusPoll;
    await expect(page.getByTestId("degraded-status-banner")).toHaveCount(0);
  });
});

test.describe("install app row", () => {
  // Spoof an iOS Safari (tab, not standalone) UA: iOS Safari has no
  // `beforeinstallprompt`, so the UA sniff is the only install path there.
  test.use({
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    viewport: { width: 390, height: 844 },
  });

  test("the drawer offers Install app with Safari steps, and it can be dismissed", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByRole("button", { name: "Open sidebar" }).first().click();
    // The desktop rail stays mounted (hidden) at this width, so scope to the
    // open drawer.
    const drawer = page.locator('[data-slot="drawer-content"]');
    const row = drawer.getByTestId("install-app-row");
    await expect(row).toBeVisible();

    await row.getByRole("button", { name: "Install app" }).click();
    await expect(page.getByText("Add to Home Screen")).toBeVisible();

    await row.getByRole("button", { name: "Dismiss install suggestion" }).click();
    await expect(drawer.getByTestId("install-app-row")).toHaveCount(0);

    // Dismissal persists across reloads.
    await page.reload();
    await waitForBootstrap(page);
    await page.getByRole("button", { name: "Open sidebar" }).first().click();
    await expect(drawer.getByTestId("sidebar-new-chat")).toBeVisible();
    await expect(page.getByTestId("install-app-row")).toHaveCount(0);
  });
});

test.describe("offline banner", () => {
  test("going offline shows the banner; reconnecting hides it", async ({
    page,
    context,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await context.setOffline(true);
    await expect(page.getByTestId("offline-banner")).toBeVisible();
    await context.setOffline(false);
    await expect(page.getByTestId("offline-banner")).toHaveCount(0);
  });
});
