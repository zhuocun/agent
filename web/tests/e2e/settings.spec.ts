// Settings hub — tab matrix, preference round-trips, budget editors, billing UI,
// usage-meter states, BYOK key management, and per-project defaults.
//
// Most tests drive the REAL shell + real BE on :8000 (PROVIDER_BACKEND=fake,
// BILLING_BACKEND=fake) so the settings-dialog / byok-form / usage-meter /
// tier-picker FE code runs end-to-end. A handful of branches that can't be
// produced deterministically against the live BE — billing-provider failures
// and specific usage-meter tones — mock /api/bootstrap (and the billing
// endpoints) so the same components render the otherwise-unreachable states.
//
// Settings is opened from the desktop sidebar account menu (the suite runs
// Chromium desktop), the same entry point account-data.spec / spend.spec use.

import { expect, test, type Page } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 8)}@example.com`;
}

// Promote the page's anon session to a registered account over HTTP, then load
// the shell so it bootstraps as that user. `page.request` shares the browser
// context cookie jar, so the registered `sid` rides into the page navigation.
async function signInPage(page: Page): Promise<void> {
  await page.request.get(`${BE_URL}/api/bootstrap`);
  const upgrade = await page.request.post(`${BE_URL}/api/auth/upgrade`, {
    data: { email: uniqueEmail("settings"), password: "settings-e2e-pass" },
  });
  expect(upgrade.ok()).toBe(true);
}

// Grant the current session an active Pro entitlement through the fake billing
// backend (mirrors agentic.spec.ts grantPro): upgrade → fake checkout (to learn
// the user id) → unsigned subscription webhook. Leaves the session registered +
// Pro; the caller reloads to re-bootstrap.
async function grantPro(page: Page): Promise<void> {
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const upgrade = await page.request.post(`${BE_URL}/api/auth/upgrade`, {
    data: { email: `settings-pro-${unique}@example.com`, password: "pro-e2e-pass" },
  });
  expect(upgrade.ok()).toBe(true);

  const checkout = await page.request.post(`${BE_URL}/api/billing/checkout`, {
    data: { kind: "pro_subscription" },
  });
  expect(checkout.ok()).toBe(true);
  const { url } = (await checkout.json()) as { url: string };
  const userId = new URL(url, BE_URL).searchParams.get("user");
  expect(userId).toBeTruthy();

  const webhook = await page.request.post(`${BE_URL}/api/billing/webhook`, {
    data: {
      id: `evt_settings_${unique}`,
      type: "customer.subscription.created",
      created: Math.floor(Date.now() / 1000),
      data: {
        object: {
          id: `sub_settings_${unique}`,
          customer: `cus_settings_${unique}`,
          status: "active",
          current_period_end: Math.floor(Date.now() / 1000) + 30 * 24 * 60 * 60,
          metadata: { user_id: userId },
        },
      },
    },
  });
  expect(webhook.ok()).toBe(true);
}

async function openSettings(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
}

function settingsDialog(page: Page) {
  return page.getByRole("dialog", { name: "Settings" });
}

// A complete bootstrap payload for the mock-only branches. Overrides are merged
// shallowly at the top level (so a test can swap `usage` / `account` wholesale).
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
      monthlyBudgetUsd: null,
      perConversationBudgetUsd: null,
      memoryEnabled: false,
      keyboardShortcuts: {},
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

test.describe("settings — tab matrix", () => {
  test("switches across every hub tab and arrow-keys along the tablist", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    // The folded-in surfaces mount their fetch-on-open bodies only while active.
    await dialog.getByTestId("open-activity-button").click();
    await expect(page.getByTestId("activity-dialog")).toBeVisible();

    await dialog.getByTestId("open-memory-button").click();
    await expect(page.getByTestId("memory-dialog")).toBeVisible();

    await dialog.getByTestId("open-templates-button").click();
    await expect(page.getByTestId("template-dialog")).toBeVisible();

    await dialog.getByTestId("open-model-directory-button").click();
    await expect(page.getByTestId("model-directory-dialog")).toBeVisible();

    await dialog.getByTestId("open-shortcuts-button").click();
    await expect(page.getByTestId("shortcuts-customize-toggle")).toBeVisible();

    // Back to General (roving-tabindex tablist; General has no testid).
    await dialog.getByRole("tab", { name: "General" }).click();
    await expect(page.getByTestId("export-data-button")).toBeVisible();

    // Roving keyboard nav: focus General then arrow across cluster boundaries.
    const general = dialog.getByRole("tab", { name: "General" });
    await general.focus();
    await page.keyboard.press("ArrowRight");
    await expect(dialog.getByRole("tab", { name: "Activity" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await page.keyboard.press("End");
    await expect(dialog.getByRole("tab", { name: "Shortcuts" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await page.keyboard.press("Home");
    await expect(general).toHaveAttribute("aria-selected", "true");
  });
});

test.describe("settings — preferences", () => {
  test("toggles, retention, and privacy switches round-trip to /api/preferences", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    // Helper: arm a PUT watcher, run an action, assert the sent prefs subset.
    async function expectPrefsPut(
      action: () => Promise<void>,
      expected: Record<string, unknown>,
    ): Promise<void> {
      const req = page.waitForRequest(
        (r) =>
          r.url() === `${BE_URL}/api/preferences` && r.method() === "PUT",
      );
      await action();
      expect((await req).postDataJSON()).toMatchObject(expected);
    }

    await expectPrefsPut(
      () => dialog.getByRole("switch", { name: "Send on Enter" }).click(),
      { sendOnEnter: false },
    );
    await expectPrefsPut(
      () =>
        dialog.getByRole("switch", { name: "Auto-expand reasoning" }).click(),
      { autoExpandReasoning: true },
    );
    await expectPrefsPut(
      () =>
        dialog
          .getByRole("switch", { name: "Temporary chats by default" })
          .click(),
      { temporaryByDefault: true },
    );

    // Retention picker (role=group "Chat retention" — scope past the project one).
    const retention = dialog.getByRole("group", { name: "Chat retention" });
    await expectPrefsPut(
      () => retention.getByRole("button", { name: "90 days" }).click(),
      { retentionDays: 90 },
    );
    await expectPrefsPut(
      () => retention.getByRole("button", { name: "Forever" }).click(),
      { retentionDays: null },
    );

    // Training + telemetry live under the Advanced privacy disclosure.
    await dialog.getByTestId("advanced-privacy-toggle").click();
    await expectPrefsPut(
      () => dialog.getByRole("switch", { name: "Help improve Olune" }).click(),
      { trainingOptIn: true },
    );
    await expectPrefsPut(
      () => dialog.getByRole("switch", { name: "Product telemetry" }).click(),
      { telemetryEnabled: false },
    );
  });

  test("custom instructions commit on blur", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await dialog.getByTestId("custom-instructions-toggle").click();
    const textarea = dialog.getByLabel("Custom instructions");
    await textarea.fill("Always answer in metric units.");

    const req = page.waitForRequest(
      (r) => r.url() === `${BE_URL}/api/preferences` && r.method() === "PUT",
    );
    // Blur commits the draft (onBlur → commitCustomInstructions).
    await dialog.getByText("Appearance", { exact: true }).click();
    expect((await req).postDataJSON()).toMatchObject({
      customInstructions: "Always answer in metric units.",
    });
  });

  test("monthly and per-conversation budget caps round-trip", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    const monthly = page.waitForRequest(
      (r) => r.url() === `${BE_URL}/api/preferences` && r.method() === "PUT",
    );
    await dialog.getByTestId("budget-cap-input").fill("25");
    await dialog.getByTestId("budget-cap-save").click();
    expect((await monthly).postDataJSON()).toMatchObject({
      monthlyBudgetUsd: 25,
    });

    const perConvo = page.waitForRequest(
      (r) => r.url() === `${BE_URL}/api/preferences` && r.method() === "PUT",
    );
    await dialog.getByTestId("conversation-cap-input").fill("5");
    await dialog.getByTestId("conversation-cap-save").click();
    expect((await perConvo).postDataJSON()).toMatchObject({
      perConversationBudgetUsd: 5,
    });
  });
});

test.describe("settings — billing", () => {
  test("a Pro account shows credits + manage billing and hides upgrade", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await grantPro(page);
    await page.reload();
    await waitForBootstrap(page);

    await openSettings(page);
    const dialog = settingsDialog(page);

    await expect(
      dialog.getByRole("button", { name: "Buy credits" }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Manage billing" }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Upgrade to Pro" }),
    ).toHaveCount(0);
  });

  test("billing failures surface inline error copy", async ({ page }) => {
    await mockBootstrap(page, {
      account: {
        name: "Ada Lovelace",
        email: "ada@example.com",
        planLabel: "Free",
        byokEnabled: false,
        isAnonymous: false,
        billing: {
          planId: "free",
          planLabel: "Free",
          proEnabled: false,
          billingProvider: "fake",
          checkoutAvailable: true,
          proCheckoutAvailable: true,
          creditCheckoutAvailable: true,
          portalAvailable: true,
          creditBalanceUsd: 0,
        },
      },
    });
    await page.route(`${BE_URL}/api/billing/checkout`, async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "BILLING_ERROR",
            severity: "error",
            title: "Nope",
            body: "boom",
          },
        }),
      });
    });
    await page.route(`${BE_URL}/api/billing/portal`, async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "BILLING_ERROR",
            severity: "error",
            title: "Nope",
            body: "boom",
          },
        }),
      });
    });

    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await dialog.getByRole("button", { name: "Upgrade to Pro" }).click();
    await expect(
      dialog.getByText("Billing could not be started."),
    ).toBeVisible();

    await dialog.getByRole("button", { name: "Manage billing" }).click();
    await expect(
      dialog.getByText("Billing management is not available yet."),
    ).toBeVisible();

    // Credit checkout uses the same path; assert it re-shows the checkout error.
    await dialog.getByRole("button", { name: "Buy credits" }).click();
    await expect(
      dialog.getByText("Billing could not be started."),
    ).toBeVisible();
  });
});

test.describe("settings — usage meter states", () => {
  test("renders the BYOK badge for a bring-your-own-key session", async ({
    page,
  }) => {
    await mockBootstrap(page, {
      account: {
        name: "Ada Lovelace",
        email: "ada@example.com",
        planLabel: "Free",
        byokEnabled: true,
        byokMaskedKey: "sk-...1234",
        isAnonymous: false,
      },
      usage: {
        used: 0,
        limit: 1000,
        periodLabel: "this month",
        isByok: true,
        creditBalanceUsd: 3.5,
      },
    });
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await expect(dialog.getByText("Billed to your key")).toBeVisible();
    await expect(dialog.getByText(/Credit balance/)).toBeVisible();
  });

  test("renders an exhausted platform-credit meter", async ({ page }) => {
    await mockBootstrap(page, {
      usage: {
        used: 1000,
        limit: 1000,
        periodLabel: "this month",
        isByok: false,
        monthlySpendUsd: 0,
        creditBalanceUsd: 0,
      },
    });
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await expect(dialog.getByText("No usage left")).toBeVisible();
    await expect(dialog.getByText(/Usage limit reached/)).toBeVisible();
  });

  test("renders a near-cap spend warning meter", async ({ page }) => {
    await mockBootstrap(page, {
      usage: {
        used: 100,
        limit: 1000,
        periodLabel: "this month",
        isByok: false,
        effectiveQuotaUsd: 10,
        monthlySpendUsd: 9,
        creditBalanceUsd: 0,
      },
    });
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    // $10 cap, $9 spent → $1 left, 90% → warning tone, USD remaining text.
    await expect(dialog.getByText("$1.00 left")).toBeVisible();
  });
});

test.describe("settings — BYOK", () => {
  test("adds, replaces, clears, then removes a provider key", async ({
    page,
  }) => {
    await signInPage(page);
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await dialog.getByTestId("byok-section-toggle").click();

    // --- Add a key (real PUT /api/account/byok) ------------------------------
    await dialog.getByLabel("Provider").selectOption("deepseek");
    await dialog.getByLabel("API key").fill("sk-deepseek-abcdefgh");
    const addReq = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/account/byok` &&
        r.request().method() === "PUT",
    );
    await dialog.getByRole("button", { name: "Add key", exact: true }).click();
    expect((await addReq).status()).toBe(200);
    await expect(dialog.getByText("Billed to your DeepSeek key")).toBeVisible();

    // --- Replace the key -----------------------------------------------------
    await dialog.getByRole("button", { name: "Replace key" }).click();
    await expect(dialog.getByLabel("API key")).toBeVisible();
    await dialog.getByLabel("API key").fill("sk-deepseek-replaced9");
    const replaceReq = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/account/byok` &&
        r.request().method() === "PUT",
    );
    await dialog.getByRole("button", { name: "Save new key" }).click();
    expect((await replaceReq).status()).toBe(200);
    await expect(dialog.getByText("Billed to your DeepSeek key")).toBeVisible();

    // --- Clear-field affordance inside the key input --------------------------
    await dialog.getByRole("button", { name: "Replace key" }).click();
    const keyInput = dialog.getByLabel("API key");
    await keyInput.fill("typo-typo");
    await dialog.getByRole("button", { name: "Clear API key" }).click();
    await expect(keyInput).toHaveValue("");
    // Leave replace mode for the removal step.
    await dialog.getByRole("button", { name: "Cancel" }).click();

    // --- Remove: cancel the confirm, then go through with it ------------------
    await dialog.getByRole("button", { name: "Remove key" }).click();
    await expect(
      dialog.getByText("Remove this key? Future requests revert to platform credits."),
    ).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();

    await dialog.getByRole("button", { name: "Remove key" }).click();
    const removeReq = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/account/byok/deepseek` &&
        r.request().method() === "DELETE",
    );
    await dialog.getByRole("button", { name: "Remove key" }).click();
    expect((await removeReq).status()).toBe(200);
    await expect(dialog.getByLabel("API key")).toBeVisible();
  });

  test("rejects a too-short key with an error toast", async ({ page }) => {
    await signInPage(page);
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await dialog.getByTestId("byok-section-toggle").click();
    await dialog.getByLabel("Provider").selectOption("deepseek");
    // Non-empty (passes the client guard) but < 8 chars → BE 400 INVALID_INPUT.
    await dialog.getByLabel("API key").fill("short");
    await dialog.getByRole("button", { name: "Add key", exact: true }).click();

    const toast = page
      .getByRole("alert")
      .filter({ hasText: /at least 8 characters/ });
    await expect(toast).toBeVisible();
  });

  test("guests are routed to sign-in from the BYOK section", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await dialog.getByTestId("byok-section-toggle").click();
    await expect(
      dialog.getByText(/Guest sessions can.t store provider credentials/),
    ).toBeVisible();

    // The in-form CTA closes settings and opens the auth dialog.
    await dialog.getByRole("button", { name: "Sign in to add a key" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
});

test.describe("settings — project defaults", () => {
  async function createProject(page: Page, name: string): Promise<string> {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/projects`, {
      data: { name },
    });
    expect(created.status()).toBe(201);
    return (await created.json()).id as string;
  }

  test("edits retention, budget sub-cap, and shared instructions per project", async ({
    page,
  }) => {
    const projectId = await createProject(page, "Research");

    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);
    const dialog = settingsDialog(page);

    await dialog.getByTestId("project-defaults-toggle").click();
    const panel = page.getByTestId("project-settings-panel");
    await expect(panel).toBeVisible();

    // Retention override (scoped to the project group, not the global one).
    const projectRetention = panel.getByRole("group", {
      name: "Project retention",
    });
    const retentionPatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/projects/${projectId}` &&
        r.request().method() === "PATCH",
    );
    await projectRetention.getByRole("button", { name: "30 days" }).click();
    expect((await (await retentionPatch).json()).retentionDays).toBe(30);

    // Per-conversation budget sub-cap.
    const capPatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/projects/${projectId}` &&
        r.request().method() === "PATCH",
    );
    await panel.getByTestId("project-cap-input").fill("3");
    await panel.getByTestId("project-cap-save").click();
    expect((await (await capPatch).json()).perConversationBudgetUsd).toBe(3);

    // Shared instructions commit on blur.
    const instructionsPatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/projects/${projectId}` &&
        r.request().method() === "PATCH",
    );
    await panel.getByTestId("project-instructions-input").fill("Cite sources.");
    await panel.getByTestId("project-cap-input").click(); // blur the textarea
    expect((await (await instructionsPatch).json()).customInstructions).toBe(
      "Cite sources.",
    );
  });
});

test.describe("settings — tier picker (mobile)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("selects a default model via the bottom-sheet picker", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // On mobile the sidebar (which hosts the account menu) lives in an
    // off-canvas drawer; the header's "Open sidebar" button reveals it. The
    // desktop openSettings() path can't see the account menu at this width.
    // On mobile the sidebar (which hosts the account menu) lives in an
    // off-canvas drawer; the header's "Open sidebar" button reveals it. The
    // desktop openSettings() path can't see the account menu at this width.
    await page.locator('button[aria-label="Open sidebar"]:visible').click();
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Settings" }).click();
    const dialog = settingsDialog(page);
    await expect(dialog.getByRole("heading", { name: "Settings" })).toBeVisible();

    // The mobile settings dialog is a bottom sheet whose swipe-to-dismiss takes
    // pointer capture, which suppresses Playwright's synthesized clicks on its
    // inner content (a real tap still fires onClick). So dispatch clicks
    // directly for every in-sheet control. First drill into General from the
    // grouped list; the back button only renders once we're in a tab's body.
    await dialog
      .getByRole("button", { name: "General" })
      .dispatchEvent("click");
    await expect(dialog.getByTestId("settings-back-button")).toBeVisible();

    // The mobile (md:hidden) TierPicker trigger opens a nested bottom-sheet.
    const trigger = page.locator(
      'button[aria-label*="Change model tier"]:visible',
    );
    await expect(trigger).toBeVisible();
    await trigger.dispatchEvent("click");

    const sheet = page.getByRole("dialog", { name: "Model" });
    await expect(sheet).toBeVisible();

    // handleSelect persists the tier + closes the sheet.
    const put = page.waitForRequest(
      (r) => r.url() === `${BE_URL}/api/preferences` && r.method() === "PUT",
    );
    await sheet.locator('button[aria-label="Smart"]').dispatchEvent("click");
    expect((await put).postDataJSON()).toMatchObject({ defaultTierId: "smart" });
  });
});
