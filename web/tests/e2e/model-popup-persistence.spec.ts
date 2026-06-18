// FE-side coverage for the Model & Reasoning popup's "selections persist across
// reload" contract (chat-thread.tsx `persistPopupDefault` → PUT /api/preferences
// → bootstrap re-seed on reload). Mirrors provider-selection.spec.ts's reload
// assertions, but proves the SERVER-backed defaults rather than the localStorage
// provider fast-path: an anonymous user's tier, reasoning effort, and the
// web-search + JSON-output toggles all survive a full page reload.
//
// The BE is MOCKED via `page.route`: a single mutable `prefs` object stands in
// for the persisted row. Each PUT /api/preferences merges its body into `prefs`,
// and the bootstrap route serves the current `prefs` — so a reload re-fetches the
// updated state exactly as the real BE would.

import { expect, test, type Page } from "@playwright/test";

import { BE_URL, modelModeTrigger, waitForBootstrap } from "./helpers";

const DATA_POLICY = {
  trainsOnData: true,
  trainingDefault: "opt_out",
  dataResidency: "China",
  retentionDays: null,
  zeroDataRetentionAvailable: false,
  policyLabel: "DeepSeek policy",
};

// A single-provider tier (only DeepSeek available) so the provider picker stays
// hidden and the popup reduces to the controls under test: tier, the two
// first-level toggles, and the Advanced reasoning-effort rows. `fast` reports
// `supportsWebSearch` so the Web-search toggle renders.
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
    dataPolicy: DATA_POLICY,
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
        dataPolicy: DATA_POLICY,
      },
    ],
  };
}

// The persisted-preferences defaults the popup starts from. The five popup
// fields (defaultTierId / defaultReasoningEffortId / webSearchDefault /
// jsonModeDefault / deepResearchDefault) are seeded to their behaviour-neutral
// baseline so each assertion below proves a real flip away from the default.
function defaultPreferences(): Record<string, unknown> {
  return {
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
    defaultReasoningEffortId: "auto",
    defaultProviderId: null,
    webSearchDefault: false,
    jsonModeDefault: false,
    deepResearchDefault: false,
  };
}

function bootstrapPayload(prefs: Record<string, unknown>): Record<string, unknown> {
  return {
    account: {
      name: "Guest",
      email: "",
      planLabel: "Free",
      byokEnabled: false,
      isAnonymous: true,
    },
    preferences: prefs,
    usage: {
      used: 0,
      limit: 1000,
      periodLabel: "this month",
      isByok: false,
    },
    modelTiers: [tier("auto", "Auto"), tier("fast", "Fast")],
    suggestions: [],
    conversations: [],
  };
}

// Wire up a mutable server-backed preferences store. `bootstrap` always serves
// the current `state.prefs`; PUT /api/preferences merges its body into that and
// records the body for assertion. Returns the live state plus the recorded PUT
// bodies.
async function mockPreferenceBackend(page: Page): Promise<{
  state: { prefs: Record<string, unknown> };
  bodies: Array<Record<string, unknown>>;
}> {
  const state = { prefs: defaultPreferences() };
  const bodies: Array<Record<string, unknown>> = [];

  await page.route(`${BE_URL}/api/bootstrap`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(bootstrapPayload(state.prefs)),
    });
  });

  await page.route(`${BE_URL}/api/preferences`, async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      bodies.push(body);
      state.prefs = { ...state.prefs, ...body };
    }
    await route.fulfill({ status: 204, body: "" });
  });

  return { state, bodies };
}

test.describe("model & reasoning popup persistence", () => {
  test("tier, reasoning effort, and the web-search + JSON toggles survive a reload", async ({
    page,
  }) => {
    const backend = await mockPreferenceBackend(page);

    await page.goto("/");
    await waitForBootstrap(page);

    // Baseline: the popup opens in the neutral default state — Auto tier, both
    // first-level toggles off.
    await modelModeTrigger(page).click();
    await expect(page.getByTestId("web-search-toggle")).toHaveAttribute(
      "aria-checked",
      "false",
    );
    await expect(page.getByTestId("json-mode-toggle")).toHaveAttribute(
      "aria-checked",
      "false",
    );

    // 1. Select the Fast tier. A tier row is a DropdownMenuItem, so the menu
    //    closes on click — reopen it for the remaining selections.
    await page.getByText("Fast", { exact: true }).click();
    await expect(modelModeTrigger(page)).toContainText("Fast");

    // 2. Flip the two first-level toggles (they keep the menu open) ...
    await modelModeTrigger(page).click();
    await page.getByTestId("web-search-toggle").click();
    await expect(page.getByTestId("web-search-toggle")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await page.getByTestId("json-mode-toggle").click();
    await expect(page.getByTestId("json-mode-toggle")).toHaveAttribute(
      "aria-checked",
      "true",
    );

    // 3. ... then pick Extended reasoning effort behind the Advanced collapsible.
    await page.getByTestId("picker-advanced").click();
    await page.getByText("Extended", { exact: true }).click();
    await expect(modelModeTrigger(page)).toContainText("Extended");

    // Every popup change rode the existing preferences PUT path. Because each
    // PUT sends the WHOLE optimistic preferences object, the final body carries
    // all four flipped fields together.
    await expect
      .poll(
        () =>
          backend.bodies.some(
            (b) =>
              b.defaultTierId === "fast" &&
              b.defaultReasoningEffortId === "extended" &&
              b.webSearchDefault === true &&
              b.jsonModeDefault === true,
          ),
        { timeout: 5_000 },
      )
      .toBe(true);

    // Reload: the bootstrap route now serves the persisted prefs, so the popup
    // must reopen in the saved state rather than the hard defaults.
    await page.reload();
    await waitForBootstrap(page);

    await expect(modelModeTrigger(page)).toContainText("Fast");
    await expect(modelModeTrigger(page)).toContainText("Extended");

    await modelModeTrigger(page).click();
    await expect(page.getByTestId("web-search-toggle")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await expect(page.getByTestId("json-mode-toggle")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    // The persisted reasoning effort is also reflected behind Advanced.
    await page.getByTestId("picker-advanced").click();
    await expect(
      page.getByText("Cost high · Latency slow", { exact: true }),
    ).toBeVisible();
  });
});
