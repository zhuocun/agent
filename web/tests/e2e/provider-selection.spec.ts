import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

const DATA_POLICY_DEEPSEEK = {
  trainsOnData: true,
  trainingDefault: "opt_out",
  dataResidency: "China",
  retentionDays: null,
  zeroDataRetentionAvailable: false,
  policyLabel: "DeepSeek policy",
};

const DATA_POLICY_OPENAI = {
  trainsOnData: false,
  trainingDefault: "never",
  dataResidency: "US",
  retentionDays: 30,
  zeroDataRetentionAvailable: true,
  policyLabel: "OpenAI no training",
};

function tier(id: "auto" | "fast", label: string) {
  return {
    id,
    label,
    description: `${label} tier`,
    speedHint: id === "fast" ? "fastest" : "balanced",
    costHint: id === "fast" ? "lowest" : "medium",
    contextHint: "1M",
    modelLabel: id === "auto" ? "" : "DeepSeek V4 Flash",
    supportsWebSearch: true,
    supportsAttachments: true,
    providerId: "deepseek",
    providerLabel: "DeepSeek",
    providerRouteStatus: "available",
    defaultRouteEligible: true,
    dataPolicy: DATA_POLICY_DEEPSEEK,
    providerOptions: [
      {
        providerId: "deepseek",
        label: "DeepSeek",
        status: "available",
        modelLabel: id === "auto" ? "" : "DeepSeek V4 Flash",
        supportsWebSearch: true,
        supportsAttachments: true,
        defaultRouteEligible: true,
        dataPolicy: DATA_POLICY_DEEPSEEK,
      },
      {
        providerId: "openai",
        label: "OpenAI",
        status: "available",
        modelLabel: id === "auto" ? "" : "GPT test",
        supportsWebSearch: false,
        supportsAttachments: false,
        defaultRouteEligible: false,
        dataPolicy: DATA_POLICY_OPENAI,
      },
      {
        providerId: "gemini",
        label: "Gemini",
        status: "pending",
        modelLabel: "Gemini pending",
        supportsWebSearch: false,
        supportsAttachments: false,
        defaultRouteEligible: false,
        dataPolicy: null,
      },
    ],
  };
}

function singleAvailableProviderTier(id: "auto" | "fast", label: string) {
  const base = tier(id, label);
  return {
    ...base,
    providerOptions: base.providerOptions.map((option) =>
      option.providerId === "openai"
        ? { ...option, status: "unavailable" }
        : option,
    ),
  };
}

test.describe("provider selection", () => {
  test("nested providerOptions drive capabilities and message providerId", async ({
    page,
  }) => {
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          account: {
            name: "Guest",
            email: "",
            planLabel: "Free",
            byokEnabled: false,
            isAnonymous: true,
          },
          preferences: {
            defaultTierId: "auto",
            temporaryByDefault: false,
            trainingOptIn: false,
            sendOnEnter: true,
            autoExpandReasoning: false,
            retentionDays: 30,
          },
          usage: {
            used: 0,
            limit: 1000,
            periodLabel: "this month",
            isByok: false,
          },
          modelTiers: [tier("auto", "Auto"), tier("fast", "Fast")],
          suggestions: [],
          conversations: [],
        }),
      });
    });

    let createdBody: { providerId?: unknown } | undefined;
    await page.route(`${BE_URL}/api/conversations`, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      createdBody = route.request().postDataJSON() as { providerId?: unknown };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "11111111-1111-4111-8111-111111111111",
          title: "New chat",
          messages: [],
          selectedTierId: "auto",
          isTemporary: false,
        }),
      });
    });

    let sentBody: { providerId?: unknown; webSearch?: unknown } | undefined;
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      sentBody = route.request().postDataJSON() as {
        providerId?: unknown;
        webSearch?: unknown;
      };
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body:
          'event: error\ndata: {"code":"TEST","severity":"error","title":"Done","body":"Test complete."}\n\n',
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await expect(page.getByRole("button", { name: "Attach image or PDF" })).toBeVisible();

    await page.getByTestId("model-mode-trigger").click();
    await page.getByTestId("web-search-toggle").click();
    await expect(page.getByTestId("web-search-toggle")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByText("Gemini", { exact: true })).toBeVisible();
    await page.getByText("OpenAI", { exact: true }).click();

    await expect(page.getByRole("button", { name: "Attach image or PDF" })).toHaveCount(0);

    await page.getByTestId("model-mode-trigger").click();
    await expect(page.getByTestId("web-search-toggle")).toHaveCount(0);
    await page.keyboard.press("Escape");

    await page.getByTestId("composer-textarea").fill("Use the selected provider");
    await page.getByTestId("composer-send").click();

    await expect
      .poll(() => sentBody, { timeout: 5_000 })
      .toMatchObject({ providerId: "openai" });
    expect(createdBody).toMatchObject({ providerId: "openai" });
    expect(sentBody?.webSearch).toBeUndefined();
  });

  test("keeps provider UI hidden when only one provider is available", async ({
    page,
  }) => {
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          account: {
            name: "Guest",
            email: "",
            planLabel: "Free",
            byokEnabled: false,
            isAnonymous: true,
          },
          preferences: {
            defaultTierId: "auto",
            temporaryByDefault: false,
            trainingOptIn: false,
            sendOnEnter: true,
            autoExpandReasoning: false,
            retentionDays: 30,
          },
          usage: {
            used: 0,
            limit: 1000,
            periodLabel: "this month",
            isByok: false,
          },
          modelTiers: [
            singleAvailableProviderTier("auto", "Auto"),
            singleAvailableProviderTier("fast", "Fast"),
          ],
          suggestions: [],
          conversations: [],
        }),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await expect(page.getByTestId("model-mode-trigger")).not.toContainText(
      "DeepSeek",
    );
    await page.getByTestId("model-mode-trigger").click();
    await expect(page.getByText("OpenAI", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Gemini", { exact: true })).toHaveCount(0);
  });
});
