// ARIA structure and keyboard reach for the surfaces the UI audit's axe pass
// flagged: the command palette listbox, the model picker (desktop menu and
// mobile sheet), the toast stack, markdown horizontal scrollers and the auth
// dialog's scroll body. Each test runs only the axe rules its defect tripped,
// so an unrelated rule elsewhere on the page cannot fail it.

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "./coverage-fixture";

import { modelModeTrigger, waitForBootstrap } from "./helpers";

async function axeViolations(page: Page, rules: string[]) {
  const res = await new AxeBuilder({ page }).withRules(rules).analyze();
  return res.violations.map((v) => ({
    id: v.id,
    targets: v.nodes.map((n) => n.target.join(" ")),
  }));
}

async function sendAndSettle(page: Page, prompt: string) {
  await page.getByTestId("composer-textarea").fill(prompt);
  await page.getByTestId("composer-send").click();
  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toHaveAttribute("data-status", "done", {
    timeout: 20_000,
  });
  return assistant;
}

test.describe("desktop", () => {
  test("command palette: options sit in listbox > group, arrow keys still move", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await page.keyboard.press("ControlOrMeta+k");
    const input = page.getByPlaceholder("Search actions & chats…");
    await expect(input).toBeVisible();

    const listbox = page.getByRole("listbox", { name: "Commands" });
    await expect(listbox.getByRole("group").first()).toBeVisible();
    await expect(listbox.locator("li, ul")).toHaveCount(0);
    expect(
      await axeViolations(page, [
        "aria-required-children",
        "aria-required-parent",
        "listitem",
        "list",
      ]),
    ).toEqual([]);

    const first = await input.getAttribute("aria-activedescendant");
    await input.press("ArrowDown");
    const next = await input.getAttribute("aria-activedescendant");
    expect(next).not.toBe(first);
    await expect(page.locator(`[id="${next}"]`)).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("model picker: Advanced is a menu item reachable by arrow keys", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await modelModeTrigger(page).focus();
    await page.keyboard.press("Enter");
    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible();
    expect(await axeViolations(page, ["aria-required-children"])).toEqual([]);

    const advanced = menu.getByTestId("picker-advanced");
    await expect(advanced).toHaveAttribute("role", "menuitem");
    await expect(advanced).toHaveAttribute("aria-expanded", "false");
    // Arrow keys walk the menu's roving focus; the End key lands on the last
    // item, which is Advanced while the section is collapsed.
    await page.keyboard.press("End");
    await expect(advanced).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(advanced).toHaveAttribute("aria-expanded", "true");
    await expect(menu).toBeVisible();
    expect(await axeViolations(page, ["aria-required-children"])).toEqual([]);
  });

  test("toast stack: a status toast is not an <li> in an <ol>", async ({
    page,
  }) => {
    await page.route(/\/api\/conversations$/, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ title: "Couldn't create conversation" }),
        });
        return;
      }
      await route.continue();
    });
    await page.goto("/");
    await waitForBootstrap(page);
    await page.getByTestId("composer-textarea").fill("This send will fail");
    await page.getByTestId("composer-send").click();
    await expect(page.getByRole("alert", { name: "Error" })).toBeVisible({
      timeout: 10_000,
    });
    expect(await axeViolations(page, ["list", "listitem"])).toEqual([]);
  });

  test("markdown: an overflowing code block becomes a focusable named region", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const assistant = await sendAndSettle(page, "RICH_MARKDOWN: show a snippet");
    const pre = assistant.locator('[data-streamdown="code-block-body"] pre');
    await expect(pre).toBeVisible();

    // The fixture's one-line snippet fits, so it stays out of the Tab order.
    await expect(pre).not.toHaveAttribute("tabindex", /.*/);

    // Narrow the column until the line no longer fits, as a long model line
    // or a phone width would. Sizing the markdown root (not editing the code)
    // keeps React's own render of the block untouched.
    const root = assistant.locator(".chat-md").first();
    await root.evaluate((el) => el.style.setProperty("max-width", "96px"));
    await expect(pre).toHaveAttribute("tabindex", "0");
    await expect(pre).toHaveAttribute("role", "region");
    await expect(pre).toHaveAttribute("aria-label", "Scrollable python code");
    expect(await axeViolations(page, ["scrollable-region-focusable"])).toEqual(
      [],
    );

    // Keyboard reach: focus lands on it and the arrow keys scroll it.
    await pre.focus();
    await expect(pre).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect
      .poll(() => pre.evaluate((el) => el.scrollLeft))
      .toBeGreaterThan(0);

    // Once it fits again it leaves the Tab order.
    await root.evaluate((el) => el.style.removeProperty("max-width"));
    await expect(pre).not.toHaveAttribute("tabindex", /.*/);
  });

  test("auth dialog: the scroll body leaves room for the field focus ring", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

    // --focus-ring draws 4px outside the field; the nearest scroller clips
    // anything past its padding box, so each side needs >= 4px of room.
    const room = await page.locator('input[type="email"]').evaluate((el) => {
      let sc = el.parentElement;
      while (sc && getComputedStyle(sc).overflowY !== "auto") {
        sc = sc.parentElement;
      }
      const a = el.getBoundingClientRect();
      const c = sc!.getBoundingClientRect();
      return { left: a.left - c.left, right: c.right - a.right };
    });
    expect(room.left).toBeGreaterThanOrEqual(4);
    expect(room.right).toBeGreaterThanOrEqual(4);
  });
});

test.describe("mobile sheet", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });

  test("model sheet toggles are single switches named by their label", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await modelModeTrigger(page).click();
    const sheet = page.getByRole("dialog", { name: "Model and reasoning" });
    await expect(sheet).toBeVisible();

    expect(await axeViolations(page, ["nested-interactive"])).toEqual([]);

    const json = sheet.getByRole("switch", { name: "JSON output", exact: true });
    await expect(json).toHaveAttribute("aria-checked", "false");
    await expect(json.locator("button, [role=switch], [tabindex]")).toHaveCount(0);
    // tap(), not click(): the sheet's swipe-dismiss captures a mouse pointer
    // on pointerdown, which retargets a synthetic mouse click to the sheet.
    await json.tap();
    await expect(json).toHaveAttribute("aria-checked", "true");

    // No section heading repeats the one row it titles.
    await expect(sheet.getByText("JSON output", { exact: true })).toHaveCount(1);
  });
});
