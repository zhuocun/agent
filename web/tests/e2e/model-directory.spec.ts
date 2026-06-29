// Model & data-policy directory + public status page — runtime coverage.
//
// Drives the real shell + real bootstrap (no stubbing) for the model directory
// and the operational /status page. For the degraded/error status branches we
// stub the PUBLIC /api/status route (the live BE reports operational off the
// fake provider's clean telemetry, so a degraded verdict can't be coerced
// cheaply): a degraded verdict flips the in-shell banner on and renders the
// /status degraded view, and a 5xx exercises the status page's error + retry.

import { expect, test, type Page } from "./coverage-fixture";

import { waitForBootstrap } from "./helpers";

// A degraded platform-status payload (shape mirrors PlatformStatus in
// web/src/lib/types.ts). Drives both the in-shell DegradedStatusBanner and the
// /status page's degraded body.
const DEGRADED_STATUS = {
  status: "degraded",
  windowSeconds: 300,
  sampleSize: 240,
  errorCount: 48,
  updatedAt: new Date().toISOString(),
} as const;

const OPERATIONAL_STATUS = {
  status: "operational",
  windowSeconds: 300,
  sampleSize: 240,
  errorCount: 0,
  updatedAt: new Date().toISOString(),
} as const;

async function openSettings(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
}

test.describe("model directory & platform status", () => {
  test("opens the model directory and renders provider policies", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await openSettings(page);
    await page.getByTestId("open-model-directory-button").click();

    const dialog = page.getByTestId("model-directory-dialog");
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("heading", { name: "Models & data policies" }),
    ).toBeVisible();

    // The registry-derived provider cards render. DeepSeek carries a published
    // policy (data residency from the registry), so its policy block is shown.
    const deepseek = dialog.locator('[data-provider="deepseek"]');
    await expect(deepseek).toBeVisible();
    await expect(deepseek.getByTestId("data-policy")).toBeVisible();
    await expect(deepseek.getByText("Data residency: China")).toBeVisible();
    // At least one tier row with a model label + price comparison.
    await expect(deepseek.getByTestId("directory-tier").first()).toBeVisible();

    // The pending Gemini route has no published policy — it renders honestly
    // as "unavailable", never a fabricated guess.
    const gemini = dialog.locator('[data-provider="gemini"]');
    await expect(gemini).toBeVisible();
    await expect(gemini.getByTestId("policy-unavailable")).toBeVisible();

    await dialog.screenshot({
      path: "/opt/cursor/artifacts/model_directory_dialog.png",
    });
  });

  test("public status page renders an operational summary", async ({
    page,
  }) => {
    await page.goto("/status");

    const status = page.getByTestId("platform-status");
    await expect(status).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("heading", { name: "All systems operational" }),
    ).toBeVisible();

    await page.screenshot({
      path: "/opt/cursor/artifacts/platform_status_page.png",
    });
  });

  test("a degraded platform routes the in-shell banner through to the /status degraded view", async ({
    page,
  }) => {
    await page.route("**/api/status", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DEGRADED_STATUS),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    // The banner only renders when the platform reports degraded.
    const banner = page.getByTestId("degraded-status-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });

    // "View status" links through to the full /status page (still degraded).
    // It renders via Base UI's Button with `render={<Link/>}` (nativeButton
    // false), i.e. an <a href> carrying role="button" — so match the button
    // role, not link.
    await banner.getByRole("button", { name: "View status" }).click();
    await expect(page).toHaveURL(/\/status$/);

    const status = page.getByTestId("platform-status");
    await expect(status).toBeVisible({ timeout: 15_000 });
    await expect(status.locator('[data-status="degraded"]')).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Some requests are failing" }),
    ).toBeVisible();

    await page.screenshot({
      path: "/opt/cursor/artifacts/platform_status_degraded.png",
    });
  });

  test("the degraded banner can be dismissed", async ({ page }) => {
    await page.route("**/api/status", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(DEGRADED_STATUS),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    const banner = page.getByTestId("degraded-status-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });

    await banner.getByRole("button", { name: "Dismiss" }).click();
    await expect(banner).toHaveCount(0);
  });

  test("the status page shows a retryable error state and recovers", async ({
    page,
  }) => {
    // Fail the first load, then recover on retry — exercises the status view's
    // error branch AND the retry path that re-fetches into the ready state.
    let failing = true;
    await page.route("**/api/status", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      if (failing) {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "INTERNAL",
              severity: "error",
              title: "Server error",
              body: "boom",
            },
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(OPERATIONAL_STATUS),
      });
    });

    await page.goto("/status");

    await expect(
      page.getByRole("heading", { name: "Couldn't load platform status" }),
    ).toBeVisible({ timeout: 15_000 });

    failing = false;
    await page.getByRole("button", { name: "Try again" }).click();

    await expect(page.getByTestId("platform-status")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("heading", { name: "All systems operational" }),
    ).toBeVisible();
  });
});
