// Confirmed frontend bug hunt. Each test fails on the pre-fix behavior:
// F1 abandoned first-send create still posts, F2 a superseded preferences PUT
// can land last, F3 any HTTP 409 is treated as still-generating, F4 a failed
// delete clears the open transcript or leaves two sidebar rows for one id,
// F5 a public share drops attachment names.

import { expect, test, type Page, type Route } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

const STILL_GENERATING = "A response is still generating";
const STILL_FINISHING = "still finishing";

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve: () => void = () => {};
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function enableCompare(page: Page): Promise<void> {
  await page.keyboard.press("ControlOrMeta+k");
  const input = page.getByPlaceholder("Search actions & chats…");
  await expect(input).toBeVisible();
  await input.fill("Compare");
  await page.getByRole("option", { name: "Compare models" }).click();
  await expect(page.getByTestId("compare-tier-bar")).toBeVisible();
}

async function exitCompare(page: Page): Promise<void> {
  await page.keyboard.press("ControlOrMeta+k");
  const input = page.getByPlaceholder("Search actions & chats…");
  await expect(input).toBeVisible();
  await input.fill("Exit compare");
  await page.getByRole("option", { name: "Exit compare" }).click();
  await expect(page.getByTestId("compare-tier-bar")).toHaveCount(0);
}

/** Hold POST /api/conversations until the test releases each one, in order. */
async function holdConversationCreates(page: Page): Promise<{
  release: (index: number) => void;
  count: () => number;
}> {
  const gates: Array<ReturnType<typeof deferred>> = [];
  await page.route(/\/api\/conversations$/, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    const gate = deferred();
    gates.push(gate);
    await gate.promise;
    await route.fallback();
  });
  return {
    release: (index: number) => {
      gates[index]?.resolve();
    },
    count: () => gates.length,
  };
}

function trackMessagePosts(page: Page): string[] {
  const bodies: string[] = [];
  page.on("request", (req) => {
    if (
      req.method() === "POST" &&
      /\/api\/conversations\/[^/]+\/messages$/.test(req.url())
    ) {
      bodies.push(`${req.url()}\n${req.postData() ?? ""}`);
    }
  });
  return bodies;
}

async function openSettings(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
}

test.describe("bug hunt frontend", () => {
  test("F1 selecting a chat during first-send create does not start or switch", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    expect(created.status()).toBe(201);
    const { id: existingId } = (await created.json()) as { id: string };

    const creates = await holdConversationCreates(page);
    const messagePosts = trackMessagePosts(page);

    await page.goto("/");
    await waitForBootstrap(page);

    const existingRow = page.locator(`[data-conversation-id="${existingId}"]`);
    await expect(existingRow).toBeVisible();

    const prompt = "abandoned first send alpha";
    await page.getByTestId("composer-textarea").fill(prompt);
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("user-message-text")).toContainText(prompt);
    await expect.poll(() => creates.count()).toBe(1);

    await existingRow.getByTestId("sidebar-conversation-link").click();
    await expect(
      existingRow.getByTestId("sidebar-conversation-link"),
    ).toHaveAttribute("aria-current", "page");

    creates.release(0);
    // Give a leaked start() time to POST the original prompt.
    await page.waitForTimeout(1500);

    expect(messagePosts).toEqual([]);
    const selected = existingRow
      .locator('[data-testid="sidebar-conversation-link"]')
      .locator("visible=true");
    await expect(selected).toHaveAttribute("aria-current", "page");
  });

  test("F1 stop then resend does not post the first text", async ({ page }) => {
    const creates = await holdConversationCreates(page);
    const messagePosts = trackMessagePosts(page);

    await page.goto("/");
    await waitForBootstrap(page);

    const first = "first prompt must not post";
    const second = "second prompt should post";
    await page.getByTestId("composer-textarea").fill(first);
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("user-message-text")).toContainText(first);
    await expect.poll(() => creates.count()).toBe(1);

    await page.getByRole("button", { name: "Stop generating" }).click();
    await expect(page.getByTestId("user-message-text")).toHaveCount(0);

    await page.getByTestId("composer-textarea").fill(second);
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("user-message-text")).toContainText(second);
    await expect.poll(() => creates.count()).toBe(2);

    // The second beginTurn has cleared the old abort flag. Releasing the first
    // create now is what used to POST the abandoned text.
    creates.release(0);
    await page.waitForTimeout(1500);
    expect(messagePosts.some((body) => body.includes(first))).toBe(false);

    creates.release(1);
    await expect
      .poll(() => messagePosts.some((body) => body.includes(second)), {
        timeout: 15_000,
      })
      .toBe(true);
    expect(messagePosts.some((body) => body.includes(first))).toBe(false);
  });

  test("F1 compare create that resolves after leaving and re-entering does not fan out", async ({
    page,
  }) => {
    const creates = await holdConversationCreates(page);
    const messagePosts = trackMessagePosts(page);

    await page.goto("/");
    await waitForBootstrap(page);
    await enableCompare(page);

    const prompt = "abandoned compare prompt";
    await page.getByTestId("composer-textarea").fill(prompt);
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("user-message-text")).toContainText(prompt);
    await expect.poll(() => creates.count()).toBe(1);

    await exitCompare(page);
    await enableCompare(page);

    creates.release(0);
    await page.waitForTimeout(1500);

    expect(messagePosts.some((body) => body.includes(prompt))).toBe(false);
    await expect(page.getByText(prompt)).toHaveCount(0);
  });

  test("F2 a superseded preferences PUT keeps Forever", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);

    const puts: Array<{ retentionDays?: number | null }> = [];
    let firstAborted = false;
    const firstGate = deferred();
    page.on("requestfailed", (req) => {
      if (req.method() === "PUT" && req.url() === `${BE_URL}/api/preferences`) {
        firstAborted = true;
      }
    });

    await page.route(/\/api\/preferences$/, async (route: Route) => {
      try {
        if (route.request().method() !== "PUT") {
          await route.fallback();
          return;
        }
        const body = route.request().postDataJSON() as {
          retentionDays?: number | null;
        };
        puts.push(body);
        if (puts.length === 1) {
          await firstGate.promise;
          // A client abort rejects the page fetch, but Playwright will still
          // forward a stalled route unless we refuse it. Forward only when the
          // browser did not abort, so a non-aborted 30-day body can land last.
          await new Promise((resolve) => setTimeout(resolve, 200));
          const failure = route.request().failure();
          if (failure || firstAborted) {
            firstAborted = true;
            return;
          }
          await route.fallback();
          return;
        }
        await route.fallback();
      } catch {
        firstAborted = true;
      }
    });

    const dialog = page.getByRole("dialog", { name: "Settings" });
    const retention = dialog.getByRole("group", { name: "Chat retention" });
    const forever = retention.getByRole("button", { name: "Forever" });

    await retention.getByRole("button", { name: "30 days" }).click();
    await expect.poll(() => puts.length).toBe(1);
    expect(puts[0]?.retentionDays).toBe(30);

    const followUp = page.waitForResponse(
      (response) =>
        response.url() === `${BE_URL}/api/preferences` &&
        response.request().method() === "PUT" &&
        response.status() === 204,
    );
    await forever.click();
    await followUp;
    await expect.poll(() => puts.length).toBeGreaterThanOrEqual(2);
    expect(puts.slice(1).some((body) => body.retentionDays === null)).toBe(true);

    firstGate.resolve();
    await page.waitForTimeout(500);

    await expect(forever).toHaveAttribute("aria-pressed", "true");
    const bootstrap = await page.request.get(`${BE_URL}/api/bootstrap`);
    expect(bootstrap.ok()).toBe(true);
    const saved = (await bootstrap.json()) as {
      preferences: { retentionDays: number | null };
    };
    expect(saved.preferences.retentionDays).toBeNull();
    expect(firstAborted).toBe(true);
  });

  test("F2 a failed follow-up does not restore an aborted retention", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await openSettings(page);

    const puts: Array<{ retentionDays?: number | null }> = [];
    const firstGate = deferred();
    let held = false;

    await page.route(/\/api\/preferences$/, async (route) => {
      if (route.request().method() !== "PUT") {
        await route.fallback();
        return;
      }
      const body = route.request().postDataJSON() as {
        retentionDays?: number | null;
      };
      puts.push(body);
      if (!held) {
        held = true;
        await firstGate.promise;
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "PREFERENCES_FAILED",
            severity: "error",
            title: "Couldn't save your preferences",
            body: "Try again.",
          },
        }),
      });
    });

    const dialog = page.getByRole("dialog", { name: "Settings" });
    const retention = dialog.getByRole("group", { name: "Chat retention" });
    const forever = retention.getByRole("button", { name: "Forever" });
    const thirty = retention.getByRole("button", { name: "30 days" });

    await thirty.click();
    await expect.poll(() => puts.length).toBe(1);
    expect(puts[0]?.retentionDays).toBe(30);

    await forever.click();
    await expect.poll(() => puts.length).toBeGreaterThanOrEqual(2);
    await expect(page.getByRole("alert", { name: "Error" })).toContainText(
      "Couldn't save your preferences",
    );
    await expect(forever).toHaveAttribute("aria-pressed", "true");
    await expect(thirty).toHaveAttribute("aria-pressed", "false");

    const nextSave = page.waitForRequest(
      (request) =>
        request.url() === `${BE_URL}/api/preferences` &&
        request.method() === "PUT",
    );
    await dialog.getByRole("switch", { name: "Send on Enter" }).click();
    const saved = (await nextSave).postDataJSON() as {
      retentionDays?: number | null;
      sendOnEnter?: boolean;
    };
    expect(saved.retentionDays).toBeNull();
    expect(saved.sendOnEnter).toBe(false);
    firstGate.resolve();
  });

  test("bulk delete does not clear a chat opened while the request is in flight", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created: string[] = [];
    for (let i = 0; i < 3; i += 1) {
      const response = await page.request.post(`${BE_URL}/api/conversations`, {
        data: { selectedTierId: "smart", isTemporary: false },
      });
      expect(response.status()).toBe(201);
      created.push((await response.json()).id as string);
    }
    const [keepId, openId, otherId] = created;

    await page.goto("/");
    await waitForBootstrap(page);

    const visibleLink = (id: string) =>
      page
        .locator(`[data-conversation-id="${id}"]`)
        .locator('[data-testid="sidebar-conversation-link"]')
        .locator("visible=true");

    await visibleLink(keepId).click();
    await page.getByTestId("composer-textarea").fill("keep this chat");
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("assistant-message").last()).toHaveAttribute(
      "data-status",
      "done",
      { timeout: 15_000 },
    );

    await visibleLink(openId).click();
    await expect(page.getByTestId("user-message-text")).toHaveCount(0);

    await page.getByTestId("sidebar-select-toggle").click();
    await page
      .locator(`[data-conversation-id="${openId}"]`)
      .getByTestId("sidebar-conversation-checkbox")
      .click();
    await page
      .locator(`[data-conversation-id="${otherId}"]`)
      .getByTestId("sidebar-conversation-checkbox")
      .click();

    const gate = deferred();
    await page.route(/\/api\/conversations\/bulk$/, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await gate.promise;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ affected: 2 }),
      });
    });

    await page.getByTestId("sidebar-bulk-delete").click();
    await visibleLink(keepId).click();
    await expect(page.getByTestId("user-message-text")).toContainText(
      "keep this chat",
    );

    gate.resolve();
    await expect(page.getByTestId("user-message-text")).toContainText(
      "keep this chat",
    );
    await expect(visibleLink(keepId)).toHaveAttribute("aria-current", "page");
  });

  test("F3 an approval-conflict 409 is not treated as still generating", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("composer-textarea").fill("TOOL_APPROVE: book a meeting");
    await page.getByTestId("composer-send").click();

    const paused = page
      .getByTestId("assistant-message")
      .filter({ has: page.getByTestId("tool-call-part") });
    await expect(paused.getByTestId("tool-call-part")).toContainText(
      "Needs approval",
      { timeout: 15_000 },
    );
    await expect(paused.getByTestId("tool-approve")).toBeVisible();

    const conflictTitle = "That approval was already decided";
    await page.route(/\/api\/conversations\/[^/]+\/messages$/, async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "APPROVAL_DECISION_CONFLICT",
            severity: "warning",
            title: conflictTitle,
            body: "This action was already approved or denied.",
          },
        }),
      });
    });

    await paused.getByTestId("tool-approve").click();

    await expect(page.getByTestId("assistant-error")).toContainText(conflictTitle, {
      timeout: 15_000,
    });
    await expect(page.getByText(STILL_GENERATING)).toHaveCount(0);
    await expect(page.getByText(STILL_FINISHING)).toHaveCount(0);

    const card = page.getByTestId("tool-call-part").first();
    await expect(card).toContainText("Needs approval");
    await expect(card).not.toContainText("Running");
    const approve = paused.getByTestId("tool-approve");
    await expect(approve).toBeVisible();
    await expect(approve).toBeEnabled();
    await expect(paused.getByTestId("tool-deny")).toBeEnabled();
  });

  test("F4 a failed delete keeps the open transcript and highlight", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    let conversationId = "";
    page.on("response", (response) => {
      if (conversationId) return;
      const match = response
        .url()
        .match(/\/api\/conversations\/([^/]+)\/messages$/);
      if (match && response.request().method() === "POST") {
        conversationId = match[1] ?? "";
      }
    });

    const prompt = "persist this transcript";
    await page.getByTestId("composer-textarea").fill(prompt);
    await page.getByTestId("composer-send").click();
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect.poll(() => conversationId).toBeTruthy();

    await page.route(/\/api\/conversations\/[^/]+$/, async (route) => {
      if (route.request().method() !== "DELETE") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "DELETE_FAILED",
            severity: "error",
            title: "Couldn't delete conversation",
            body: "The conversation is still here.",
          },
        }),
      });
    });

    const row = page.locator(`[data-conversation-id="${conversationId}"]`);
    const link = row
      .locator('[data-testid="sidebar-conversation-link"]')
      .locator("visible=true");
    await expect(link).toHaveAttribute("aria-current", "page");
    await row.getByRole("button", { name: "Conversation actions" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Delete" }).click();

    await expect(
      page.getByRole("alert", { name: "Error" }),
    ).toContainText("Couldn't delete conversation");
    await expect(page.getByTestId("user-message-text")).toContainText(prompt);
    // The optimistic removal keeps an exiting copy until the collapse ends.
    await expect(link).toHaveCount(1, { timeout: 3_000 });
    await expect(link).toHaveAttribute("aria-current", "page");
  });

  test("F4 a failed delete does not replace a chat opened while it is in flight", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created: string[] = [];
    for (let i = 0; i < 2; i += 1) {
      const response = await page.request.post(`${BE_URL}/api/conversations`, {
        data: { selectedTierId: "smart", isTemporary: false },
      });
      expect(response.status()).toBe(201);
      created.push((await response.json()).id as string);
    }
    const [keepId, openId] = created;

    await page.goto("/");
    await waitForBootstrap(page);

    const visibleLink = (id: string) =>
      page
        .locator(`[data-conversation-id="${id}"]`)
        .locator('[data-testid="sidebar-conversation-link"]')
        .locator("visible=true");

    await visibleLink(keepId).click();
    await page.getByTestId("composer-textarea").fill("alpha stays");
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("assistant-message").last()).toHaveAttribute(
      "data-status",
      "done",
      { timeout: 15_000 },
    );

    await visibleLink(openId).click();
    await page.getByTestId("composer-textarea").fill("beta was open");
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("assistant-message").last()).toHaveAttribute(
      "data-status",
      "done",
      { timeout: 15_000 },
    );

    const gate = deferred();
    await page.route(/\/api\/conversations\/[^/]+$/, async (route) => {
      if (route.request().method() !== "DELETE") {
        await route.fallback();
        return;
      }
      await gate.promise;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "DELETE_FAILED",
            severity: "error",
            title: "Couldn't delete conversation",
            body: "The conversation is still here.",
          },
        }),
      });
    });

    const openRow = page.locator(`[data-conversation-id="${openId}"]`);
    await openRow.getByRole("button", { name: "Conversation actions" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Delete" }).click();

    await visibleLink(keepId).click();
    await expect(page.getByTestId("user-message-text")).toContainText(
      "alpha stays",
    );

    gate.resolve();
    await expect(
      page.getByRole("alert", { name: "Error" }),
    ).toContainText("Couldn't delete conversation");
    await expect(page.getByTestId("user-message-text")).toContainText(
      "alpha stays",
    );
    await expect(page.getByTestId("user-message-text")).not.toContainText(
      "beta was open",
    );
    await expect(visibleLink(keepId)).toHaveAttribute("aria-current", "page");
  });

  test("F4 a fast failed delete does not leave two sidebar rows for one id", async ({
    page,
  }) => {
    // ROW_EXIT_MS (250) plus the 80ms fallback is 330ms. A retry that long lets
    // the timer drop the exit snapshot, so the row looks healed. These checks
    // stay inside a shorter window, and the console record does not clear.
    const beforeCollapseMs = 100;
    const sameKeyWarnings: string[] = [];
    page.on("console", (message) => {
      const text = message.text();
      if (text.includes("two children with the same key")) {
        sameKeyWarnings.push(text);
      }
    });

    await page.goto("/");
    await waitForBootstrap(page);

    let conversationId = "";
    page.on("response", (response) => {
      if (conversationId) return;
      const match = response
        .url()
        .match(/\/api\/conversations\/([^/]+)\/messages$/);
      if (match && response.request().method() === "POST") {
        conversationId = match[1] ?? "";
      }
    });

    const prompt = "restore this sidebar row";
    await page.getByTestId("composer-textarea").fill(prompt);
    await page.getByTestId("composer-send").click();
    await expect(page.getByTestId("assistant-message").last()).toHaveAttribute(
      "data-status",
      "done",
      { timeout: 15_000 },
    );
    await expect.poll(() => conversationId).toBeTruthy();

    await page.route(/\/api\/conversations\/[^/]+$/, async (route) => {
      if (route.request().method() !== "DELETE") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "DELETE_FAILED",
            severity: "error",
            title: "Couldn't delete conversation",
            body: "The conversation is still here.",
          },
        }),
      });
    });

    const link = page
      .locator(`[data-conversation-id="${conversationId}"]`)
      .locator('[data-testid="sidebar-conversation-link"]')
      .locator("visible=true");
    await expect(link).toHaveAttribute("aria-current", "page");
    const row = page.locator(`[data-conversation-id="${conversationId}"]`);
    await row.getByRole("button", { name: "Conversation actions" }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Delete" }).click();

    await expect(
      page.getByRole("alert", { name: "Error" }),
    ).toContainText("Couldn't delete conversation");
    // Round-trip so the duplicate-key console record is in before the asserts.
    await page.evaluate(() => undefined);
    expect(sameKeyWarnings).toEqual([]);
    await expect(link).toBeEnabled({ timeout: beforeCollapseMs });
    await expect(link).toHaveAttribute("aria-current", "page", {
      timeout: beforeCollapseMs,
    });
  });

  test("F5 a public share shows an attachment-only user message name", async ({
    page,
  }) => {
    const fileName = "quarterly-report.pdf";
    await page.route(/\/api\/share\/[^/]+$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "11111111-1111-1111-1111-111111111111",
          title: "Shared files",
          messages: [
            {
              id: "22222222-2222-2222-2222-222222222222",
              role: "user",
              createdAt: "2026-01-01T00:00:00.000Z",
              parts: [
                {
                  type: "attachment",
                  id: "att-1",
                  name: fileName,
                  mediaType: "pdf",
                  mimeType: "application/pdf",
                  sizeBytes: 4096,
                  contentBase64: "SHOULD_NOT_RENDER_BYTES",
                },
              ],
            },
          ],
        }),
      });
    });

    await page.goto("/share/public-attachment-token");
    const bubble = page.getByTestId("public-user-message");
    await expect(bubble).toBeVisible();
    await expect(bubble).toContainText(fileName);
    await expect(bubble).toContainText("pdf");
    await expect(bubble).toContainText("4 KB");
    await expect(bubble).not.toContainText("SHOULD_NOT_RENDER_BYTES");
  });
});
