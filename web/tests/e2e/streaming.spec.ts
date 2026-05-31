// Streaming path — the headline test.
//
// What this exercises beyond the in-process BE suite:
//   (a) the BROWSER opens an SSE stream against POST /api/conversations/:id/messages
//   (b) the browser receives FakeProvider reasoning deltas + answer deltas
//   (c) the browser sees a terminal frame and the UI commits the assistant turn
//   (d) the BE persists the assistant row (verified via a follow-up GET)
//
// We assert SSE content-type by capturing the response via a `page.on(...)`
// listener and reading headers off the Response handle. We deliberately do
// NOT use `page.waitForResponse` for the streaming POST: that path holds the
// Response object live for the duration of the awaited body and is fragile
// against a fast-completing SSE stream. A passive listener records the
// headers once and lets the browser own the body lifecycle end-to-end.

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

test.describe("streaming", () => {
  test("send a message: SSE opens, reasoning + answer stream, terminal lands, message persists", async ({
    page,
  }) => {
    // Drive the full UI flow rather than pre-creating via API: this is the
    // path that exercises the lazy-create-on-send branch in chat-thread.tsx
    // (`beginTurn` mints a conversation when none is active) AND streaming.
    await page.goto("/");
    await waitForBootstrap(page);

    // Record the conversation id and SSE headers as the network rolls past.
    // Both fire within ~50ms of the click; we read them with `expect.poll`
    // after the click so we never race the listener installation.
    let createdConvoId = "";
    let createStatus: number | undefined;
    let sseStatus: number | undefined;
    let sseContentType = "";

    page.on("response", async (response) => {
      const url = response.url();
      const method = response.request().method();
      if (url === `${BE_URL}/api/conversations` && method === "POST") {
        createStatus = response.status();
        if (createStatus === 201) {
          try {
            const json = (await response.json()) as { id?: unknown };
            if (typeof json.id === "string") createdConvoId = json.id;
          } catch {
            // The response may have already been consumed by the FE; that's
            // fine — we have the status, and the convo id will surface in
            // the SSE URL below.
          }
        }
      } else if (
        method === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(url)
      ) {
        sseStatus = response.status();
        sseContentType = response.headers()["content-type"] ?? "";
        if (!createdConvoId) {
          const m = url.match(/\/api\/conversations\/([^/]+)\/messages$/);
          if (m) createdConvoId = m[1];
        }
      }
    });

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("Hello from Playwright");
    await page.getByTestId("composer-send").click();

    // Wait for the create POST + SSE POST to complete header-wise.
    await expect.poll(() => createStatus, { timeout: 15_000 }).toBe(201);
    await expect.poll(() => sseStatus, { timeout: 15_000 }).toBe(200);
    // (a) SSE wire shape — text/event-stream content type.
    expect(sseContentType).toContain("text/event-stream");
    expect(createdConvoId).toBeTruthy();

    // (b) Reasoning panel materializes with the FakeProvider's reasoning text.
    // FakeProvider emits "Let me think" then "... OK" (see api/app/providers/fake.py).
    const reasoning = page.getByTestId("reasoning-panel");
    await expect(reasoning).toBeVisible({ timeout: 15_000 });
    await expect(reasoning).toContainText("Let me think", { timeout: 15_000 });
    await expect(reasoning).toContainText("OK");

    // (c) Answer text streams in. FakeProvider picks one of 8 templates by
    // sha256(user_text)[0] % 8. Rather than couple the test to the hash, we
    // wait for ANY non-empty assistant answer to appear.
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible();

    // (c) Terminal landed: the assistant-message wrapper carries
    // `data-status="done"` once the stream resolves. Until terminal, status
    // is "submitted"/"streaming"; the FE flips it via the wrapper attribute.
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // The answer text part is rendered with non-empty content.
    const answer = assistant.getByTestId("assistant-answer");
    await expect(answer).toBeVisible();
    await expect(answer).not.toHaveText("");

    // (d) BE round-trip: the assistant turn is persisted. The conversation
    // GET returns both the user message and the assistant message.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${createdConvoId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = await fetched.json();
    const messages: Array<{ role: string; parts: Array<{ type: string; text?: string }> }> =
      body.messages;
    const roles = messages.map((m) => m.role);
    expect(roles).toEqual(["user", "assistant"]);

    const userMsg = messages[0];
    expect(userMsg.parts.some((p) => p.type === "text" && p.text === "Hello from Playwright"))
      .toBe(true);

    const assistantMsg = messages[1];
    // FakeProvider always emits at least one reasoning + one text part.
    expect(assistantMsg.parts.some((p) => p.type === "reasoning")).toBe(true);
    expect(assistantMsg.parts.some((p) => p.type === "text" && (p.text ?? "").length > 0))
      .toBe(true);
  });

  // Web-search path. Requires the integrated BE running the FakeProvider with
  // web search wired (api/app/providers/fake.py emits a `status` event
  // "Searching the web…" — active then done — and a `sources` event with 3
  // deterministic items when the message-create carries `webSearch: true`; the
  // BE persists the `sources` part on the assistant row). This asserts the FE
  // half of the contract end-to-end:
  //   (a) toggling web search on sends `webSearch: true`
  //   (b) the "Searching the web…" status line shows WHILE data-status is
  //       streaming/submitted
  //   (c) the sources panel + >=1 source card render AFTER data-status="done"
  //   (d) the assistant row persists a `sources` part (GET round-trip)
  test("web search: status line shows while streaming, sources render after done, sources part persists", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Capture the message-create POST body to confirm `webSearch: true` rode
    // along, plus the conversation id from the SSE URL.
    let createdConvoId = "";
    let sentWebSearch: boolean | undefined;
    page.on("request", (request) => {
      const url = request.url();
      if (
        request.method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(url)
      ) {
        const m = url.match(/\/api\/conversations\/([^/]+)\/messages$/);
        if (m) createdConvoId = m[1];
        try {
          const body = request.postDataJSON() as { webSearch?: unknown };
          if (typeof body.webSearch === "boolean") sentWebSearch = body.webSearch;
        } catch {
          // Non-JSON body — leave `sentWebSearch` undefined; the assertion
          // below will flag it.
        }
      }
    });

    // Toggle web search ON via the model-mode picker. The default tier ("auto")
    // supports search, so the "Web search" section is present. Desktop project
    // (Desktop Chrome) → the dropdown variant; open it, then click the toggle.
    await page.getByTestId("model-mode-trigger").click();
    const toggle = page.getByTestId("web-search-toggle");
    await expect(toggle).toBeVisible({ timeout: 5_000 });
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    // Dismiss the dropdown so it doesn't overlay the composer.
    await page.keyboard.press("Escape");

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("What is the latest on Playwright?");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });

    // (b) The "Searching the web…" status line is visible while the turn is
    // still in flight (data-status submitted/streaming). The status part
    // renders an active spinner + the BE-provided label.
    await expect(assistant).toHaveAttribute("data-status", /submitted|streaming/, {
      timeout: 15_000,
    });
    await expect(assistant.getByText("Searching the web…")).toBeVisible({
      timeout: 15_000,
    });

    // (a) The create request carried webSearch: true.
    expect(sentWebSearch).toBe(true);

    // (c) Terminal lands; the sources panel + at least one source card render
    // after the answer settles.
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    const answer = assistant.getByTestId("assistant-answer");
    await expect(answer).toBeVisible();

    const sourcesPanel = assistant.getByTestId("sources-panel");
    await expect(sourcesPanel).toBeVisible({ timeout: 15_000 });
    const sourceCards = assistant.getByTestId("source-card");
    await expect(sourceCards.first()).toBeVisible({ timeout: 15_000 });
    expect(await sourceCards.count()).toBeGreaterThanOrEqual(1);

    // (d) BE round-trip: the assistant row persists a `sources` part whose
    // items carry the contract shape (id/title/url, optional snippet/domain).
    expect(createdConvoId).toBeTruthy();
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${createdConvoId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = await fetched.json();
    const messages: Array<{
      role: string;
      parts: Array<{
        type: string;
        items?: Array<{ id: number; title: string; url: string }>;
      }>;
    }> = body.messages;

    const assistantMsg = messages.find((m) => m.role === "assistant");
    expect(assistantMsg).toBeTruthy();
    const sourcesPart = assistantMsg!.parts.find((p) => p.type === "sources");
    expect(sourcesPart).toBeTruthy();
    expect(Array.isArray(sourcesPart!.items)).toBe(true);
    expect((sourcesPart!.items ?? []).length).toBeGreaterThanOrEqual(1);
    const first = (sourcesPart!.items ?? [])[0];
    expect(typeof first.id).toBe("number");
    expect(typeof first.title).toBe("string");
    expect(typeof first.url).toBe("string");

    // The sources part is ordered AFTER the answer text part (contract: sources
    // render after the answer).
    const textIdx = assistantMsg!.parts.findIndex((p) => p.type === "text");
    const sourcesIdx = assistantMsg!.parts.findIndex((p) => p.type === "sources");
    expect(textIdx).toBeGreaterThanOrEqual(0);
    expect(sourcesIdx).toBeGreaterThan(textIdx);
  });
});
