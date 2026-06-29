// Tool-call aggregation — FE↔BE e2e against the real BE + fake provider.
//
// A turn that produces >=2 contiguous SETTLED tool runs folds into a single
// collapsed `tool-group-panel` (see web/src/lib/tool-groups.ts +
// tool-group-panel.tsx) instead of rendering a wall of identical tool cards.
//
// The `TOOL_MULTI:` marker drives the fake provider to request TWO auto
// `get_current_time` calls in round 1 (distinct ids + timezones); the agent
// loop executes both, emits two succeeded `tool_result`s, and re-invokes the
// stream for the grounded answer (see api/app/providers/fake.py +
// app/tools/agent_loop.py). The committed turn therefore carries a span of two
// settled runs.
//
// Assertions:
//   (a) the panel renders, collapsed by default — its `tool-result-part` rows
//       are NOT visible until the trigger is clicked (keepMounted but hidden)
//   (b) the summary reads "2 calls"
//   (c) clicking `tool-group-trigger` reveals exactly two `tool-result-part`
//       rows inside the panel
//   (d) the grouping survives a full reload (it derives from the persisted
//       call+result parts, not live stream state)

import { expect, test, type Page } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

// Send `TOOL_MULTI: …` and wait for the assistant turn to settle as done.
// Returns the conversation id captured from the create POST so a reload can
// re-open the same thread.
async function sendMultiTool(page: Page): Promise<string> {
  const composer = page.getByTestId("composer-textarea");
  await composer.fill("TOOL_MULTI: what time is it");

  const createPromise = page.waitForResponse(
    (r) =>
      r.url() === `${BE_URL}/api/conversations` &&
      r.request().method() === "POST",
  );
  await page.getByTestId("composer-send").click();

  const createResp = await createPromise;
  const { id: convId } = (await createResp.json()) as { id: string };
  expect(convId).toBeTruthy();

  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toHaveAttribute("data-status", "done", {
    timeout: 15_000,
  });

  // Regression guard for the blank-after-tools bug: the settled turn must
  // carry a written answer body — never a bubble that's nothing but the tool
  // panel. (When the model genuinely returns no synthesis the FE shows the
  // calm `assistant-empty-fallback` instead; here the fake provider always
  // re-invokes for a grounded answer.)
  await expect(assistant.getByTestId("assistant-answer")).toBeVisible({
    timeout: 15_000,
  });
  return convId;
}

// Assert the panel is on screen, collapsed (its rows hidden), and that
// expanding it reveals exactly two settled `tool-result-part` rows.
async function expectCollapsedThenExpand(page: Page): Promise<void> {
  const assistant = page.getByTestId("assistant-message").last();
  const panel = assistant.getByTestId("tool-group-panel");
  await expect(panel).toBeVisible({ timeout: 15_000 });

  // The grounded answer body survives the cold-render path (it persists
  // alongside the call+result parts), so the reloaded bubble is never blank.
  await expect(assistant.getByTestId("assistant-answer")).toBeVisible({
    timeout: 15_000,
  });
  // Regression: answerText must include reloaded text (subagentId: null), so
  // the empty-fallback note must not appear when an answer is on screen.
  await expect(assistant.getByTestId("assistant-empty-fallback")).toHaveCount(0);

  // The folded summary counts both runs.
  await expect(panel.getByTestId("tool-group-trigger")).toContainText("2 calls");

  // (a) Collapsed by default — the run rows are mounted (keepMounted) but the
  // panel hides them, so none are visible before the trigger is clicked.
  const resultRows = panel.getByTestId("tool-result-part");
  await expect(resultRows.first()).toBeHidden();

  // (c) Expand → the two settled run rows become visible.
  await panel.getByTestId("tool-group-trigger").click();
  await expect(resultRows).toHaveCount(2);
  await expect(resultRows.first()).toBeVisible();
  await expect(resultRows.last()).toBeVisible();
}

test.describe("tool-call aggregation (tool group panel)", () => {
  test("a turn with >=2 settled tools renders a collapsed panel that expands to the run rows", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const convId = await sendMultiTool(page);

    // No flat tool cards leaked outside the panel — the two runs are folded.
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant.getByTestId("tool-group-panel")).toHaveCount(1);

    await expectCollapsedThenExpand(page);

    // (d) BE round-trip: the assistant row persisted the call + result parts so
    // the grouping re-derives on a cold render.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = (await fetched.json()) as {
      messages: Array<{ role: string; parts: Array<{ type: string }> }>;
    };
    const assistantRow = body.messages.filter((m) => m.role === "assistant").at(-1)!;
    const toolCalls = assistantRow.parts.filter((p) => p.type === "tool_call");
    const toolResults = assistantRow.parts.filter((p) => p.type === "tool_result");
    expect(toolCalls.length).toBe(2);
    expect(toolResults.length).toBe(2);
  });

  test("the grouped panel re-renders collapsed after a full reload", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const convId = await sendMultiTool(page);

    // Full nav reload, then re-open the thread from the sidebar so the parts
    // come back via GET /api/conversations/:id (the cold-render grouping path).
    await page.reload();
    await waitForBootstrap(page);

    const row = page.locator(`[data-conversation-id="${convId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    const getPromise = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convId}` &&
        r.request().method() === "GET",
    );
    await row.getByTestId("sidebar-conversation-link").click();
    expect((await getPromise).status()).toBe(200);

    await expectCollapsedThenExpand(page);
  });
});
