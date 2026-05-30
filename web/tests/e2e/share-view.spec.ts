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

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

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
