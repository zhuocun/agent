// FE-side coverage for the spend-analytics dashboard (PRD 05 §4.5 D27).
//
// Mocks the BE so the FE half is exercised deterministically: a mocked
// /api/bootstrap mints a guest, and /api/account/spend returns a fixed
// analytics payload that echoes the requested `days` back as `rangeDays`. The
// spec opens Settings → Account and asserts the inline Usage & spend panel:
// totals, the daily bars, the by-model + top-conversation lists, the export
// affordances, and that switching the range re-fetches.

import { promises as fs } from "node:fs";

import { expect, test, type Page } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

function bootstrapPayload() {
  return {
    account: {
      name: "Guest",
      email: "",
      planLabel: "Free",
      byokEnabled: false,
      isAnonymous: true,
    },
    preferences: {
      defaultTierId: "fast",
      temporaryByDefault: false,
      trainingOptIn: false,
      sendOnEnter: true,
      autoExpandReasoning: false,
      telemetryEnabled: true,
      customInstructions: "",
      retentionDays: 30,
      monthlyBudgetUsd: null,
      perConversationBudgetUsd: null,
    },
    usage: {
      used: 0,
      limit: 1000,
      periodLabel: "this month",
      isByok: false,
      monthlySpendUsd: 0,
      creditBalanceUsd: 0,
    },
    modelTiers: [],
    suggestions: [],
    conversations: [],
  };
}

// A spend payload whose `daily` zero-fills the requested window and whose
// `rangeDays` echoes the requested `days` (so the FE's stale-detection clears).
function spendPayload(days: number) {
  const daily = Array.from({ length: days }, (_, i) => ({
    date: `2026-05-${String(i + 1).padStart(2, "0")}`,
    costUsd: i === days - 1 ? 0.3 : i === 0 ? 0.5 : 0,
    messageCount: i === days - 1 ? 1 : i === 0 ? 1 : 0,
  }));
  return {
    rangeDays: days,
    currency: "USD",
    survivingMessagesUsd: 0.8,
    cumulativeMeterUsd: 1.25,
    daily,
    byModel: [
      {
        label: "DeepSeek V4 Pro",
        tierId: "pro",
        providerId: "deepseek",
        costUsd: 0.5,
        messageCount: 1,
      },
      {
        label: "DeepSeek V4 Flash",
        tierId: "fast",
        providerId: "deepseek",
        costUsd: 0.3,
        messageCount: 1,
      },
    ],
    byConversation: [
      {
        conversationId: "c1",
        title: "Alpha thread",
        costUsd: 0.5,
        messageCount: 1,
      },
      {
        conversationId: "c2",
        title: "Beta thread",
        costUsd: 0.3,
        messageCount: 1,
      },
    ],
  };
}

async function mockBootstrap(page: Page): Promise<void> {
  await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(bootstrapPayload()),
    });
  });
}

async function mockSpend(
  page: Page,
  onRequest?: (days: number) => void,
): Promise<void> {
  await page.route(`${BE_URL}/api/account/spend**`, async (route) => {
    const url = new URL(route.request().url());
    const days = Number(url.searchParams.get("days") ?? "30");
    onRequest?.(days);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(spendPayload(days)),
    });
  });
}

// A spend payload whose `daily`, `byModel`, and `byConversation` are all empty
// for an account that has spent nothing in the window. `rangeDays` still echoes
// the request so the FE clears its stale-detection (`loading` resolves false).
function emptySpendPayload(days: number) {
  return {
    rangeDays: days,
    currency: "USD",
    survivingMessagesUsd: 0,
    cumulativeMeterUsd: 0,
    daily: [],
    byModel: [],
    byConversation: [],
  };
}

// Mirror of `spendPayload` but with a label that contains a comma + a quote so
// the CSV export's `csvField` quoting/escaping path runs on export.
function spendPayloadWithSpecialChars(days: number) {
  const base = spendPayload(days);
  return {
    ...base,
    byConversation: [
      {
        conversationId: "c1",
        title: 'Alpha, "beta" thread',
        costUsd: 0.5,
        messageCount: 1,
      },
    ],
  };
}

async function openSpendPanel(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("dialog", { name: "Settings" })).toBeVisible();
  await expect(page.getByTestId("spend-analytics-panel")).toBeVisible();
}

test.describe("spend analytics dashboard", () => {
  test("opens from settings and renders both totals, bars, and breakdowns", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await mockSpend(page);

    await page.goto("/");
    await waitForBootstrap(page);
    await openSpendPanel(page);

    // Two clearly-labelled, honest totals. Scope the label lookup to each
    // total's card (its testid value's parent) so the same words inside the
    // explanation copy don't trip strict mode.
    const cumulativeCard = page
      .getByTestId("spend-total-cumulative")
      .locator("..");
    const survivingCard = page
      .getByTestId("spend-total-surviving")
      .locator("..");
    await expect(
      cumulativeCard.getByText("Cumulative meter", { exact: true }),
    ).toBeVisible();
    await expect(
      survivingCard.getByText("Surviving messages", { exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("spend-total-cumulative")).toHaveText("$1.25");
    await expect(page.getByTestId("spend-total-surviving")).toHaveText("$0.80");

    // Daily CSS bar chart zero-fills the 30-day window (default range).
    const bars = page.getByTestId("spend-daily-bars").locator("> div");
    await expect(bars).toHaveCount(30);

    // By-model and top-conversation breakdowns.
    const byModel = page.getByTestId("spend-by-model");
    await expect(byModel.getByText("DeepSeek V4 Pro")).toBeVisible();
    await expect(byModel.getByText("DeepSeek V4 Flash")).toBeVisible();
    const byConvo = page.getByTestId("spend-by-conversation");
    await expect(byConvo.getByText("Alpha thread")).toBeVisible();
    await expect(byConvo.getByText("Beta thread")).toBeVisible();

    // Export affordances are enabled once data is loaded.
    await expect(page.getByTestId("spend-export-csv")).toBeEnabled();
    await expect(page.getByTestId("spend-export-json")).toBeEnabled();
  });

  test("switching the range re-fetches the selected window", async ({
    page,
  }) => {
    const requestedDays: number[] = [];
    await mockBootstrap(page);
    await mockSpend(page, (days) => requestedDays.push(days));

    await page.goto("/");
    await waitForBootstrap(page);
    await openSpendPanel(page);

    // Default request is the 30-day window.
    await expect.poll(() => requestedDays.includes(30)).toBe(true);

    // Switching to 7d re-fetches and the bar count follows the new window.
    await page.getByTestId("spend-range-7").click();
    await expect.poll(() => requestedDays.includes(7)).toBe(true);
    await expect(
      page.getByTestId("spend-daily-bars").locator("> div"),
    ).toHaveCount(7);
  });

  test("exporting CSV and JSON downloads the loaded data (with CSV field escaping)", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await page.route(`${BE_URL}/api/account/spend**`, async (route) => {
      const url = new URL(route.request().url());
      const days = Number(url.searchParams.get("days") ?? "30");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(spendPayloadWithSpecialChars(days)),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);
    await openSpendPanel(page);

    // Wait for data to land so the export buttons leave their disabled state.
    await expect(page.getByTestId("spend-export-csv")).toBeEnabled();

    // CSV export: capture the download and assert the file name + that the
    // comma/quote-bearing conversation title was CSV-escaped (wrapped in quotes
    // with the inner quotes doubled).
    const csvDownloadPromise = page.waitForEvent("download");
    await page.getByTestId("spend-export-csv").click();
    const csvDownload = await csvDownloadPromise;
    expect(csvDownload.suggestedFilename()).toBe("spend-30d.csv");
    const csvPath = await csvDownload.path();
    const csvText = await fs.readFile(csvPath, "utf8");
    expect(csvText).toContain('"Alpha, ""beta"" thread"');
    expect(csvText).toContain("Cumulative meter");
    expect(csvText).toContain("DeepSeek V4 Pro");

    // JSON export: capture the download and assert it round-trips the payload.
    const jsonDownloadPromise = page.waitForEvent("download");
    await page.getByTestId("spend-export-json").click();
    const jsonDownload = await jsonDownloadPromise;
    expect(jsonDownload.suggestedFilename()).toBe("spend-30d.json");
    const jsonPath = await jsonDownload.path();
    const parsed = JSON.parse(await fs.readFile(jsonPath, "utf8")) as {
      rangeDays: number;
      byConversation: Array<{ title: string }>;
    };
    expect(parsed.rangeDays).toBe(30);
    expect(parsed.byConversation[0]!.title).toBe('Alpha, "beta" thread');
  });

  test("an empty window shows the no-spend copy and hides the breakdowns", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await page.route(`${BE_URL}/api/account/spend**`, async (route) => {
      const url = new URL(route.request().url());
      const days = Number(url.searchParams.get("days") ?? "30");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(emptySpendPayload(days)),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);
    await openSpendPanel(page);

    // Totals fall back to the zero figures (not the em-dash placeholder, which
    // only shows before data lands).
    await expect(page.getByTestId("spend-total-cumulative")).toHaveText("$0.00");
    await expect(page.getByTestId("spend-total-surviving")).toHaveText("$0.00");

    // No daily bars; the empty-window copy renders instead.
    await expect(page.getByTestId("spend-daily-bars")).toHaveCount(0);
    await expect(page.getByText("No spend in this window.")).toBeVisible();

    // By-model and top-conversation sections are omitted when empty.
    await expect(page.getByTestId("spend-by-model")).toHaveCount(0);
    await expect(page.getByTestId("spend-by-conversation")).toHaveCount(0);

    // Export buttons stay enabled — there's still a (zeroed) payload to export.
    await expect(page.getByTestId("spend-export-csv")).toBeEnabled();
    await expect(page.getByTestId("spend-export-json")).toBeEnabled();
  });

  test("a failed spend fetch surfaces the error message and keeps exports disabled", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await page.route(`${BE_URL}/api/account/spend**`, async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "INTERNAL", title: "boom" } }),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);
    await openSpendPanel(page);

    // The catch arm renders the error alert; totals stay at the em-dash
    // placeholder and the exports stay disabled (no data to export).
    await expect(page.getByText("Spend data could not be loaded.")).toBeVisible();
    await expect(page.getByTestId("spend-total-cumulative")).toHaveText("—");
    await expect(page.getByTestId("spend-export-csv")).toBeDisabled();
    await expect(page.getByTestId("spend-export-json")).toBeDisabled();
  });
});
