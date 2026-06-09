// FE-side coverage for the cost/reasoning transparency features:
//   1. reasoning-effort wiring + cost/latency hint chips
//   2. pre-send cost & token estimate in the composer
//   3. monthly budget cap settings UI (+ refusal surface)
//   4. regenerate-with-a-different-model
//   5. cost-anomaly callouts
//   + Phase 2: provider-fallback substitution clause (real BE)
//
// Most specs MOCK the BE via `page.route` so the FE half is exercised
// deterministically (the real BE ships these wire fields concurrently; the
// orchestrator runs the real-BE specs after integration). The fallback spec at
// the end drives the REAL FakeProvider, mirroring provider-selection.spec.ts.

import { expect, test, type Locator, type Page } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

// The open model-mode dropdown content (desktop). Scoping row clicks here keeps
// them unambiguous — the picker TRIGGER can show the same tier/effort label as
// a menu row, so an unscoped getByText would match twice.
function pickerMenu(page: Page): Locator {
  return page.locator('[data-slot="dropdown-menu-content"]');
}

// --- Mocked bootstrap fixtures ----------------------------------------------

const DATA_POLICY = {
  trainsOnData: true,
  trainingDefault: "opt_out",
  dataResidency: "China",
  retentionDays: null,
  zeroDataRetentionAvailable: false,
  policyLabel: "DeepSeek policy",
};

// A priced tier. `auto` carries 0/0 (no single model ⇒ estimate unavailable);
// `fast`/`pro` carry distinct prices so the estimate visibly rises on Pro.
function tier(
  id: "auto" | "fast" | "pro",
  label: string,
  priceIn: number,
  priceOut: number,
  modelLabel: string,
) {
  return {
    id,
    label,
    description: `${label} tier`,
    speedHint: id === "fast" ? "fastest" : id === "pro" ? "slow" : "balanced",
    costHint: id === "fast" ? "lowest" : id === "pro" ? "high" : "medium",
    contextHint: id === "auto" ? "auto" : "1M",
    modelLabel,
    supportsWebSearch: true,
    supportsAttachments: false,
    supportsVision: false,
    listPriceInPerM: priceIn,
    listPriceOutPerM: priceOut,
    providerId: "deepseek",
    providerLabel: "DeepSeek",
    providerRouteStatus: "available",
    defaultRouteEligible: true,
    dataPolicy: DATA_POLICY,
    providerOptions: [
      {
        providerId: "deepseek",
        label: "DeepSeek",
        status: "available",
        modelLabel,
        supportsWebSearch: true,
        supportsAttachments: false,
        listPriceInPerM: priceIn,
        listPriceOutPerM: priceOut,
        defaultRouteEligible: true,
        dataPolicy: DATA_POLICY,
      },
    ],
  };
}

function bootstrapPayload(overrides: Record<string, unknown> = {}) {
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
    },
    usage: {
      used: 0,
      limit: 1000,
      periodLabel: "this month",
      isByok: false,
      monthlySpendUsd: 0,
      creditBalanceUsd: 0,
    },
    modelTiers: [
      tier("auto", "Auto", 0, 0, ""),
      tier("fast", "Fast", 0.14, 0.28, "DeepSeek V4 Flash"),
      tier("pro", "Pro", 0.435, 0.87, "DeepSeek V4 Pro"),
    ],
    suggestions: [],
    conversations: [],
    ...overrides,
  };
}

async function mockBootstrap(
  page: Page,
  overrides: Record<string, unknown> = {},
): Promise<void> {
  await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(bootstrapPayload(overrides)),
    });
  });
}

async function mockCreateConversation(page: Page): Promise<void> {
  await page.route(`${BE_URL}/api/conversations`, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        id: "11111111-1111-4111-8111-111111111111",
        title: "New chat",
        messages: [],
        selectedTierId: "fast",
        isTemporary: false,
      }),
    });
  });
}

// Build a `terminal` SSE frame with a custom attribution breakdown so the FE
// commits a `done` assistant turn carrying that attribution.
function terminalFrame(attribution: Record<string, unknown>): string {
  return `event: terminal\ndata: ${JSON.stringify({
    status: "done",
    messageId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    attribution,
  })}\n\n`;
}

function defaultAttribution(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    requestedTierId: "fast",
    servedTierId: "fast",
    servedModelLabel: "DeepSeek V4 Flash",
    providerId: "deepseek",
    providerLabel: "DeepSeek",
    isByok: false,
    costUsd: 0.0001,
    costConfidence: "exact",
    breakdown: {
      currency: "USD",
      listPriceInPerM: 0.14,
      listPriceOutPerM: 0.28,
      inputTokens: 10,
      outputTokens: 10,
      reasoningTokens: 0,
      cachedInputTokens: 0,
      longContext: { flat: true },
      promoApplied: false,
      subtotalUsd: 0.0001,
      sessionSurchargeUsd: 0,
    },
    ...overrides,
  };
}

// --- Feature 1: reasoning-effort wiring + hint chips ------------------------

test.describe("reasoning effort", () => {
  test("Extended effort shows cost/latency chips, rides the wire, and streams to terminal", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await mockCreateConversation(page);

    let sentEffort: unknown;
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      const body = route.request().postDataJSON() as { reasoningEffort?: unknown };
      sentEffort = body.reasoningEffort;
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: terminalFrame(defaultAttribution()),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    // Open the desktop picker and assert the Extended row surfaces its
    // cost/latency hint (REASONING_EFFORTS: Extended ⇒ cost high, latency slow).
    await page.getByTestId("model-mode-trigger").click();
    const menu = pickerMenu(page);
    // Reasoning effort now lives behind the "Advanced" collapsible (progressive
    // disclosure); expand it before the effort rows are reachable.
    await menu.getByTestId("picker-advanced").click();
    await expect(
      menu.getByText("Cost high · Latency slow", { exact: true }),
    ).toBeVisible();
    // Pick Extended (clicking the row's label span; mirrors how the existing
    // provider-selection specs select a row). Scoped to the open menu so the
    // match is unambiguous.
    await menu.getByText("Extended", { exact: true }).click();

    await page.getByTestId("composer-textarea").fill("Think hard about this");
    await page.getByTestId("composer-send").click();

    // The effort rode the wire as a concrete value (auto would be omitted).
    await expect.poll(() => sentEffort, { timeout: 5_000 }).toBe("extended");

    // The turn streamed to a terminal.
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
  });
});

// --- Feature 2: pre-send cost & token estimate ------------------------------

test.describe("pre-send estimate", () => {
  test("estimate appears for a priced tier, rises on Pro, and is unavailable for Auto", async ({
    page,
  }) => {
    await mockBootstrap(page); // defaultTierId: "fast"

    await page.goto("/");
    await waitForBootstrap(page);

    const estimate = page.getByTestId("cost-estimate");
    // No estimate before there's any draft text.
    await expect(estimate).toHaveCount(0);

    // A long message on the Fast tier produces a concrete dollar estimate.
    const longText = "word ".repeat(400); // ~2000 chars ⇒ ~500 input tokens
    await page.getByTestId("composer-textarea").fill(longText);
    await expect(estimate).toBeVisible();
    await expect(estimate).toContainText("Est. $");
    await expect(estimate).toContainText("tokens in");

    const fastText = (await estimate.textContent()) ?? "";
    const fastUsd = parseEstimateUsd(fastText);
    expect(fastUsd).toBeGreaterThan(0);

    // Switch to Pro (pricier) — same draft, the dollar estimate rises. Scope to
    // the open menu so the row click never collides with the trigger label.
    await page.getByTestId("model-mode-trigger").click();
    await pickerMenu(page).getByText("Pro", { exact: true }).click();
    await expect(estimate).toContainText("Est. $");
    const proText = (await estimate.textContent()) ?? "";
    const proUsd = parseEstimateUsd(proText);
    expect(proUsd).toBeGreaterThan(fastUsd);

    // Switch to Auto (no single price) — the estimate reads "unavailable".
    // "Auto" labels two rows (the Model tier and the Reasoning-effort option);
    // the Model group renders first, so the tier "Auto" is the first match.
    await page.getByTestId("model-mode-trigger").click();
    await pickerMenu(page).getByText("Auto", { exact: true }).first().click();
    await expect(estimate).toContainText("Estimate unavailable for Auto");
  });
});

// Pull the dollar number out of an estimate line like "Est. $0.0123 · 500 tokens in".
function parseEstimateUsd(text: string): number {
  const match = text.match(/\$([0-9]+(?:\.[0-9]+)?)/);
  return match ? Number(match[1]) : NaN;
}

// --- Feature 3: monthly budget cap ------------------------------------------

test.describe("monthly budget cap", () => {
  test("saving a cap persists monthlyBudgetUsd; an over-budget second turn is refused", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await mockCreateConversation(page);

    const preferenceBodies: Array<Record<string, unknown>> = [];
    await page.route(`${BE_URL}/api/preferences`, async (route) => {
      if (route.request().method() === "PUT") {
        preferenceBodies.push(
          route.request().postDataJSON() as Record<string, unknown>,
        );
      }
      await route.fulfill({ status: 204, body: "" });
    });

    // First message-create streams a normal terminal; the second is refused
    // with a budget-exceeded error envelope (the FE renders the error surface).
    let messageCreateCount = 0;
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      messageCreateCount += 1;
      if (messageCreateCount === 1) {
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
          body: terminalFrame(defaultAttribution()),
        });
        return;
      }
      await route.fulfill({
        status: 402,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "BUDGET_EXCEEDED",
            severity: "warning",
            title: "Monthly budget reached",
            body: "You've hit your monthly spend cap. Raise it in settings to continue.",
          },
        }),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    // Open settings and set a tiny cap.
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Settings" }).click();
    const dialog = page.getByRole("dialog", { name: "Settings" });
    await expect(dialog).toBeVisible();

    // The budget cap editor now lives behind the collapsed "Spending details"
    // disclosure — expand it before interacting with the cap input.
    await dialog.getByTestId("spending-details-toggle").click();

    const capInput = page.getByTestId("budget-cap-input");
    await capInput.fill("1");
    await page.getByTestId("budget-cap-save").click();

    // The cap rode the existing preferences PUT path as monthlyBudgetUsd.
    await expect
      .poll(() => preferenceBodies.some((b) => b.monthlyBudgetUsd === 1))
      .toBe(true);

    // Settings reflects the saved cap (the input keeps the value).
    await expect(capInput).toHaveValue("1");

    // Close settings, then send two turns.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("First turn");
    await page.getByTestId("composer-send").click();
    const firstAssistant = page.getByTestId("assistant-message").last();
    await expect(firstAssistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    await composer.fill("Second turn over budget");
    await page.getByTestId("composer-send").click();

    // The second turn is refused — the budget error surface shows.
    await expect(page.getByText("Monthly budget reached")).toBeVisible({
      timeout: 15_000,
    });
  });
});

// --- Feature 4: regenerate with a different model ---------------------------

test.describe("regenerate with model", () => {
  test("picking a different model from the regenerate menu streams a new bubble with the new served model", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await mockCreateConversation(page);

    // First turn served by Fast; the regenerated turn served by Pro. We key off
    // the requested tierId in the message-create body so the mock returns the
    // matching served attribution.
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      const body = route.request().postDataJSON() as { tierId?: string };
      const isPro = body.tierId === "pro";
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: terminalFrame(
          defaultAttribution(
            isPro
              ? {
                  requestedTierId: "pro",
                  servedTierId: "pro",
                  servedModelLabel: "DeepSeek V4 Pro",
                }
              : {},
          ),
        ),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    // Send an initial turn (served by Fast).
    await page.getByTestId("composer-textarea").fill("Original question");
    await page.getByTestId("composer-send").click();
    const firstAssistant = page.getByTestId("assistant-message").last();
    await expect(firstAssistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("message-attribution")).toContainText(
      "DeepSeek V4 Flash",
    );

    // Open the message "…" overflow menu (the regenerate split control lives
    // there now) and pick Pro. The menu portals to body, so the tier item
    // resolves via page.getByTestId.
    await page.getByTestId("message-actions-overflow").last().click();
    await page.getByTestId("regenerate-with-tier-pro").click();

    // A new bubble streams; the attribution now shows the Pro served model.
    const regenerated = page.getByTestId("assistant-message").last();
    await expect(regenerated).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect(page.getByTestId("message-attribution")).toContainText(
      "DeepSeek V4 Pro",
    );

    // The picker reflects the new served model going forward.
    await expect(page.getByTestId("model-mode-trigger")).toContainText("Pro");
  });
});

// --- Feature 5: cost-anomaly callouts ---------------------------------------

test.describe("cost anomaly", () => {
  test("a high-reasoning turn surfaces a 'why' clause on the attribution row", async ({
    page,
  }) => {
    await mockBootstrap(page);
    await mockCreateConversation(page);

    // Terminal with reasoningTokens > outputTokens ⇒ "High reasoning cost".
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: terminalFrame(
          defaultAttribution({
            costUsd: 0.02,
            breakdown: {
              currency: "USD",
              listPriceInPerM: 0.14,
              listPriceOutPerM: 0.28,
              inputTokens: 100,
              outputTokens: 50,
              reasoningTokens: 5000,
              cachedInputTokens: 0,
              longContext: { flat: true },
              promoApplied: false,
              subtotalUsd: 0.02,
              sessionSurchargeUsd: 0,
            },
          }),
        ),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("composer-textarea").fill("Reason deeply");
    await page.getByTestId("composer-send").click();
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // The muted "why" clause appears inline on the byline.
    const anomaly = assistant.getByTestId("attribution-anomaly");
    await expect(anomaly).toBeVisible();
    await expect(anomaly).toContainText("High reasoning cost");

    // It also appears as a one-line callout inside the cost breakdown popover.
    await page.getByTestId("message-attribution").click();
    await expect(page.getByTestId("cost-anomaly")).toContainText(
      "High reasoning cost",
    );
  });
});

// --- Phase 2: provider-fallback substitution (REAL BE) ----------------------
//
// Requires the integrated BE running PROVIDER_BACKEND=fake with a fallback
// route configured: a message whose text starts with "FORCE_FALLBACK_RETRY:"
// makes the primary route fail and the BE substitute a fallback provider,
// stamping the assistant attribution with a `substitution`. We assert the FE
// renders the substitution clause ("substituted from …"). Mirrors the real-BE
// streaming spec; no bootstrap/route mocks here.

test.describe("provider fallback substitution", () => {
  test("a forced-fallback turn shows the substitution clause on the attribution row", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page
      .getByTestId("composer-textarea")
      .fill("FORCE_FALLBACK_RETRY: answer anyway");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // The byline carries the substitution clause (served != requested).
    await expect(assistant.getByTestId("attribution-substitution")).toBeVisible({
      timeout: 15_000,
    });
  });
});
