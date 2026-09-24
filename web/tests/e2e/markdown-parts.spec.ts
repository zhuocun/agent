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

test.describe("markdown tables", () => {
  // UI-LAYOUT-2 / UI-LAYOUT-11. `.chat-md` sets `overflow-wrap: anywhere` so an
  // unbroken URL wraps in prose; inherited into cells, it shrank every column's
  // min-content to one character, so tables squeezed to fit and broke words
  // mid-letter instead of scrolling. The table and the prose are injected, as
  // UI-LAYOUT-11 prescribes: the property under test is the stylesheet.
  for (const width of [320, 1280]) {
    test(`cells wrap at word boundaries and a wide table scrolls at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/");
      await waitForBootstrap(page);
      await sendAndSettle(page, "NO_REASONING: keep it short");

      const result = await page.evaluate(() => {
        const md = [...document.querySelectorAll(".chat-md")].pop()!;
        const p = document.createElement("p");
        p.textContent = "https://example.com/" + "a".repeat(280);
        md.append(p);
        const cols = ["Region", "Latency p50", "Latency p95", "Error rate", "Notes", "Owner"];
        const row = ["ap-southeast-1", "120 ms", "480 ms", "0.02%", "Primary database region, warm", "platform"];
        const table = document.createElement("table");
        table.innerHTML =
          `<thead><tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead>` +
          `<tbody>${[0, 1, 2].map(() => `<tr>${row.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>`;
        md.append(table);
        // A word split mid-letter paints as more than one line box.
        const splitWords: string[] = [];
        for (const cell of table.querySelectorAll("th, td")) {
          const text = cell.firstChild as Text;
          for (const m of text.data.matchAll(/[A-Za-z]+/g)) {
            const range = document.createRange();
            range.setStart(text, m.index);
            range.setEnd(text, m.index + m[0].length);
            if (range.getClientRects().length > 1) splitWords.push(m[0]);
          }
        }
        // The scroll container is the table or its nearest horizontally
        // scrollable ancestor inside the message, whichever owns overflow.
        let scroller: HTMLElement | null = table;
        while (scroller && scroller !== md) {
          const ox = getComputedStyle(scroller).overflowX;
          if (
            (ox === "auto" || ox === "scroll") &&
            scroller.scrollWidth > scroller.clientWidth + 1
          )
            break;
          scroller = scroller.parentElement;
        }
        const scrolls = !!scroller && scroller !== md;
        return {
          splitWords,
          tableScrolls: scrolls,
          // At 1280 the table may fit; then no scroller is required.
          tableFits: table.scrollWidth <= md.clientWidth + 1,
          prose: { sw: p.scrollWidth, cw: p.clientWidth },
          md: { sw: md.scrollWidth, cw: md.clientWidth },
          doc: document.documentElement.scrollWidth,
          vw: window.innerWidth,
        };
      });

      expect(result.splitWords).toEqual([]);
      // Six columns never fit a phone column without breaking words, so the
      // table must scroll there; wherever it overflows, something scrolls it.
      if (width === 320) expect(result.tableScrolls).toBe(true);
      if (!result.tableFits) expect(result.tableScrolls).toBe(true);
      // The long URL still wraps inside prose, and nothing widens the page.
      expect(result.prose.sw).toBeLessThanOrEqual(result.prose.cw + 1);
      expect(result.md.sw).toBeLessThanOrEqual(result.md.cw + 1);
      expect(result.doc).toBeLessThanOrEqual(result.vw);
    });
  }
});
