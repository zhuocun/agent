// Model & data-policy directory + public status page — runtime coverage.
//
// Drives the real shell + real bootstrap (no stubbing). Opens Settings →
// "Models & data policies" and asserts the registry-derived provider cards
// render with their data policy (incl. the pending, null-policy route showing
// "policy unavailable"). Also asserts the public /status page renders an
// operational summary against the live BE.

import { expect, test, type Page } from "@playwright/test";

import { waitForBootstrap } from "./helpers";

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
});
