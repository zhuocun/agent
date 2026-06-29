// Status/temporary banners + iOS install coachmark (Flow 19) E2E.
//
// Closes the ST-4 gaps on `temporary-chat-banner.tsx` (its dismiss callback was
// at 0% function coverage), `degraded-status-banner.tsx` (the degraded render +
// dismiss branch — driven here by a mocked degraded `/api/status`), and
// `install-coachmark.tsx` (the iOS-Safari-tab path, reached by spoofing the UA).

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

test.describe("iOS install coachmark", () => {
  // Spoof an iOS Safari (tab, not standalone) UA so isIosSafariTab() passes —
  // iOS Safari has no `beforeinstallprompt`, so the UA sniff is the only path.
  test.use({
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    viewport: { width: 390, height: 844 },
  });

  test("shows the Add-to-Home-Screen hint and dismisses it", async ({ page }) => {
    // The coachmark lives in the root layout, so the public /status route shows
    // it without a BE bootstrap. It defers ~1.2s after mount before appearing.
    await page.goto("/status");

    const hint = page.getByText(/Install Olune/);
    await expect(hint).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Dismiss install hint" }).click();
    await expect(page.getByText(/Install Olune/)).toHaveCount(0);
  });
});
