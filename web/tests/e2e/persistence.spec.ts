// Persistence path — cookie + DB + bootstrap survives a reload.
//
// The conversation + its messages must be present after a full page reload
// in the same browser context: that exercises (i) the cookie surviving the
// nav, (ii) the BE recognising the session, (iii) bootstrap returning the
// conversation summary, and (iv) the active-thread load fetching messages.

import { expect, test } from "./coverage-fixture";

import { BE_URL, sessionCookie, waitForBootstrap } from "./helpers";

test.describe("persistence across reload", () => {
  test("a sent message survives a full page reload", async ({
    page,
    context,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const sidBefore = await sessionCookie(context);
    expect(sidBefore).not.toBeNull();

    // Send a message via the UI, then wait for the assistant turn to land.
    const composer = page.getByTestId("composer-textarea");
    await composer.fill("Persist me across reloads");

    const createPromise = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations` &&
        r.request().method() === "POST",
    );
    const ssePromise = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(r.url()),
    );

    await page.getByTestId("composer-send").click();

    const createResp = await createPromise;
    const { id: convoId } = await createResp.json();
    expect(convoId).toBeTruthy();

    const sseResp = await ssePromise;
    expect(sseResp.status()).toBe(200);

    // Wait for terminal so the BE has finished persisting.
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // Reload — full nav, NOT SPA route change. Cookie must survive.
    const reloadBootstrap = page.waitForResponse(
      (r) => r.url() === `${BE_URL}/api/bootstrap` && r.request().method() === "GET",
    );
    await page.reload();
    const reloadResp = await reloadBootstrap;
    expect(reloadResp.status()).toBe(200);
    await waitForBootstrap(page);

    const sidAfter = await sessionCookie(context);
    expect(sidAfter?.value).toBe(sidBefore?.value);

    // Sidebar lists the persisted conversation (autogen title may have
    // landed via the detached title-autogen task — either "New chat" or a
    // FakeProvider-derived 5-word title is acceptable; we only assert the
    // row is present).
    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();

    // Open the conversation. This triggers GET /api/conversations/:id which
    // brings the messages back. We assert both messages re-render.
    const getPromise = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "GET",
    );
    await row.getByTestId("sidebar-conversation-link").click();
    const getResp = await getPromise;
    expect(getResp.status()).toBe(200);
    const body = await getResp.json();
    expect(body.messages.length).toBe(2);

    // UI confirms: the user bubble carries the original text, the assistant
    // bubble is final.
    await expect(
      page.getByTestId("user-message-text").filter({
        hasText: "Persist me across reloads",
      }),
    ).toBeVisible();
    await expect(
      page.getByTestId("assistant-message").last(),
    ).toHaveAttribute("data-status", "done");
  });
});
