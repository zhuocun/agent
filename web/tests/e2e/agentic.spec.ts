// Agentic mode (Deep Research) — FE↔BE e2e against the fake provider.
//
// The BE runs with AGENTIC_ENABLED + AGENTIC_PLAN_APPROVAL + BILLING_BACKEND=fake
// (see shared-config.ts), so:
//   - bootstrap advertises `agenticEnabled: true` → the Deep Research toggle
//     renders in the model-mode picker
//   - `deep_research` uses the platform provider key (same as normal chat);
//     Pro/BYOK is NOT required. Platform spend stays gated by usage quotas.
//     (Pro grant helpers live in settings.spec.ts for unrelated billing coverage.)
//   - a deep-research turn pauses on the plan BEFORE any fan-out: the planner
//     surfaces a pseudo `agentic_plan_approval` tool_call with the decomposed
//     plan + cost estimate, reusing the shipped `awaiting_approval` terminal
//   - approving fans out one worker per planned sub-question (the fake
//     provider answers `DEEP_RESEARCH_WORKER:n:<q>` prompts deterministically)
//     and the aggregator streams the synthesized answer; denying produces a
//     labeled "plan was declined" synthesis with no fan-out
//
// The deterministic plan contract (api/app/agentic/planner.py): a prompt
// `DEEP_RESEARCH: a | b` decomposes into two sub-questions, so the fan-out
// shape (2 workers + synthesis) is stable.

import { expect, test, type Page } from "./coverage-fixture";

import { BE_URL, modelModeTrigger, waitForBootstrap } from "./helpers";

// Flip the Deep Research toggle ON via the model-mode picker (desktop
// dropdown variant — the chromium project). It sits in the picker's main
// toggle group, peer to Web search, so no Advanced expansion is needed.
async function enableDeepResearch(page: Page): Promise<void> {
  await modelModeTrigger(page).click();
  const toggle = page.getByTestId("deep-research-toggle");
  await expect(toggle).toBeVisible({ timeout: 5_000 });
  await toggle.click();
  // Base UI menu checkbox item → on-state is aria-checked, not aria-pressed.
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

// Drive a session to the plan-approval pause. Returns the conversation id
// (captured from the streaming POST URL) once the BE has PERSISTED the
// `awaiting_approval` row, so the approve/deny resume can't race persistence —
// mirrors tool-approval.spec.ts's sendAndPause.
async function sendAndPauseOnPlan(page: Page): Promise<string> {
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

  // The planner pauses the turn: the assistant bubble carries the pseudo
  // `agentic_plan_approval` tool_call ("Review research plan") with the
  // decomposed plan + cost estimate rendered in the structured detail.
  const paused = page.getByTestId("assistant-message").last();
  await expect(paused).toBeVisible({ timeout: 15_000 });
  const planCall = paused.getByTestId("tool-call-part");
  await expect(planCall).toBeVisible({ timeout: 15_000 });
  await expect(planCall).toContainText("Review research plan");
  const planDetail = planCall.getByTestId("plan-approval-detail");
  await expect(planDetail).toBeVisible();
  await expect(planDetail).toContainText("alpha topic");
  await expect(planDetail).toContainText("beta topic");
  await expect(planDetail.getByTestId("plan-approval-cost")).toBeVisible();

  // The pause reuses the shipped HITL terminal.
  await expect(paused).toHaveAttribute("data-status", "awaiting_approval", {
    timeout: 15_000,
  });
  await expect(paused.getByTestId("tool-approve")).toBeVisible();
  await expect(paused.getByTestId("tool-deny")).toBeVisible();

  // Wait for the BE to persist the paused row before deciding.
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

test.describe("agentic mode (deep research)", () => {
  test("toggle is hidden when bootstrap does not advertise agenticEnabled", async ({
    page,
  }) => {
    // Force the flag-off shape on an otherwise-real bootstrap response so the
    // rest of the shell hydrates normally.
    await page.route("**/api/bootstrap", async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as Record<string, unknown>;
      body.agenticEnabled = false;
      await route.fulfill({ response, json: body });
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await modelModeTrigger(page).click();
    // Control: the picker is open (the peer Web search toggle renders) but the
    // Deep Research toggle is absent.
    await expect(page.getByTestId("web-search-toggle")).toBeVisible();
    await expect(page.getByTestId("deep-research-toggle")).toHaveCount(0);
  });

  test("approve the plan: fan-out panel shows workers + synthesis, parts persist", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    // Capture every message-create POST body — the initial send AND the
    // approve resume must both carry agenticMode: "deep_research" (the resume
    // re-runs the orchestrator, so dropping the mode would silently degrade).
    const sentModes: unknown[] = [];
    page.on("request", (req) => {
      if (
        req.method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(req.url())
      ) {
        try {
          const body = req.postDataJSON() as { agenticMode?: unknown };
          sentModes.push(body.agenticMode);
        } catch {
          // Non-JSON body — the assertion below will flag it.
        }
      }
    });

    const convId = await sendAndPauseOnPlan(page);
    expect(sentModes).toEqual(["deep_research"]);

    const paused = page.getByTestId("assistant-message").last();
    await paused.getByTestId("tool-approve").click();

    // The resumed bubble fans out: the subagent panel lists one row per
    // worker plus the synthesis aggregator.
    const resumed = page.getByTestId("assistant-message").last();
    const panel = resumed.getByTestId("subagent-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(panel.getByTestId("subagent-row")).toHaveCount(3, {
      timeout: 15_000,
    });
    await expect(panel).toContainText("Worker 1");
    await expect(panel).toContainText("Worker 2");
    await expect(panel).toContainText("Synthesis");
    await expect(panel.getByTestId("run-cost-meter")).toBeVisible();
    // Worker intermediate findings stay in the panel; the synthesis answer does not.
    await expect(panel).toContainText("Worker 1 finding");
    await expect(panel).not.toContainText("Synthesis of 2 findings");

    // The aggregator's synthesized answer renders as the bubble's main answer
    // (the deterministic fake-worker findings, merged in plan order).
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    const answer = resumed.getByTestId("assistant-answer");
    await expect(answer).toContainText("Synthesis of 2 findings");
    await expect(answer).toContainText("alpha topic");
    await expect(answer).toContainText("beta topic");
    await expect(resumed.getByTestId("assistant-empty-fallback")).toHaveCount(0);

    // The resume rode with the mode; no duplicate user bubble was minted.
    expect(sentModes).toEqual(["deep_research", "deep_research"]);
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);

    // BE round-trip: the resumed assistant row persisted subagent marker
    // parts, so a reload re-renders the same grouped panel.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = (await fetched.json()) as {
      messages: Array<{
        role: string;
        parts: Array<{ type: string }>;
      }>;
    };
    const assistantRows = body.messages.filter((m) => m.role === "assistant");
    expect(assistantRows.length).toBe(2);
    const fanout = assistantRows[assistantRows.length - 1]!;
    expect(fanout.parts.some((p) => p.type === "subagent")).toBe(true);

    // Reload: persisted subagent parts must still render a written answer, not
    // the empty-fallback note.
    await page.reload();
    await waitForBootstrap(page);
    const row = page.locator(`[data-conversation-id="${convId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.getByTestId("sidebar-conversation-link").click();

    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("assistant-answer")).toContainText(
      "Synthesis of 2 findings",
    );
    await expect(reloaded.getByTestId("assistant-empty-fallback")).toHaveCount(0);
  });

  test("deny the plan: no fan-out, a labeled declined synthesis streams", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    await sendAndPauseOnPlan(page);

    const paused = page.getByTestId("assistant-message").last();
    await paused.getByTestId("tool-deny").click();

    // Declined → the orchestrator skips the fan-out and streams a labeled
    // (non-error) synthesis from the aggregator alone.
    const resumed = page.getByTestId("assistant-message").last();
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect(resumed.getByTestId("assistant-answer")).toContainText(
      "the research plan was declined",
    );
    await expect(resumed.getByTestId("assistant-empty-fallback")).toHaveCount(0);
    // Only the synthesis row — no workers ran.
    const panel = resumed.getByTestId("subagent-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("subagent-row")).toHaveCount(1);
    await expect(panel).toContainText("Synthesis");
    await expect(panel).not.toContainText("the research plan was declined");

    // The resume reused the user turn (continue-style invariant).
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);
  });

  test("web search during fan-out renders inside the agent activity panel", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);
    await enableWebSearch(page);

    const convId = await sendAndPauseOnPlan(page);

    const paused = page.getByTestId("assistant-message").last();
    await paused.getByTestId("tool-approve").click();

    const resumed = page.getByTestId("assistant-message").last();
    const panel = resumed.getByTestId("subagent-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 30_000,
    });

    const nestedSearch = panel.getByTestId("web-search-panel");
    await expect(nestedSearch.first()).toBeVisible({ timeout: 15_000 });
    const totalSearchPanels = await resumed.getByTestId("web-search-panel").count();
    const nestedCount = await nestedSearch.count();
    expect(totalSearchPanels).toBe(nestedCount);
    expect(nestedCount).toBeGreaterThan(0);

    // Per-run rows show human-readable queries, not raw tool-argument JSON.
    const firstNestedPanel = nestedSearch.first();
    await firstNestedPanel.getByTestId("web-search-trigger").click();
    const searchRuns = panel.getByTestId("web-search-run");
    await expect(searchRuns.first()).toBeVisible({ timeout: 15_000 });
    await expect(searchRuns.first()).toContainText("alpha topic");
    await expect(panel).not.toContainText('{"query"');

    // Each subagent row shows at most one aggregated web-search panel.
    const rows = panel.getByTestId("subagent-row");
    const rowCount = await rows.count();
    for (let i = 0; i < rowCount; i++) {
      const panelsInRow = await rows.nth(i).getByTestId("web-search-panel").count();
      expect(panelsInRow).toBeLessThanOrEqual(1);
    }

    // Reload should keep web search nested under agent activity.
    await page.reload();
    await waitForBootstrap(page);
    const row = page.locator(`[data-conversation-id="${convId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.getByTestId("sidebar-conversation-link").click();

    const reloaded = page.getByTestId("assistant-message").last();
    const reloadedPanel = reloaded.getByTestId("subagent-panel");
    await expect(reloadedPanel.getByTestId("web-search-panel").first()).toBeVisible({
      timeout: 15_000,
    });
    const reloadedTotal = await reloaded.getByTestId("web-search-panel").count();
    const reloadedNested = await reloadedPanel.getByTestId("web-search-panel").count();
    expect(reloadedTotal).toBe(reloadedNested);
  });

  test("no-Pro deep research fans out without entitlement coercion", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    // Deep Research ON, deliberately NO Pro grant: platform key is enough.
    // Must NOT coerce to single / show an entitlement callout.
    await enableDeepResearch(page);

    const sentModes: unknown[] = [];
    page.on("request", (req) => {
      if (
        req.method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(req.url())
      ) {
        try {
          const body = req.postDataJSON() as { agenticMode?: unknown };
          sentModes.push(body.agenticMode);
        } catch {
          // Non-JSON body — the assertion below will flag it.
        }
      }
    });

    const convId = await sendAndPauseOnPlan(page);
    expect(sentModes).toEqual(["deep_research"]);

    const paused = page.getByTestId("assistant-message").last();
    await paused.getByTestId("tool-approve").click();

    const resumed = page.getByTestId("assistant-message").last();
    const panel = resumed.getByTestId("subagent-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    // Real deep-research fan-out (workers + synthesis), not coerced primary-only
    // "Agent activity".
    await expect(panel.getByTestId("subagent-row")).toHaveCount(3, {
      timeout: 15_000,
    });
    await expect(panel).toContainText("Worker 1");
    await expect(panel).toContainText("Worker 2");
    await expect(panel).toContainText("Synthesis");
    await expect(panel).not.toContainText("Agent activity");
    await expect(resumed.getByTestId("agentic-coercion-callout")).toHaveCount(0);

    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect(resumed.getByTestId("assistant-answer")).toContainText(
      "Synthesis of 2 findings",
    );
    await expect(resumed.getByTestId("assistant-empty-fallback")).toHaveCount(0);
    expect(sentModes).toEqual(["deep_research", "deep_research"]);

    // Reload parity: fan-out panel + answer survive a cold render.
    await page.reload();
    await waitForBootstrap(page);
    const row = page.locator(`[data-conversation-id="${convId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.getByTestId("sidebar-conversation-link").click();

    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("subagent-panel")).toBeVisible({
      timeout: 15_000,
    });
    await expect(reloaded.getByTestId("subagent-row")).toHaveCount(3);
    await expect(reloaded.getByTestId("assistant-answer")).toContainText(
      "Synthesis of 2 findings",
    );
    await expect(reloaded.getByTestId("agentic-coercion-callout")).toHaveCount(0);
    await expect(reloaded.getByTestId("assistant-empty-fallback")).toHaveCount(0);
  });

  // TOOL_GREEDY drives several tool rounds then a compelled final answer (no
  // synthesis skipped). The BE may inject a fallback string on empty synthesis;
  // either way the bubble must show a non-empty assistant-answer, never the
  // empty-fallback note.
  test("greedy tool loop settles with a written answer, not the empty fallback", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("TOOL_GREEDY: keep calling tools");

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
      timeout: 30_000,
    });
    await expect(assistant.getByTestId("assistant-answer")).toBeVisible({
      timeout: 15_000,
    });
    await expect(assistant.getByTestId("assistant-empty-fallback")).toHaveCount(0);

    await page.reload();
    await waitForBootstrap(page);
    const row = page.locator(`[data-conversation-id="${convId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.getByTestId("sidebar-conversation-link").click();

    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("assistant-answer")).toBeVisible({
      timeout: 15_000,
    });
    await expect(reloaded.getByTestId("assistant-empty-fallback")).toHaveCount(0);
  });

  // The subagent panel is a disclosure: its body (worker findings, etc.) folds
  // behind `subagent-panel-trigger` while the header/title row stays put.
  // Uses a real deep-research fan-out (platform key; no Pro) — cheapest turn
  // that renders the panel with nested worker content.
  test("agent activity panel folds and unfolds its nested content", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    await sendAndPauseOnPlan(page);
    const paused = page.getByTestId("assistant-message").last();
    await paused.getByTestId("tool-approve").click();

    const resumed = page.getByTestId("assistant-message").last();
    const panel = resumed.getByTestId("subagent-panel");
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // Worker intermediate findings live in the panel body this disclosure guards.
    const nested = panel.getByText("Worker 1 finding").first();
    const trigger = panel.getByTestId("subagent-panel-trigger");
    const header = panel.getByText("Deep research");

    // (1) Default-open: trigger + header + nested content all visible.
    await expect(trigger).toBeVisible();
    await expect(header).toBeVisible();
    await expect(nested).toBeVisible({ timeout: 15_000 });

    // (2) Click to fold → the nested content collapses (kept mounted, hidden),
    // but the header row survives so the card is still re-openable.
    await trigger.click();
    await expect(nested).toBeHidden();
    await expect(header).toBeVisible();

    // (3) Click again to unfold → the nested content returns.
    await trigger.click();
    await expect(nested).toBeVisible();
    await expect(header).toBeVisible();
  });
});
