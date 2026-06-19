// Public-by-link share view path — the one UNAUTHENTICATED read surface.
//
// What this exercises that the in-process BE suite cannot:
//   (a) a real send persists a user + assistant turn (drives the UI like
//       streaming.spec, since the BE row is minted lazily on first send),
//   (b) POST /api/conversations/:id/share mints a token + relative sharePath,
//   (c) navigating to /share/{token} renders the conversation read-only:
//       the message text shows, the model attribution / served-model label is
//       visible, and NO dollar/cost figure appears anywhere (the public
//       contract is structurally cost-free — web/src/lib/types.ts),
//   (d) an unknown token shows the friendly "no longer available" empty state.
//
// The share page fetches client-side via the apiClient (FE `/api/*` rewrite),
// so navigating to /share/{token} issues a GET /api/share/{token} we can both
// observe and let the React app render.

import { expect, test, type Page } from "@playwright/test";

import { BE_URL, modelModeTrigger, waitForBootstrap } from "./helpers";

// Flip the Deep Research toggle ON via the model-mode picker (minimal copy of
// agentic.spec.ts's helper — the toggle is a Base UI menu checkbox item, so its
// on-state is aria-checked, not aria-pressed).
async function enableDeepResearch(page: Page): Promise<void> {
  await modelModeTrigger(page).click();
  const toggle = page.getByTestId("deep-research-toggle");
  await expect(toggle).toBeVisible({ timeout: 5_000 });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
}

test.describe("public share view", () => {
  test("a shared conversation renders read-only with attribution and no cost", async ({
    page,
  }) => {
    // 1) Drive a real send so the BE persists a user + assistant turn. This is
    // the lazy-create-on-send path (chat-thread.tsx `beginTurn`).
    await page.goto("/");
    await waitForBootstrap(page);

    let createdConvoId = "";
    page.on("response", (response) => {
      if (createdConvoId) return;
      const m = response
        .url()
        .match(/\/api\/conversations\/([^/]+)\/messages$/);
      if (m && response.request().method() === "POST") createdConvoId = m[1];
    });

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("Hello from the share spec");
    await page.getByTestId("composer-send").click();

    // Wait for the assistant turn to settle (terminal frame committed).
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect.poll(() => createdConvoId, { timeout: 15_000 }).toBeTruthy();

    // 2) Mint a share token. Owner-side route; the same browser context carries
    // the anon session cookie minted on bootstrap, so this request is owned.
    const shareResp = await page.request.post(
      `${BE_URL}/api/conversations/${createdConvoId}/share`,
    );
    expect(shareResp.status()).toBe(200);
    const share = await shareResp.json();
    expect(share.shareToken).toBeTruthy();
    expect(share.sharePath).toBe(`/share/${share.shareToken}`);

    // Read the persisted served-model label off the public payload so the
    // assertion isn't coupled to a specific registry label string.
    const publicResp = await page.request.get(
      `${BE_URL}/api/share/${share.shareToken}`,
    );
    expect(publicResp.status()).toBe(200);
    const publicConvo = await publicResp.json();
    const assistantMsg = (publicConvo.messages as Array<{
      role: string;
      attribution?: { servedModelLabel?: string };
    }>).find((m) => m.role === "assistant");
    expect(assistantMsg).toBeTruthy();
    const servedLabel = assistantMsg?.attribution?.servedModelLabel ?? "";
    expect(servedLabel.length).toBeGreaterThan(0);
    // The public payload structurally has no cost — guard the contract by
    // asserting cost-bearing KEYS are absent. We match serialized keys rather
    // than the bare word "cost": a substitution `reasonText` can legitimately
    // contain it (e.g. "Downgraded by router for cost/latency."), and that is
    // model attribution, not a cost field.
    expect(JSON.stringify(publicConvo)).not.toMatch(
      /"(costUsd|costConfidence|breakdown|subtotalUsd|sessionSurchargeUsd)"/,
    );

    // 3) Navigate to the public page (no auth needed — it's public-by-link).
    await page.goto(share.sharePath);

    // The user message text renders.
    await expect(
      page.getByTestId("public-user-message").filter({
        hasText: "Hello from the share spec",
      }),
    ).toBeVisible({ timeout: 15_000 });

    // The assistant answer renders (non-empty).
    const publicAnswer = page.getByTestId("public-assistant-answer").first();
    await expect(publicAnswer).toBeVisible();
    await expect(publicAnswer).not.toHaveText("");

    // The model attribution / served-model label is visible.
    const attribution = page.getByTestId("public-attribution").first();
    await expect(attribution).toBeVisible();
    await expect(attribution).toContainText(servedLabel);

    // NO cost figure anywhere on the page. The public contract is cost-free;
    // a "$" digit pattern would mean a leak. We scan the rendered body text.
    const bodyText = (await page.locator("body").innerText()) ?? "";
    expect(bodyText).not.toMatch(/\$\s?\d/);

    // Read-only chrome: no composer is rendered on the public page.
    await expect(page.getByTestId("composer-textarea")).toHaveCount(0);
  });

  test("shared agentic conversation renders subagent panel with nested tools and no cost", async ({
    page,
  }) => {
    // 1) Drive a real agentic send so the BE persists a subagent-tagged turn.
    await page.goto("/");
    await waitForBootstrap(page);
    // Deep Research toggle ON but NO Pro grant: `deep_research` is Pro/BYOK-gated,
    // so the BE coerces a non-entitled caller down to `single` mode (one
    // `primary` subagent). `TOOL_MULTI:` then drives the fake provider to request
    // two `get_current_time` calls that fold into one generic tool group owned by
    // `primary` — rendered nested inside the agent-activity (subagent) panel.
    await enableDeepResearch(page);

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("TOOL_MULTI: what time is it");

    const createPromise = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations` &&
        r.request().method() === "POST",
    );
    await page.getByTestId("composer-send").click();

    const createResp = await createPromise;
    const { id: createdConvoId } = (await createResp.json()) as { id: string };
    expect(createdConvoId).toBeTruthy();

    // Wait for the assistant turn to settle (terminal frame committed).
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // 2) Mint a share token. The same browser context carries the anon session
    // cookie minted on bootstrap, so this owner-side request is owned.
    const shareResp = await page.request.post(
      `${BE_URL}/api/conversations/${createdConvoId}/share`,
    );
    expect(shareResp.status()).toBe(200);
    const share = await shareResp.json();
    expect(share.shareToken).toBeTruthy();
    expect(share.sharePath).toBe(`/share/${share.shareToken}`);

    // The public payload structurally has no cost — guard the contract by
    // asserting cost-bearing KEYS are absent (same pattern as the test above).
    const publicResp = await page.request.get(
      `${BE_URL}/api/share/${share.shareToken}`,
    );
    expect(publicResp.status()).toBe(200);
    const publicConvo = await publicResp.json();
    expect(JSON.stringify(publicConvo)).not.toMatch(
      /"(costUsd|costConfidence|breakdown|subtotalUsd|sessionSurchargeUsd)"/,
    );

    // 3) Navigate to the public page (no auth needed — it's public-by-link).
    await page.goto(share.sharePath);

    // The agentic turn re-renders read-only: the assistant message carries the
    // subagent panel, and the folded generic tool group nests INSIDE it (parity
    // with the private thread — same AgenticAssistantParts primitive).
    const publicAssistant = page.getByTestId("public-assistant-message").first();
    await expect(publicAssistant).toBeVisible({ timeout: 15_000 });
    const panel = publicAssistant.getByTestId("subagent-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    const nestedTools = panel.getByTestId("tool-group-panel");
    await expect(nestedTools.first()).toBeVisible({ timeout: 15_000 });
    const nestedCount = await nestedTools.count();
    expect(nestedCount).toBeGreaterThan(0);
    // No standalone sibling tool-group-panel leaked outside the panel.
    const totalToolPanels = await publicAssistant
      .getByTestId("tool-group-panel")
      .count();
    expect(totalToolPanels).toBe(nestedCount);

    // NO cost figure anywhere on the page — the public contract is cost-free.
    const bodyText = (await page.locator("body").innerText()) ?? "";
    expect(bodyText).not.toMatch(/\$\s?\d/);

    // Read-only chrome: no composer is rendered on the public page.
    await expect(page.getByTestId("composer-textarea")).toHaveCount(0);
  });

  test("an unknown share token shows the unavailable empty state", async ({
    page,
  }) => {
    const notFound = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/share/does-not-exist` &&
        r.request().method() === "GET",
    );
    await page.goto("/share/does-not-exist");
    const resp = await notFound;
    expect(resp.status()).toBe(404);

    await expect(page.getByTestId("public-unavailable")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByText("This shared conversation is no longer available"),
    ).toBeVisible();
  });
});
