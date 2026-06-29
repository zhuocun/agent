// Human-in-the-loop (HITL) tool-approval path. Exercises the FE half end-to-end
// against the real BE + fake provider:
//   (a) sending `TOOL_APPROVE: <text>` pauses the turn — the assistant bubble
//       commits in place with a tool_call part carrying the "Needs approval"
//       pill + the approve/deny controls (no footer actions; it's not "done")
//   (b) the bubble's data-status is `awaiting_approval`
//   (c) clicking Approve / Deny keeps the paused bubble (its pending tool_call
//       stays put — the FE mirrors continue and never mutates it) AND appends a
//       NEW assistant bubble carrying the fake's deterministic post-tool answer
//       ("…tool approved: …" / "…tool denied: …") + the resolved tool_result
//       (approved → "Approved" / denied → "Rejected")
//   (d) NO duplicate user bubble is created (the resume reuses the user turn,
//       exactly like continue)
//   (e) a GET round-trip shows two assistant rows
//
// The fake provider only emits the tool_call on the `TOOL_APPROVE:` marker, and
// resolves it on the resume POST that carries `toolApproval` (approve→succeeded,
// deny→rejected). See api/app/providers/fake.py + TOOLS_ENABLED in
// shared-config.ts.

import { expect, test, type Page } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

// Drive a fresh chat to the awaiting-approval pause. Returns the conversation id
// captured from the streaming POST URL. Polls the BE for the persisted
// `awaiting_approval` row before returning so the resume POST (which the BE keys
// off that paused turn) can't race persistence — mirrors the continue test's
// stopped-row poll.
async function sendAndPause(page: Page): Promise<string> {
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
  await composer.fill("TOOL_APPROVE: book a meeting");
  await page.getByTestId("composer-send").click();

  // The assistant bubble materializes with the tool_call part carrying the
  // "Needs approval" pill — the deterministic marker the fake provider emits for
  // calendar_create_event.
  const paused = page.getByTestId("assistant-message").last();
  await expect(paused).toBeVisible({ timeout: 15_000 });
  const toolCall = paused.getByTestId("tool-call-part");
  await expect(toolCall).toBeVisible({ timeout: 15_000 });
  await expect(toolCall).toContainText("Needs approval", { timeout: 15_000 });

  // (b) The bubble settles into the `awaiting_approval` terminal — not "done",
  // not "streaming". This is the HITL pause.
  await expect(paused).toHaveAttribute("data-status", "awaiting_approval", {
    timeout: 15_000,
  });

  // The approve/deny controls render on the paused tool_call.
  await expect(paused.getByTestId("tool-approve")).toBeVisible();
  await expect(paused.getByTestId("tool-deny")).toBeVisible();

  // Confirm the BE persisted the `awaiting_approval` row before deciding — a
  // resume POST that races persistence would have no paused turn to resume.
  await expect.poll(() => capturedConvId).not.toBeNull();
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
          (m) => m.role === "assistant" && m.status === "awaiting_approval",
        );
      },
      { timeout: 8_000, intervals: [250] },
    )
    .toBe(true);

  return capturedConvId!;
}

test.describe("tool approval (HITL)", () => {
  test("approve a tool call: keeps the paused bubble, appends the post-tool answer, no duplicate user turn", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const convId = await sendAndPause(page);

    // Exactly one user bubble before deciding (the resume must not mint another).
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);

    const paused = page.getByTestId("assistant-message").last();
    await paused.getByTestId("tool-approve").click();

    // (c) A NEW assistant bubble streams the deterministic post-tool answer.
    await expect
      .poll(
        async () => {
          const texts = await page
            .getByTestId("assistant-message")
            .getByTestId("assistant-answer")
            .allInnerTexts();
          return texts.some((t) => t.includes("tool approved: "));
        },
        { timeout: 15_000 },
      )
      .toBe(true);

    // Two assistant bubbles now: the paused one + the continuation. The paused
    // bubble is NOT removed (resume, like continue, keeps it) and still carries
    // its tool_call part.
    await expect(page.getByTestId("assistant-message")).toHaveCount(2);
    const pausedAfter = page.getByTestId("assistant-message").first();
    await expect(pausedAfter.getByTestId("tool-call-part")).toBeVisible();

    // The resolved tool_result renders on the resumed (second) bubble with the
    // `approved` outcome — its "Approved" approval pill shows (approve →
    // approvalState "approved", status "succeeded").
    const resumed = page.getByTestId("assistant-message").last();
    const resolvedResult = resumed.getByTestId("tool-result-part");
    await expect(resolvedResult).toBeVisible({ timeout: 15_000 });
    await expect(resolvedResult).toContainText("Approved");

    // CRITICAL: still exactly ONE user bubble — the resume reuses the user turn
    // and must not mint a duplicate (continue-style invariant).
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);

    // (e) BE round-trip: two assistant rows persisted (the paused turn + the
    // resumed post-tool answer).
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = (await fetched.json()) as {
      messages: Array<{ role: string }>;
    };
    const assistantRows = body.messages.filter((m) => m.role === "assistant");
    expect(assistantRows.length).toBe(2);
  });

  test("deny a tool call: renders the rejected result, the answer reflects denial, no duplicate user turn", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const convId = await sendAndPause(page);

    await expect(page.getByTestId("user-message-text")).toHaveCount(1);

    const paused = page.getByTestId("assistant-message").last();
    await paused.getByTestId("tool-deny").click();

    // The new assistant bubble streams the denial answer.
    await expect
      .poll(
        async () => {
          const texts = await page
            .getByTestId("assistant-message")
            .getByTestId("assistant-answer")
            .allInnerTexts();
          return texts.some((t) => t.includes("tool denied: "));
        },
        { timeout: 15_000 },
      )
      .toBe(true);

    // Two assistant bubbles: the paused one (kept) + the denial continuation.
    await expect(page.getByTestId("assistant-message")).toHaveCount(2);
    const pausedAfter = page.getByTestId("assistant-message").first();
    await expect(pausedAfter.getByTestId("tool-call-part")).toBeVisible();

    // The rejected tool_result renders on the resumed (second) bubble (deny →
    // approvalState "rejected", status "failed"/"rejected").
    const resumed = page.getByTestId("assistant-message").last();
    const rejectedResult = resumed.getByTestId("tool-result-part");
    await expect(rejectedResult).toBeVisible({ timeout: 15_000 });
    await expect(rejectedResult).toContainText("Rejected");

    // Still exactly ONE user bubble.
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);

    // BE round-trip: two assistant rows persisted.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = (await fetched.json()) as {
      messages: Array<{ role: string }>;
    };
    const assistantRows = body.messages.filter((m) => m.role === "assistant");
    expect(assistantRows.length).toBe(2);
  });
});
