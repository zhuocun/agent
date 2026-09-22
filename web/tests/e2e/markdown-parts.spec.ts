// Rendered-message part coverage: code-block chrome, the image renderer, and
// the empty-reasoning case.
//
// These are the three surfaces `docs/design/UI_STANDARDS.md` gained clauses for
// (UI-LAYOUT-10, UI-FOCUS-9, UI-PERF-8, UI-TRUST-12) and the three the suite
// could not reach before: no fake-provider marker emitted a fenced code block,
// an image, or an answer without reasoning. `RICH_MARKDOWN:` and
// `NO_REASONING:` in `api/app/providers/fake.py` exist for these tests.

import { expect, test } from "./coverage-fixture";

import { waitForBootstrap } from "./helpers";

async function sendAndSettle(
  page: import("@playwright/test").Page,
  prompt: string,
) {
  await page.getByTestId("composer-textarea").fill(prompt);
  await page.getByTestId("composer-send").click();
  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toHaveAttribute("data-status", "done", {
    timeout: 20_000,
  });
  return assistant;
}

test.describe("code block chrome", () => {
  test("a fenced block names its language and copies the raw source", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/");
    await waitForBootstrap(page);

    const assistant = await sendAndSettle(page, "RICH_MARKDOWN: show a snippet");

    // Streamdown marks its parts with `data-streamdown`, not class names.
    const header = assistant.locator('[data-streamdown="code-block-header"]');
    await expect(header).toHaveAttribute("data-language", "python");
    await expect(header).toContainText("python");

    // The copy control must put the fence's SOURCE on the clipboard, not the
    // highlighted DOM text (PRD 01 §5.4).
    await assistant
      .locator('[data-streamdown="code-block-copy-button"]')
      .click();
    const clipboard = await page.evaluate(() =>
      navigator.clipboard.readText(),
    );
    expect(clipboard).toBe('print("hello")\n');
  });
});

test.describe("image renderer", () => {
  test("an alt-less model image gets a label, lazy loading and a capped box", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await sendAndSettle(page, "RICH_MARKDOWN: show a snippet");

    // No image anywhere in the app may omit `alt` — an omitted attribute makes
    // a screen reader announce the URL.
    const missingAlt = await page.$$eval("img", (els) =>
      els.filter((el) => !el.hasAttribute("alt")).length,
    );
    expect(missingAlt).toBe(0);

    // The fake emits `![](…)`, so a non-empty alt here can only have come from
    // the renderer's fallback (markdown-renderer.tsx).
    const content = await page.$$eval("img", (els) =>
      els
        .filter((el) => el.closest(".chat-md"))
        .map((el) => ({
          alt: el.getAttribute("alt") ?? "",
          loading: el.getAttribute("loading"),
          maxWidth: getComputedStyle(el).maxWidth,
          background: getComputedStyle(el).backgroundColor,
        })),
    );
    expect(content).toHaveLength(1);
    expect(content[0].alt.trim().length).toBeGreaterThan(0);
    expect(content[0].loading).toBe("lazy");
    // Capped to the reading column, and painting a box before the bytes land.
    expect(content[0].maxWidth).toBe("100%");
    expect(content[0].background).not.toBe("rgba(0, 0, 0, 0)");
  });
});

test.describe("reasoning panel", () => {
  test("a turn with no reasoning renders neither panel nor affordance", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const assistant = await sendAndSettle(page, "NO_REASONING: keep it short");

    await expect(assistant.getByTestId("reasoning-panel")).toHaveCount(0);
    // The affordance matters as much as the panel: a chevron with nothing
    // behind it is the likelier regression (PRD 01 §4.2 AC).
    await expect(
      assistant.getByRole("button", { name: /reasoning|thought/i }),
    ).toHaveCount(0);
    // The answer itself must still be there.
    await expect(assistant.getByTestId("assistant-answer")).not.toBeEmpty();
  });
});
