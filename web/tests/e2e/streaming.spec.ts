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
    let sentProviderId: unknown;
    page.on("request", (request) => {
      const url = request.url();
      if (
        request.method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(url)
      ) {
        const m = url.match(/\/api\/conversations\/([^/]+)\/messages$/);
        if (m) createdConvoId = m[1];
        try {
          const body = request.postDataJSON() as {
            providerId?: unknown;
            webSearch?: unknown;
          };
          sentProviderId = body.providerId;
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
    // The desktop toggle is a Base UI menu checkbox item
    // (role="menuitemcheckbox"), so its on-state is conveyed via aria-checked,
    // not aria-pressed.
    await expect(toggle).toHaveAttribute("aria-checked", "true");
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
    expect(typeof sentProviderId).toBe("string");
    expect((sentProviderId as string).length).toBeGreaterThan(0);

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

    // Provenance label ("From the web") renders on the sources panel.
    await expect(assistant.getByTestId("sources-provenance")).toHaveText(
      "From the web",
    );

    // Inline `[n]` citation markers: the fake grounded answer cites [1][2], so
    // those tokens render as interactive chips bound to source ids 1 and 2.
    // Activating one reveals (keeps visible) the matching source card.
    const citationMarkers = assistant.getByTestId("citation-marker");
    await expect(citationMarkers.first()).toBeVisible({ timeout: 15_000 });
    expect(await citationMarkers.count()).toBeGreaterThanOrEqual(2);
    await citationMarkers.first().click();
    // Activating the marker reveals the matching card: the panel stays visible
    // and the card picks up the transient highlight ring (primary box-shadow).
    const revealedCard = assistant.locator('[data-source-id="1"]').first();
    await expect(revealedCard).toBeVisible();
    await expect
      .poll(async () =>
        revealedCard.evaluate((el) => getComputedStyle(el).boxShadow),
      )
      .not.toBe("none");

    // (d) BE round-trip: the assistant row persists a `sources` part whose
    // items carry the contract shape (id/title/url, optional snippet/domain,
    // plus provenance) and `requested: true`.
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
        requested?: boolean;
        items?: Array<{
          id: number;
          title: string;
          url: string;
          provenance?: string;
        }>;
      }>;
    }> = body.messages;

    const assistantMsg = messages.find((m) => m.role === "assistant");
    expect(assistantMsg).toBeTruthy();
    const sourcesPart = assistantMsg!.parts.find((p) => p.type === "sources");
    expect(sourcesPart).toBeTruthy();
    // Grounded turn: web search was effective (`requested`) and resolved items.
    expect(sourcesPart!.requested).toBe(true);
    expect(Array.isArray(sourcesPart!.items)).toBe(true);
    expect((sourcesPart!.items ?? []).length).toBeGreaterThanOrEqual(1);
    const first = (sourcesPart!.items ?? [])[0];
    expect(typeof first.id).toBe("number");
    expect(typeof first.title).toBe("string");
    expect(typeof first.url).toBe("string");
    // Provenance defaults to "web" and round-trips through persistence.
    expect(first.provenance).toBe("web");

    // The sources part is ordered AFTER the answer text part (contract: sources
    // render after the answer).
    const textIdx = assistantMsg!.parts.findIndex((p) => p.type === "text");
    const sourcesIdx = assistantMsg!.parts.findIndex((p) => p.type === "sources");
    expect(textIdx).toBeGreaterThanOrEqual(0);
    expect(sourcesIdx).toBeGreaterThan(textIdx);
  });

  // JSON-mode (structured-output) path. Requires the integrated BE running the
  // FakeProvider with JSON mode wired: when the message-create carries
  // `responseFormat: { type: "json_object" }`, the fake emits the deterministic
  // answer `{"ok": true, "items": [1, 2, 3]}` (valid JSON) and the terminal
  // frame's attribution carries `outputFormat: "json_object"` /
  // `outputValid: true`. This asserts the FE half of the contract end-to-end:
  //   (a) toggling JSON mode on sends `responseFormat: { type: "json_object" }`
  //   (b) the assistant answer renders the JSON object text ("ok" + "items")
  //   (c) the "JSON" attribution chip appears on the assistant message
  test("json mode: toggle on sends responseFormat, answer renders JSON, attribution chip shows", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Capture the message-create POST body to confirm the `responseFormat`
    // object rode along.
    let sentResponseFormat: unknown;
    page.on("request", (request) => {
      const url = request.url();
      if (
        request.method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(url)
      ) {
        try {
          const body = request.postDataJSON() as { responseFormat?: unknown };
          if (body.responseFormat !== undefined) {
            sentResponseFormat = body.responseFormat;
          }
        } catch {
          // Non-JSON body — leave `sentResponseFormat` undefined; the assertion
          // below will flag it.
        }
      }
    });

    // Toggle JSON mode ON via the model-mode picker. Unlike web search, the
    // "JSON output" section is NOT tier-gated, so it's always present. Desktop
    // project (Desktop Chrome) → the dropdown variant; open it, click the toggle.
    await page.getByTestId("model-mode-trigger").click();
    const toggle = page.getByTestId("json-mode-toggle");
    await expect(toggle).toBeVisible({ timeout: 5_000 });
    await toggle.click();
    // The desktop toggle is a Base UI menu checkbox item
    // (role="menuitemcheckbox"), so its on-state is conveyed via aria-checked.
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    // Dismiss the dropdown so it doesn't overlay the composer.
    await page.keyboard.press("Escape");

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("Give me a structured result");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });

    // Terminal lands; the answer settles.
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // (a) The create request carried responseFormat: { type: "json_object" }.
    expect(sentResponseFormat).toEqual({ type: "json_object" });

    // (b) The assistant answer renders the deterministic JSON object: the fake
    // emits `{"ok": true, "items": [1, 2, 3]}` when JSON mode is requested.
    const answer = assistant.getByTestId("assistant-answer");
    await expect(answer).toBeVisible();
    await expect(answer).toContainText("ok", { timeout: 15_000 });
    await expect(answer).toContainText("items");

    // (c) The "JSON" attribution chip appears on the assistant message (valid
    // JSON → no "(invalid)" affordance).
    const jsonChip = assistant.getByTestId("json-output-chip");
    await expect(jsonChip).toBeVisible({ timeout: 15_000 });
    await expect(jsonChip).toContainText("JSON");
    await expect(jsonChip).not.toContainText("invalid");
  });

  // Mermaid rendering path. The FakeProvider emits a well-formed, closed
  // ```mermaid fence as its answer when the prompt starts with "MERMAID:" (see
  // api/app/providers/fake.py). This asserts the FE half: Streamdown's mermaid
  // plugin (markdown-renderer.tsx) renders the fence to an <svg> diagram rather
  // than leaving the raw "graph TD" source as a plain code block.
  test("mermaid: a fenced mermaid block renders as an svg diagram, not raw source", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("MERMAID: show a flowchart");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible({ timeout: 15_000 });

    // Wait for the terminal frame: the fence is only complete (and the diagram
    // only renders) once the stream resolves.
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    const answer = assistant.getByTestId("assistant-answer");
    await expect(answer).toBeVisible();

    // The diagram rendered: Streamdown emits a `data-streamdown="mermaid"`
    // container and mermaid renders an <svg> inside it. Headless mermaid render
    // can be slow, so give it a generous timeout.
    const svg = answer.locator('[data-streamdown="mermaid"] svg');
    await expect(svg.first()).toBeVisible({ timeout: 30_000 });

    // It did NOT fall through to a raw code block: no visible "graph TD" plain
    // source text. (The rendered SVG may contain shapes but not the literal
    // fenced source as a <code> block.)
    await expect(
      answer.locator("pre code", { hasText: "graph TD" }),
    ).toHaveCount(0);
  });

  // Continue-a-stopped-turn path. Exercises the FE half end-to-end:
  //   (a) Stop mid-stream produces a `stopped` assistant bubble (partial kept)
  //   (b) the Continue affordance shows ONLY on the stopped turn
  //   (c) clicking Continue keeps the stopped partial AND appends a NEW
  //       assistant bubble carrying the fake's deterministic continuation
  //   (d) NO duplicate user bubble is created (continue reuses the user turn)
  // The fake provider answers the continuation instruction with a distinctive
  // "…continued: " prefix (see api/app/providers/fake.py).
  test("continue a stopped turn: keeps the partial, appends a new bubble, no duplicate user turn", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Capture the conversation id authoritatively from the streaming POST URL
    // (the sidebar row id can lag the first send).
    let capturedConvId: string | null = null;
    page.on("request", (req) => {
      const m = req
        .url()
        .match(/\/api\/conversations\/([0-9a-fA-F-]{36})\/messages/);
      if (m && !capturedConvId) capturedConvId = m[1]!;
    });

    const composer = page.getByTestId("composer-textarea");

    // Produce a SERVER-CONFIRMED stopped turn. The partial assistant row is
    // persisted via the disconnect path, which is timing-nondeterministic in
    // this harness (the BE marks the mid-stream-disconnect persist xfail under
    // test transports — production works). `SLOW:` makes the fake stream ~40
    // deltas at 50ms each (api/app/providers/fake.py) for a wide stop window;
    // we stop a few deltas in (not at the first, which races the
    // reasoning→answer boundary), then retry the whole produce-stop-confirm
    // with a fresh chat until the BE commits the `stopped` row — so Continue
    // (which reads that row) has a real partial to extend.
    let partialBefore: string | null = null;
    for (let attempt = 0; partialBefore === null && attempt < 6; attempt++) {
      if (attempt > 0) {
        await page.getByRole("button", { name: "New chat" }).first().click();
        await expect(page.getByTestId("user-message-text")).toHaveCount(0);
      }
      capturedConvId = null;
      await composer.fill("SLOW: tell me a long story so I can stop it");
      await page.getByTestId("composer-send").click();

      const streaming = page.getByTestId("assistant-message").last();
      await expect(
        streaming.getByTestId("assistant-answer").first(),
      ).toContainText("part 5 ", { timeout: 15_000 });

      // Stop mid-stream (well within the ~2s slow window).
      await page.getByRole("button", { name: "Stop generating" }).click();
      await expect(streaming).toHaveAttribute("data-status", "stopped", {
        timeout: 15_000,
      });
      await expect(streaming.getByTestId("stopped-chip")).toBeVisible();

      // Confirm the BE committed the `stopped` row before continuing — a
      // continue POST that races persistence 400s NOTHING_TO_CONTINUE.
      await expect.poll(() => capturedConvId).not.toBeNull();
      try {
        await expect
          .poll(
            async () => {
              const r = await page.request.get(
                `${BE_URL}/api/conversations/${capturedConvId}`,
              );
              if (!r.ok()) return false;
              const body = (await r.json()) as {
                messages: Array<{ role: string; status?: string | null }>;
              };
              return body.messages.some(
                (m) => m.role === "assistant" && m.status === "stopped",
              );
            },
            { timeout: 6_000, intervals: [250] },
          )
          .toBe(true);
      } catch {
        continue; // not persisted this attempt — fresh chat and retry
      }
      partialBefore =
        (await streaming
          .getByTestId("assistant-answer")
          .first()
          .textContent()
          .catch(() => "")) ?? "";
    }
    expect(
      partialBefore,
      "the BE never persisted a stopped turn after retries",
    ).not.toBeNull();

    const stopped = page.getByTestId("assistant-message").last();
    // Exactly one user bubble in the (final) conversation.
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);

    // The Continue affordance is present on the stopped turn; Regenerate too.
    const continueBtn = stopped.getByTestId("continue-turn");
    await expect(continueBtn).toBeVisible();
    await continueBtn.click();

    // A NEW assistant bubble streams the deterministic continuation. We assert
    // on the LAST assistant message carrying the "…continued: " marker.
    await expect
      .poll(
        async () => {
          const texts = await page
            .getByTestId("assistant-message")
            .getByTestId("assistant-answer")
            .allInnerTexts();
          return texts.some((t) => t.includes("…continued: "));
        },
        { timeout: 15_000 },
      )
      .toBe(true);

    // Two assistant bubbles now: the stopped partial + the continuation. The
    // stopped one is NOT removed (continue, unlike regenerate, keeps it).
    await expect(page.getByTestId("assistant-message")).toHaveCount(2);
    const stoppedAfter = page
      .getByTestId("assistant-message")
      .filter({ has: page.getByTestId("stopped-chip") });
    await expect(stoppedAfter).toHaveCount(1);
    if (partialBefore) {
      await expect(stoppedAfter.getByTestId("assistant-answer").first()).toHaveText(
        partialBefore,
      );
    }

    // CRITICAL: still exactly ONE user bubble — continue reuses the user turn
    // and must not mint a duplicate.
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);
  });
});
