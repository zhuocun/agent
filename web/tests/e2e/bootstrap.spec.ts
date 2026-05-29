// Bootstrap path — first paint surface.
//
// Asserts the cross-process pieces that the in-process BE tests cannot:
//   (a) the bootstrap network call succeeds against the real BE on :8000,
//   (b) the BE sets a session cookie on its own origin (NOT the FE's),
//   (c) the rendered shell carries the bootstrap-derived model tier list,
//   (d) a second visit reuses the same anonymous user (no duplicate row).

import { expect, test } from "@playwright/test";

import { BE_URL, sessionCookie, waitForBootstrap } from "./helpers";

test.describe("bootstrap", () => {
  test("first visit issues a credentialed bootstrap call, sets the session cookie on the BE origin, and renders the empty state", async ({
    page,
    context,
  }) => {
    // Race-free assertion: register the response listener BEFORE navigating
    // so we never miss the bootstrap response that fires on mount.
    const bootstrapResponsePromise = page.waitForResponse(
      (r) => r.url() === `${BE_URL}/api/bootstrap` && r.request().method() === "GET",
    );

    await page.goto("/");

    const bootstrapResponse = await bootstrapResponsePromise;
    expect(bootstrapResponse.status()).toBe(200);

    // The shell renders an aria-hidden placeholder until bootstrap resolves;
    // the composer's presence is the cleanest "shell is live" sentinel.
    await waitForBootstrap(page);

    // (b) Cookie is on the BE origin (:8000) — assertions against :3000
    // would always be empty even on a correctly working build. See brief
    // §traps "Cookie origin".
    const sid = await sessionCookie(context);
    expect(sid).not.toBeNull();
    expect(sid?.value.length ?? 0).toBeGreaterThan(0);

    // (c) UI rendered the empty/initial state with model tiers visible.
    // The model-mode-picker button carries the selected tier label as its
    // visible span text. The default tier is "auto" (label "Auto").
    await expect(page.getByText("Auto", { exact: true }).first()).toBeVisible();

    // Sidebar is also live — the "New chat" rail item appears on mount.
    await expect(page.getByTestId("sidebar-new-chat")).toBeVisible();

    // Welcome screen ("What's on your mind?") is the empty state.
    await expect(page.getByText("What's on your mind?")).toBeVisible();
  });

  test("bootstrap returns a camelCase JSON payload with the expected shape", async ({
    page,
  }) => {
    // Reading directly via `page.request` shares the cookie jar with the
    // browser context, so cookies set by a prior nav would carry through.
    // We don't navigate first — this exercises the cold-cookie path and
    // confirms the wire shape independently of the React app.
    const response = await page.request.get(`${BE_URL}/api/bootstrap`);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain("application/json");
    // CORS preflight is not triggered for a simple GET issued by the
    // Playwright client (it isn't a browser), but the JSON response should
    // still be camelCase — that's the FE↔BE contract.
    const body = await response.json();

    // Top-level shape per BootstrapResponse in apiClient.ts.
    expect(body).toHaveProperty("account");
    expect(body).toHaveProperty("preferences");
    expect(body).toHaveProperty("usage");
    expect(body).toHaveProperty("modelTiers");
    expect(body).toHaveProperty("suggestions");
    expect(body).toHaveProperty("conversations");

    // Spot-check camelCase keys on nested objects.
    expect(body.account).toHaveProperty("planLabel");
    expect(body.account).toHaveProperty("byokEnabled");
    expect(body.preferences).toHaveProperty("defaultTierId");
    expect(body.preferences).toHaveProperty("sendOnEnter");
    expect(body.usage).toHaveProperty("periodLabel");
    expect(body.usage).toHaveProperty("isByok");

    // Model tier list must include the four canonical tier ids (single
    // source of truth is api/app/providers/tiers.py).
    expect(Array.isArray(body.modelTiers)).toBe(true);
    const tierIds = (body.modelTiers as Array<{ id: string }>).map((t) => t.id).sort();
    expect(tierIds).toEqual(["auto", "fast", "pro", "smart"]);
  });

  test("second visit in the same context reuses the same anonymous user", async ({
    page,
    context,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const first = await sessionCookie(context);
    expect(first).not.toBeNull();

    // A second navigation in the same browser context should send the same
    // cookie back to the BE. The BE will look up the existing session row
    // and reuse the same user — no new cookie issued.
    const secondResponse = page.waitForResponse(
      (r) => r.url() === `${BE_URL}/api/bootstrap` && r.request().method() === "GET",
    );
    await page.goto("/");
    const response = await secondResponse;
    expect(response.status()).toBe(200);

    await waitForBootstrap(page);

    const second = await sessionCookie(context);
    expect(second).not.toBeNull();
    // Same signed cookie value => same session row => same user. (The BE
    // does not roll the cookie on every hit.)
    expect(second?.value).toBe(first?.value);

    // Belt-and-braces: the bootstrap response on the second visit must not
    // carry a Set-Cookie header for `sid`. (A duplicate user would always be
    // accompanied by a new Set-Cookie.)
    const setCookie = response.headers()["set-cookie"];
    expect(setCookie ?? "").not.toContain("sid=");
  });
});
