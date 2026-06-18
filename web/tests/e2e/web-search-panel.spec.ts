// Web-search consolidation — FE↔BE e2e against the real BE + fake provider.
//
// Web-search tool calls and the search status line fold into a single
// `web-search-panel` instead of separate tool cards plus a status row.

import { expect, test, type Page } from "@playwright/test";

import { modelModeTrigger, waitForBootstrap } from "./helpers";

async function enableWebSearch(page: Page): Promise<void> {
  await modelModeTrigger(page).click();
  await page.getByTestId("picker-advanced").click();
  const toggle = page.getByTestId("web-search-toggle");
  await expect(toggle).toBeVisible({ timeout: 5_000 });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
}

test.describe("web search panel consolidation", () => {
  test("a single web-search turn renders one consolidated panel with live status", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableWebSearch(page);

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("What is the latest on Playwright?");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });
    const panel = assistant.getByTestId("web-search-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });

    await expect(assistant).toHaveAttribute("data-status", /submitted|streaming/, {
      timeout: 15_000,
    });
    await expect(panel.getByText("Searching the web…")).toBeVisible({
      timeout: 15_000,
    });

    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect(panel.getByTestId("web-search-trigger")).toContainText("1 query");
    await expect(assistant.getByTestId("tool-call-part")).toHaveCount(0);
    await expect(assistant.getByText("Searching the web…")).toHaveCount(0);
  });

  test("multiple web-search queries fold into one panel", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableWebSearch(page);

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("WEB_SEARCH_MULTI: rust vs go");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    const panel = assistant.getByTestId("web-search-panel");
    await expect(panel).toHaveCount(1);
    await expect(panel.getByTestId("web-search-trigger")).toContainText("2 queries");

    await panel.getByTestId("web-search-trigger").click();
    await expect(panel.getByTestId("tool-result-part")).toHaveCount(2);
    await expect(assistant.getByTestId("tool-call-part")).toHaveCount(0);
  });
});
