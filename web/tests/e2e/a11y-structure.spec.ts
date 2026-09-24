// ARIA structure and keyboard reach for the surfaces the UI audit's axe pass
// flagged: the command palette listbox, the model picker (desktop menu and
// mobile sheet), the toast stack, markdown horizontal scrollers and the auth
// dialog's scroll body. Each test runs only the axe rules its defect tripped,
// so an unrelated rule elsewhere on the page cannot fail it.

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect, test } from "./coverage-fixture";

import { BE_URL, modelModeTrigger, waitForBootstrap } from "./helpers";

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

    // ArrowUp from the first option wraps to the last, below the fold; the
    // list must scroll it into view since focus never leaves the input.
    await input.press("ArrowUp");
    await input.press("ArrowUp");
    const last = await input.getAttribute("aria-activedescendant");
    await expect(page.locator(`[id="${last}"]`)).toBeInViewport({ ratio: 1 });
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

    // Once it fits again it leaves the Tab order, but not while it holds
    // focus: dropping tabindex then would throw focus to <body>.
    await root.evaluate((el) => el.style.removeProperty("max-width"));
    await page.waitForTimeout(400);
    await expect(pre).toBeFocused();
    await expect(pre).toHaveAttribute("tabindex", "0");
    await pre.evaluate((el) => el.blur());
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

// The fake provider emits no table, so one turn's answer is swapped in flight
// for a wide one (the real stream is fetched so the turn persists). Same
// technique as the UI audit harness.
const WIDE_TABLE = [
  "| Region | Latency p50 | Latency p95 | Error rate | Notes | Owner |",
  "| --- | --- | --- | --- | --- | --- |",
  "| ap-southeast-1 | 120 ms | 480 ms | 0.02% | Primary database region, warm | platform |",
  "| us-east-1 | 210 ms | 900 ms | 0.10% | Cross-region reads only | infra |",
].join("\n");

test.describe("phone width", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("markdown: a wide table is a focusable scroller with a visible focus ring", async ({
    page,
  }) => {
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      const req = route.request();
      if (req.method() !== "POST" || !(req.postData() ?? "").includes("WIDE_TABLE")) {
        await route.fallback();
        return;
      }
      const resp = await route.fetch();
      const frames = (await resp.text()).replace(/\r\n/g, "\n").split(/\n\n/);
      const kept = frames.filter((f) => !/^event: answer_delta/m.test(f));
      const at = kept.findIndex((f) => /^event: terminal/m.test(f));
      const table = `event: answer_delta\ndata: ${JSON.stringify({ text: WIDE_TABLE })}`;
      if (at >= 0) kept.splice(at, 0, table);
      else kept.push(table);
      await route.fulfill({ response: resp, body: kept.join("\n\n") });
    });
    await page.goto("/");
    await waitForBootstrap(page);
    const assistant = await sendAndSettle(page, "WIDE_TABLE: latency by region");

    // Whichever box scrolls (the table itself, or Streamdown's wrapper) is
    // the one marked.
    const region = assistant.locator("[data-scroll-region]");
    await expect(region).toHaveCount(1);
    await expect(region).toHaveAttribute("tabindex", "0");
    await expect(region).toHaveAttribute("aria-label", "Scrollable table");
    expect(await region.locator("table").count().then(async (n) =>
      n > 0 || (await region.evaluate((el) => el.tagName === "TABLE")),
    )).toBe(true);
    expect(await axeViolations(page, ["scrollable-region-focusable"])).toEqual(
      [],
    );

    // Reach it by Tab (keyboard modality) and check the inset ring paints.
    await region.focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");
    await expect(region).toBeFocused();
    const shadow = await region.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(shadow).not.toBe("none");
    expect(shadow).toContain("inset");
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

async function openSettings(page: Page) {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  const dialog = page.getByRole("dialog", { name: "Settings" });
  await expect(dialog).toBeVisible();
  return dialog;
}

test.describe("scroll regions", () => {
  // A short viewport so the tall message-actions menu has to scroll, as it
  // does on a laptop once a thread fills the screen.
  test.use({ viewport: { width: 1280, height: 520 } });

  test("message overflow menu: a pointer-opened scrolling menu is keyboard reachable", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await sendAndSettle(page, "Hello overflow");
    await page.getByTestId("message-actions-overflow").last().click();
    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible();
    expect(await menu.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(
      true,
    );
    expect(await axeViolations(page, ["scrollable-region-focusable"])).toEqual(
      [],
    );
    // Arrow keys still drive the menu, and End scrolls the last row in.
    await page.keyboard.press("End");
    const last = menu.locator('[role^="menuitem"]').last();
    await expect(last).toBeFocused();
    await expect(last).toBeInViewport();
  });

  test("settings: the read-only Models and Shortcuts scrollers take focus", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const dialog = await openSettings(page);
    for (const [tab, name] of [
      ["Models", "Models and data policies"],
      ["Shortcuts", "Keyboard shortcuts"],
    ] as const) {
      await dialog.getByRole("tab", { name: tab }).click();
      const region = dialog.getByRole("region", { name, exact: true });
      await expect(region).toHaveAttribute("tabindex", "0");
      expect(
        await axeViolations(page, ["scrollable-region-focusable"]),
      ).toEqual([]);
      // Keyboard focus draws the inset ring, and the keyboard scrolls it.
      await region.focus();
      await page.keyboard.press("Tab");
      await page.keyboard.press("Shift+Tab");
      await expect(region).toBeFocused();
      expect(
        await region.evaluate((el) => getComputedStyle(el).boxShadow),
      ).toContain("inset");
      await page.keyboard.press("PageDown");
      await expect
        .poll(() => region.evaluate((el) => el.scrollTop))
        .toBeGreaterThan(0);
    }
  });
});

test.describe("touch tablet", () => {
  test.use({
    viewport: { width: 820, height: 1180 },
    hasTouch: true,
    isMobile: true,
  });

  test("settings disclosure toggles meet the 44px touch floor", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const dialog = await openSettings(page);
    for (const id of [
      "byok-section-toggle",
      "custom-instructions-toggle",
      "project-defaults-toggle",
      "advanced-privacy-toggle",
    ]) {
      const box = await dialog.getByTestId(id).boundingBox();
      expect(box?.height, id).toBeGreaterThanOrEqual(44);
    }
  });
});

test.describe("desktop density", () => {
  test("settings disclosure toggles keep their compact desktop height", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    const dialog = await openSettings(page);
    const box = await dialog
      .getByTestId("advanced-privacy-toggle")
      .boundingBox();
    expect(box?.height).toBeLessThan(44);
  });
});

test.describe("phone temporary chat", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });

  test("turning on Temporary chat closes the menu so Turn off is not covered", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await page.getByRole("button", { name: "Chat menu" }).first().click();
    await page
      .getByRole("menuitemcheckbox", { name: "Temporary chat" })
      .click();
    const banner = page.getByTestId("temporary-chat-banner");
    await expect(banner).toBeVisible();
    await expect(page.getByRole("menu")).toHaveCount(0);
    expect(await axeViolations(page, ["target-size"])).toEqual([]);
    await banner.getByRole("button", { name: "Turn off" }).click();
    await expect(banner).toHaveCount(0);
  });
});
