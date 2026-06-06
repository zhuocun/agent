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
    listPriceInPerM: id === "auto" ? 0 : 0.14,
    listPriceOutPerM: id === "auto" ? 0 : 0.28,
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
        listPriceInPerM: id === "auto" ? 0 : 0.14,
        listPriceOutPerM: id === "auto" ? 0 : 0.28,
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
        listPriceInPerM: id === "auto" ? 0 : 0.5,
        listPriceOutPerM: id === "auto" ? 0 : 1.5,
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
        listPriceInPerM: 0,
        listPriceOutPerM: 0,
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
      defaultTierId: "auto",
      temporaryByDefault: false,
      trainingOptIn: false,
      sendOnEnter: true,
      autoExpandReasoning: false,
      telemetryEnabled: true,
      customInstructions: "",
      retentionDays: 30,
      keyboardShortcuts: {},
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
    ...overrides,
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
            telemetryEnabled: true,
            customInstructions: "",
            retentionDays: 30,
            keyboardShortcuts: {},
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

    // Attach now lives behind the composer's "More actions" (+) disclosure; open
    // it to assert the provider's attachment capability, then close it again.
    await page.getByTestId("composer-more-actions").click();
    await expect(page.getByRole("button", { name: "Attach file" })).toBeVisible();
    await page.keyboard.press("Escape");

    await page.getByTestId("model-mode-trigger").click();
    await page.getByTestId("web-search-toggle").click();
    await expect(page.getByTestId("web-search-toggle")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await expect(page.getByText("Gemini", { exact: true })).toBeVisible();
    await page.getByText("OpenAI", { exact: true }).click();

    // Switched to a provider without attachment support: Attach is gone from the
    // disclosure too. Open it to assert absence, then close it.
    await page.getByTestId("composer-more-actions").click();
    await expect(page.getByRole("button", { name: "Attach file" })).toHaveCount(0);
    await page.keyboard.press("Escape");

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

  test("attaches text file, sends transient payload, then clears on unsupported provider", async ({
    page,
  }) => {
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(bootstrapPayload()),
      });
    });

    await page.route(`${BE_URL}/api/conversations`, async (route) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "22222222-2222-4222-8222-222222222222",
          title: "New chat",
          messages: [],
          selectedTierId: "auto",
          isTemporary: false,
        }),
      });
    });

    let sentBody:
      | {
          text?: unknown;
          attachments?: Array<{
            name?: unknown;
            mediaType?: unknown;
            storagePolicy?: unknown;
            dataUrl?: unknown;
          }>;
        }
      | undefined;
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      sentBody = route.request().postDataJSON() as typeof sentBody;
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body:
          'event: terminal\ndata: {"status":"done","messageId":"33333333-3333-4333-8333-333333333333","userMessageId":"44444444-4444-4444-8444-444444444444","attribution":{"requestedTierId":"auto","servedTierId":"fast","servedModelLabel":"DeepSeek V4 Flash","providerId":"deepseek","providerLabel":"DeepSeek","isByok":false,"costUsd":0.00003,"costConfidence":"exact","breakdown":{"currency":"USD","listPriceInPerM":0,"listPriceOutPerM":0,"inputTokens":1,"outputTokens":1,"reasoningTokens":0,"cachedInputTokens":0,"longContext":{"flat":true},"promoApplied":false,"subtotalUsd":0,"sessionSurchargeUsd":0}}}\n\n',
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("composer-file-input").setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Alpha beta notes"),
    });
    await expect(page.getByText("notes.txt")).toBeVisible();
    await page.getByTestId("composer-send").click();

    await expect.poll(() => sentBody, { timeout: 5_000 }).toBeTruthy();
    expect(sentBody?.text).toBe("");
    expect(sentBody?.attachments?.[0]).toMatchObject({
      name: "notes.txt",
      mediaType: "text",
      storagePolicy: "transient",
    });
    expect(sentBody?.attachments?.[0]?.dataUrl).toContain(
      "data:text/plain;base64,",
    );
    await expect(page.getByText("Request only")).toBeVisible();
    await expect(page.getByTestId("message-attribution")).toHaveText(
      "DeepSeek V4 Flash·<$0.0001",
    );

    await page.getByTestId("composer-file-input").setInputFiles({
      name: "draft.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Draft"),
    });
    await expect(page.getByText("draft.txt")).toBeVisible();
    await page.getByTestId("model-mode-trigger").click();
    await page.getByText("OpenAI", { exact: true }).click();
    await expect(
      page.getByText("Attachments were removed because the current model does not support files."),
    ).toBeVisible();
    await expect(page.getByText("draft.txt")).toHaveCount(0);
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
            telemetryEnabled: true,
            customInstructions: "",
            retentionDays: 30,
            keyboardShortcuts: {},
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

  test("restores the stored provider preference on reload when available", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("olune.preferredProviderId", "openai");
    });
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(bootstrapPayload()),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await expect(page.getByTestId("model-mode-trigger")).toContainText("OpenAI");
  });

  test("new chat does not overwrite the stored provider preference", async ({
    page,
  }) => {
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(bootstrapPayload()),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("model-mode-trigger").click();
    await page.getByText("OpenAI", { exact: true }).click();
    await expect(page.getByTestId("model-mode-trigger")).toContainText("OpenAI");

    await page.getByTestId("sidebar-new-chat").click();
    await page.reload();
    await waitForBootstrap(page);

    await expect(page.getByTestId("model-mode-trigger")).toContainText("OpenAI");
  });

  test("preserves selected provider when loading another conversation", async ({
    page,
  }) => {
    const conversationId = "22222222-2222-4222-8222-222222222222";
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          bootstrapPayload({
            conversations: [
              {
                id: conversationId,
                title: "Saved provider chat",
                updatedAt: new Date().toISOString(),
                pinned: false,
              },
            ],
          }),
        ),
      });
    });

    await page.route(`${BE_URL}/api/conversations/${conversationId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: conversationId,
          title: "Saved provider chat",
          selectedTierId: "fast",
          isTemporary: false,
          messages: [],
        }),
      });
    });

    let sentBody: { providerId?: unknown } | undefined;
    await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
      sentBody = route.request().postDataJSON() as { providerId?: unknown };
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body:
          'event: error\ndata: {"code":"TEST","severity":"error","title":"Done","body":"Test complete."}\n\n',
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("model-mode-trigger").click();
    await page.getByText("OpenAI", { exact: true }).click();
    await expect(page.getByTestId("model-mode-trigger")).toContainText("OpenAI");

    await page
      .getByTestId("sidebar-conversation-link")
      .filter({ hasText: "Saved provider chat" })
      .click();
    await expect(page.getByTestId("model-mode-trigger")).toContainText("OpenAI");

    await page.getByTestId("composer-textarea").fill("Still OpenAI");
    await page.getByTestId("composer-send").click();

    await expect
      .poll(() => sentBody, { timeout: 5_000 })
      .toMatchObject({ providerId: "openai" });
  });

  test("refreshes bootstrap-derived provider availability after saving BYOK", async ({
    page,
  }) => {
    let bootstrapCount = 0;
    const analyticsEvents: Array<{
      eventType?: string;
      properties?: Record<string, unknown>;
    }> = [];
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      bootstrapCount += 1;
      const refreshed = bootstrapCount > 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          bootstrapPayload({
            account: {
              name: "Ada Lovelace",
              email: "ada@example.com",
              planLabel: "Free",
              byokEnabled: refreshed,
              byokMaskedKey: refreshed ? "sk-...1234" : undefined,
              byokKeys: refreshed
                ? [
                    {
                      providerId: "openai",
                      providerLabel: "OpenAI",
                      maskedKey: "sk-...1234",
                      usable: true,
                    },
                  ]
                : [],
              isAnonymous: false,
            },
            usage: {
              used: 0,
              limit: 1000,
              periodLabel: "this month",
              isByok: refreshed,
            },
            modelTiers: [
              refreshed
                ? tier("auto", "Auto")
                : singleAvailableProviderTier("auto", "Auto"),
              refreshed
                ? tier("fast", "Fast")
                : singleAvailableProviderTier("fast", "Fast"),
            ],
          }),
        ),
      });
    });
    await page.route(`${BE_URL}/api/analytics/events`, async (route) => {
      analyticsEvents.push(route.request().postDataJSON() as {
        eventType?: string;
        properties?: Record<string, unknown>;
      });
      await route.fulfill({ status: 204 });
    });

    let byokBody: { provider?: unknown; apiKey?: unknown } | undefined;
    await page.route(`${BE_URL}/api/account/byok`, async (route) => {
      byokBody = route.request().postDataJSON() as {
        provider?: unknown;
        apiKey?: unknown;
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          name: "Ada Lovelace",
          email: "ada@example.com",
          planLabel: "Free",
          byokEnabled: true,
          byokMaskedKey: "sk-...1234",
          byokKeys: [
            {
              providerId: "openai",
              providerLabel: "OpenAI",
              maskedKey: "sk-...1234",
              usable: true,
            },
          ],
          isAnonymous: false,
        }),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByText("Settings", { exact: true }).click();
    await expect
      .poll(() =>
        analyticsEvents.filter((event) => event.eventType === "settings.opened")
          .length,
      )
      .toBe(1);
    await expect
      .poll(() =>
        analyticsEvents.filter(
          (event) =>
            event.eventType === "usage.viewed" &&
            event.properties?.isByok === false,
        ).length,
      )
      .toBe(1);
    await page.getByLabel("Provider").selectOption("openai");
    await page.getByLabel("API key").fill("sk-test-1234");
    await page.getByRole("button", { name: "Add key" }).click();

    await expect.poll(() => byokBody, { timeout: 5_000 }).toMatchObject({
      provider: "openai",
      apiKey: "sk-test-1234",
    });
    await expect.poll(() => bootstrapCount, { timeout: 5_000 }).toBeGreaterThan(1);
    await expect(page.getByText("Billed to your OpenAI key")).toBeVisible();

    await page.getByRole("button", { name: "Replace key" }).click();
    await expect(page.getByLabel("API key")).toBeVisible();
    await expect
      .poll(() =>
        analyticsEvents.filter(
          (event) =>
            event.eventType === "byok.form_opened" &&
            event.properties?.providerId === "openai" &&
            event.properties?.action === "replace",
        ).length,
      )
      .toBe(1);

    await page.keyboard.press("Escape");
    await page.getByTestId("model-mode-trigger").click();
    await expect(page.getByText("OpenAI", { exact: true })).toBeVisible();
  });

  test("renders the mobile provider picker without horizontal overflow", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(bootstrapPayload()),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByRole("button", { name: /Model Auto/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Provider");
    await expect(dialog.getByText("OpenAI", { exact: true })).toBeVisible();
    await expect(dialog.getByText("Gemini", { exact: true })).toBeVisible();

    const hasHorizontalOverflow = await dialog.evaluate(
      (node) => node.scrollWidth > node.clientWidth + 1,
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
});
