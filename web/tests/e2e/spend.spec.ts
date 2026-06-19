// FE-side coverage for the spend-analytics dashboard (PRD 05 §4.5 D27).
//
// Mocks the BE so the FE half is exercised deterministically: a mocked
// /api/bootstrap mints a guest, and /api/account/spend returns a fixed
// analytics payload that echoes the requested `days` back as `rangeDays`. The
// spec opens Settings → Account and asserts the inline Usage & spend panel:
// totals, the daily bars, the by-model + top-conversation lists, the export
// affordances, and that switching the range re-fetches.

import { expect, test, type Page } from "@playwright/test";

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
});
