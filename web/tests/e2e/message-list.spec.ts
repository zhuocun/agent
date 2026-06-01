import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

const LONG_CONVERSATION_ID = "22222222-2222-4222-8222-222222222222";

const DATA_POLICY = {
  trainsOnData: true,
  trainingDefault: "opt_out",
  dataResidency: "China",
  retentionDays: null,
  zeroDataRetentionAvailable: false,
  policyLabel: "DeepSeek policy",
};

function tier() {
  return {
    id: "auto",
    label: "Auto",
    description: "Auto tier",
    speedHint: "balanced",
    costHint: "medium",
    contextHint: "1M",
    modelLabel: "",
    supportsWebSearch: true,
    supportsAttachments: true,
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
        modelLabel: "",
        supportsWebSearch: true,
        supportsAttachments: true,
        defaultRouteEligible: true,
        dataPolicy: DATA_POLICY,
      },
    ],
  };
}

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
    modelTiers: [tier()],
    suggestions: [],
    conversations: [
      {
        id: LONG_CONVERSATION_ID,
        title: "Long history",
        updatedAt: "2026-01-01T00:00:00.000Z",
        isTemporary: false,
      },
    ],
  };
}

function longMessages() {
  return Array.from({ length: 180 }, (_, index) => {
    const createdAt = new Date(Date.UTC(2026, 0, 1, 0, 0, index)).toISOString();
    if (index % 2 === 0) {
      return {
        id: `user-${index}`,
        role: "user",
        parts: [
          {
            type: "text",
            text: `User prompt ${index}`,
          },
        ],
        createdAt,
      };
    }
    return {
      id: `assistant-${index}`,
      role: "assistant",
      parts: [
        {
          type: "reasoning",
          text:
            index % 12 === 1
              ? `Reasoning notes for ${index}\n\n- line one\n- line two\n- line three`
              : "",
          durationSec: 2,
        },
        {
          type: "text",
          text: `Assistant answer ${index}\n\n${"Detailed paragraph. ".repeat(
            index % 10 === 9 ? 14 : 2,
          )}`,
        },
      ],
      createdAt,
      status: "done",
    };
  });
}

test.describe("message list virtualization", () => {
  test("long conversations window rows while preserving bottom-follow and jump-to-latest", async ({
    page,
  }) => {
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(bootstrapPayload()),
      });
    });
    await page.route(
      `${BE_URL}/api/conversations/${LONG_CONVERSATION_ID}`,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: LONG_CONVERSATION_ID,
            title: "Long history",
            messages: longMessages(),
            selectedTierId: "auto",
            isTemporary: false,
          }),
        });
      },
    );

    await page.goto("/");
    await waitForBootstrap(page);
    await page.locator(`[data-conversation-id="${LONG_CONVERSATION_ID}"]`).click();

    const rows = page.getByTestId("message-list-row");
    const messagesRegion = page.getByRole("region", { name: "Messages" });

    await expect(page.getByText("Assistant answer 179")).toBeVisible();
    await expect.poll(() => rows.count()).toBeLessThan(80);
    await expect.poll(() => rows.count()).toBeGreaterThan(0);

    await messagesRegion.evaluate((el) => {
      el.scrollTo({ top: 0, behavior: "auto" });
    });
    await expect(page.getByText("User prompt 0")).toBeVisible();
    await expect
      .poll(() => rows.count())
      .toBeLessThan(80);

    const jump = page.locator('button[aria-label="Jump to latest"]');
    await expect(jump).toHaveAttribute("aria-hidden", "false");
    await jump.click();

    await expect(page.getByText("Assistant answer 179")).toBeVisible();
    await expect(jump).toHaveAttribute("aria-hidden", "true");
    await expect.poll(() => rows.count()).toBeLessThan(80);
  });
});
