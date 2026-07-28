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

import { expect, test, type Page } from "./coverage-fixture";

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

async function enableWebSearch(page: Page): Promise<void> {
  await modelModeTrigger(page).click();
  await page.getByTestId("picker-advanced").click();
  const toggle = page.getByTestId("web-search-toggle");
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
      attribution?: { servedTierId?: string; servedModelLabel?: string };
    }>).find((m) => m.role === "assistant");
    expect(assistantMsg).toBeTruthy();
    const servedModelLabel =
      assistantMsg?.attribution?.servedModelLabel?.trim() ?? "";
    expect(servedModelLabel.length).toBeGreaterThan(0);
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

    // The model attribution / served-model label is visible (quiet public
    // phrasing: "Answered with {label}" — no router/tier jargon).
    const attribution = page.getByTestId("public-attribution").first();
    await expect(attribution).toBeVisible();
    await expect(attribution).toContainText(`Answered with ${servedModelLabel}`);

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
    // 1) Drive a real deep-research send (platform key; no Pro) so the BE
    // persists a subagent-tagged turn. Plan approval pauses before fan-out;
    // approve to get workers + synthesis. Nested generic tool groups are no
    // longer produced via coerce-to-single; web search nests under workers.
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);
    await enableWebSearch(page);

    let capturedConvId: string | null = null;
    page.on("request", (req) => {
      const m = req
        .url()
        .match(/\/api\/conversations\/([0-9a-fA-F-]{36})\/messages/);
      if (m && !capturedConvId) capturedConvId = m[1]!;
    });

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("DEEP_RESEARCH: alpha topic | beta topic");
    await page.getByTestId("composer-send").click();

    const paused = page.getByTestId("assistant-message").last();
    await expect(paused).toHaveAttribute("data-status", "awaiting_approval", {
      timeout: 15_000,
    });
    await paused.getByTestId("tool-approve").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 30_000,
    });
    const privatePanel = assistant.getByTestId("subagent-panel");
    await expect(privatePanel.getByTestId("web-search-panel").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect.poll(() => capturedConvId).not.toBeNull();
    const createdConvoId = capturedConvId!;

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
    // subagent panel, and web-search activity nests INSIDE it (parity with the
    // private thread — same AgenticAssistantParts primitive).
    const publicAssistant = page.getByTestId("public-assistant-message").last();
    await expect(publicAssistant).toBeVisible({ timeout: 15_000 });
    const panel = publicAssistant.getByTestId("subagent-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    const nestedSearch = panel.getByTestId("web-search-panel");
    await expect(nestedSearch.first()).toBeVisible({ timeout: 15_000 });
    const nestedCount = await nestedSearch.count();
    expect(nestedCount).toBeGreaterThan(0);
    await expect(publicAssistant.getByTestId("public-assistant-answer")).toBeVisible({
      timeout: 15_000,
    });
    await expect(publicAssistant.getByTestId("assistant-empty-fallback")).toHaveCount(0);
    // No standalone sibling web-search-panel leaked outside the panel.
    const totalSearchPanels = await publicAssistant
      .getByTestId("web-search-panel")
      .count();
    expect(totalSearchPanels).toBe(nestedCount);

    // NO cost figure anywhere on the page — the public contract is cost-free.
    const bodyText = (await page.locator("body").innerText()) ?? "";
    expect(bodyText).not.toMatch(/\$\s?\d/);

    // Read-only chrome: no composer is rendered on the public page.
    await expect(page.getByTestId("composer-textarea")).toHaveCount(0);
  });

  // FE-6 / GAP-6: the ungrounded honesty marker ("Answered without live
  // sources") used to be decided by two different rules. The private thread
  // asked `shouldShowSourcesInMainPanel`, which counts a `primary`-tagged list
  // as the main answer's; the share view hard-gated on `subagentId == null`, so
  // a `primary`-tagged empty catalog silently lost the marker on exactly the
  // surface where the transparency contract carries the most weight. Both
  // surfaces now read the one predicate and render the one component.
  //
  // `api/app/search/fake.py` always returns three results, so the zero-result
  // state comes from a route stub — applied identically to the private and the
  // public payload so any divergence is the renderers', not the fixture's.
  test("ungrounded marker appears on the share view", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableWebSearch(page);

    let capturedConvId: string | null = null;
    page.on("request", (req) => {
      const m = req
        .url()
        .match(/\/api\/conversations\/([0-9a-fA-F-]{36})\/messages/);
      if (m && !capturedConvId) capturedConvId = m[1]!;
    });

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("What is the latest on Playwright?");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    // Grounded control: real sources landed, so NEITHER surface shows the
    // marker. Without this half the test would pass on a renderer that always
    // draws it.
    await expect(assistant.getByTestId("sources-panel")).toBeVisible({
      timeout: 15_000,
    });
    await expect(assistant.getByTestId("ungrounded-marker")).toHaveCount(0);
    await expect.poll(() => capturedConvId).not.toBeNull();
    const convId = capturedConvId!;

    const shareResp = await page.request.post(
      `${BE_URL}/api/conversations/${convId}/share`,
    );
    expect(shareResp.status()).toBe(200);
    const share = await shareResp.json();

    await page.goto(share.sharePath);
    const publicAssistant = page.getByTestId("public-assistant-message").last();
    await expect(publicAssistant.getByTestId("public-assistant-answer")).toBeVisible({
      timeout: 15_000,
    });
    await expect(publicAssistant.getByTestId("ungrounded-marker")).toHaveCount(0);

    // Rewrite the persisted turn into the ungrounded state on BOTH payloads:
    // the search stays `requested`, its catalog empties, and the list is tagged
    // to a `primary` subagent — the shape whose marker the share view dropped.
    const asUngrounded = (parts: Array<Record<string, unknown>>) => {
      for (const part of parts) {
        if (part.type === "sources") {
          part.items = [];
          part.requested = true;
          part.subagentId = "primary";
        }
      }
      parts.push({
        type: "subagent",
        subagentId: "primary",
        label: "Answer",
        role: "primary",
        outcome: "succeeded",
      });
    };
    const stub = async (pattern: string) => {
      await page.route(pattern, async (route) => {
        if (route.request().method() !== "GET") return route.fallback();
        const response = await route.fetch();
        const body = (await response.json()) as {
          messages: Array<{ role: string; parts: Array<Record<string, unknown>> }>;
        };
        for (const message of body.messages) {
          if (message.role === "assistant") asUngrounded(message.parts);
        }
        await route.fulfill({ response, json: body });
      });
    };
    await stub(`**/api/share/${share.shareToken}`);
    await stub(`**/api/conversations/${convId}`);

    // The share view: the marker is back, and no empty sources panel takes its
    // place.
    await page.goto(share.sharePath);
    const reloadedPublic = page.getByTestId("public-assistant-message").last();
    await expect(reloadedPublic.getByTestId("ungrounded-marker")).toBeVisible({
      timeout: 15_000,
    });
    await expect(reloadedPublic.getByTestId("ungrounded-marker")).toHaveText(
      "Answered without live sources",
    );
    await expect(reloadedPublic.getByTestId("sources-panel")).toHaveCount(0);

    // ...and the private thread reads the same rule on the same payload shape.
    await page.goto("/");
    await waitForBootstrap(page);
    const row = page.locator(`[data-conversation-id="${convId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.getByTestId("sidebar-conversation-link").click();
    const reloadedPrivate = page.getByTestId("assistant-message").last();
    await expect(reloadedPrivate.getByTestId("ungrounded-marker")).toBeVisible({
      timeout: 15_000,
    });
    await expect(reloadedPrivate.getByTestId("sources-panel")).toHaveCount(0);
  });

  test("a non-404 server error shows the retryable error state", async ({
    page,
  }) => {
    // A 5xx (not a 404) is the "couldn't load" branch, distinct from the
    // unknown-token "no longer available" empty state below.
    let getCount = 0;
    await page.route("**/api/share/*", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      getCount += 1;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "INTERNAL",
            severity: "error",
            title: "Server error",
            body: "boom",
          },
        }),
      });
    });

    await page.goto("/share/server-error-token");

    await expect(
      page.getByRole("heading", { name: "Couldn't load this conversation" }),
    ).toBeVisible({ timeout: 15_000 });

    // "Try again" re-runs the fetch effect (bumps the attempt counter).
    const before = getCount;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect.poll(() => getCount, { timeout: 15_000 }).toBeGreaterThan(
      before,
    );
    // Still failing → stays on the error state, retry button still offered.
    await expect(
      page.getByRole("heading", { name: "Couldn't load this conversation" }),
    ).toBeVisible();
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
