// Touch and pointer target floors (UI-TOUCH-1 / -2 / -5) on the controls the
// UI audit found undersized: inline citation markers, the reasoning and
// sources disclosure toggles, and the desktop-rail "Advanced search" and
// "Select" affordances a touch tablet also receives.
//
// The hit region is measured the way UI-TOUCH-1 defines it: the element's box
// grown by any absolutely positioned ::before / ::after hit-slop.

import { expect, test, type Locator, type Page } from "./coverage-fixture";

import { modelModeTrigger, waitForBootstrap } from "./helpers";

async function hitRegion(locator: Locator): Promise<{ w: number; h: number }> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    let w = r.width;
    let h = r.height;
    for (const pseudo of ["::before", "::after"]) {
      const ps = getComputedStyle(el, pseudo);
      if (ps.content === "none" || ps.position !== "absolute") continue;
      const px = (v: string) => (v.endsWith("px") ? parseFloat(v) : 0);
      w = Math.max(w, r.width - px(ps.left) - px(ps.right));
      h = Math.max(h, r.height - px(ps.top) - px(ps.bottom));
    }
    return { w, h };
  });
}

async function expectFloor(locator: Locator, floor: number): Promise<void> {
  await expect(locator).toBeVisible();
  const { w, h } = await hitRegion(locator);
  expect(w, "hit region width").toBeGreaterThanOrEqual(floor);
  expect(h, "hit region height").toBeGreaterThanOrEqual(floor);
}

async function sendWebSearchTurn(page: Page): Promise<Locator> {
  await modelModeTrigger(page).click();
  await page.getByTestId("picker-advanced").click();
  const toggle = page.getByTestId("web-search-toggle");
  await expect(toggle).toBeVisible({ timeout: 5_000 });
  await toggle.click();
  // The desktop menu and the phone sheet expose different roles; both name
  // the on state.
  await expect(toggle).toHaveAttribute("aria-label", "Web search: on");
  await page.keyboard.press("Escape");

  await page.getByTestId("composer-textarea").fill("What is the latest on Playwright?");
  await page.getByTestId("composer-send").click();
  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toHaveAttribute("data-status", "done", {
    timeout: 15_000,
  });
  await expect(assistant.getByTestId("citation-marker").first()).toBeVisible({
    timeout: 15_000,
  });
  return assistant;
}

test.describe("pointer target floor", () => {
  test("citation markers meet the 24 px pointer floor", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const assistant = await sendWebSearchTurn(page);
    await expectFloor(assistant.getByTestId("citation-marker").first(), 24);
  });
});

test.describe("touch tablet target floor", () => {
  // A touch tablet at >=768 px gets the desktop layout; the 44 px floor must
  // follow the pointer, not the width (UI-TOUCH-5).
  test.use({ viewport: { width: 820, height: 1180 }, hasTouch: true });

  test("disclosure toggles, citations and rail affordances reach 44 px", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const assistant = await sendWebSearchTurn(page);

    await expectFloor(assistant.getByTestId("citation-marker").first(), 44);
    await expectFloor(
      assistant.getByTestId("reasoning-panel").getByRole("button").first(),
      44,
    );
    await expectFloor(
      assistant.getByTestId("sources-panel").getByRole("button").first(),
      44,
    );
    await expectFloor(page.getByTestId("sidebar-advanced-search"), 44);
    await expectFloor(page.getByTestId("sidebar-select-toggle"), 44);
  });
});

test.describe("phone target floor", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });

  test("citation markers reach 44 px on a phone", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const assistant = await sendWebSearchTurn(page);
    await expectFloor(assistant.getByTestId("citation-marker").first(), 44);
  });
});
