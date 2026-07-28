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

import { expect, test, type Locator, type Page } from "./coverage-fixture";

import {
  BE_URL,
  modelModeTrigger,
  reloadIntoConversation,
  snapshotAgenticTurn,
  waitForBootstrap,
  type AgenticTurnSnapshot,
} from "./helpers";

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
async function sendAndPauseOnPlan(
  page: Page,
  prompt = "DEEP_RESEARCH: alpha topic | beta topic",
): Promise<string> {
  let capturedConvId: string | null = null;
  page.on("request", (req) => {
    const m = req
      .url()
      .match(/\/api\/conversations\/([0-9a-fA-F-]{36})\/messages/);
    if (m && !capturedConvId) capturedConvId = m[1]!;
  });

  const composer = page.getByTestId("composer-textarea");
  await composer.fill(prompt);
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
  for (const subQuestion of prompt
    .replace(/^DEEP_RESEARCH:\s*/, "")
    .split("|")
    .map((part) => part.trim())) {
    await expect(planDetail).toContainText(subQuestion);
  }
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
    // the empty-fallback note, and every contract surface must come back
    // identical (the shared parity snapshot, not just "something rendered").
    const live = await snapshotAgenticTurn(resumed);
    await reloadIntoConversation(page, convId);

    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("assistant-answer")).toContainText(
      "Synthesis of 2 findings",
    );
    await expect(reloaded.getByTestId("assistant-empty-fallback")).toHaveCount(0);
    expect(await snapshotAgenticTurn(reloaded)).toEqual(live);
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
    const live = await snapshotAgenticTurn(resumed);
    await reloadIntoConversation(page, convId);

    const reloaded = page.getByTestId("assistant-message").last();
    const reloadedPanel = reloaded.getByTestId("subagent-panel");
    await expect(reloadedPanel.getByTestId("web-search-panel").first()).toBeVisible({
      timeout: 15_000,
    });
    const reloadedTotal = await reloaded.getByTestId("web-search-panel").count();
    const reloadedNested = await reloadedPanel.getByTestId("web-search-panel").count();
    expect(reloadedTotal).toBe(reloadedNested);
    expect(await snapshotAgenticTurn(reloaded)).toEqual(live);
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
    const live = await snapshotAgenticTurn(resumed);
    await reloadIntoConversation(page, convId);

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
    expect(await snapshotAgenticTurn(reloaded)).toEqual(live);
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

    const live = await snapshotAgenticTurn(assistant);
    await reloadIntoConversation(page, convId);

    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("assistant-answer")).toBeVisible({
      timeout: 15_000,
    });
    await expect(reloaded.getByTestId("assistant-empty-fallback")).toHaveCount(0);
    expect(await snapshotAgenticTurn(reloaded)).toEqual(live);
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

    // Outer-panel body content this disclosure guards: settled worker *rows*
    // (headers stay visible; per-row finding text collapses behind its own
    // chevron and is the wrong target for the outer fold).
    const nested = panel.getByTestId("subagent-row").first();
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

  // The headline reload-parity case: one grounded multi-worker turn snapshotted
  // through every contract surface at once (meter + honesty attributes, partial
  // chip, per-row label/role/outcome tuples, resolved citation ids, answer) and
  // compared against the same turn re-derived from persisted parts. The existing
  // reload blocks assert PRESENCE; this asserts EQUIVALENCE, which is where the
  // live and reload paths actually drifted.
  test("agentic turn renders equivalently after reload", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);
    await enableWebSearch(page);

    // The `[1]` in the second sub-question rides into that worker's answer text,
    // so the aggregator's synthesis carries a remapped citation marker and the
    // snapshot's citation-id surface is non-empty.
    const convId = await sendAndPauseOnPlan(
      page,
      "DEEP_RESEARCH: alpha topic | beta [1] topic",
    );
    await page.getByTestId("assistant-message").last().getByTestId("tool-approve").click();

    const resumed = page.getByTestId("assistant-message").last();
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 30_000,
    });
    await expect(resumed.getByTestId("subagent-row")).toHaveCount(3, {
      timeout: 15_000,
    });

    const live = await snapshotAgenticTurn(resumed);
    // Guard the snapshot itself: an all-empty snapshot would compare equal on
    // both sides and prove nothing.
    expect(live.meter).not.toBeNull();
    expect(live.meter?.confidence).toBe("exact");
    expect(live.meter?.phase).toBe("final");
    expect(live.rows.map((r) => r.role)).toEqual([
      "Worker",
      "Worker",
      "Aggregator",
    ]);
    expect(live.rows.every((r) => r.outcome === "succeeded")).toBe(true);
    expect(live.citationIds.length).toBeGreaterThan(0);
    expect(live.answer).toContain("Synthesis of 2 findings");
    expect(live.partialChip).toBeNull();

    await reloadIntoConversation(page, convId);
    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("subagent-panel")).toBeVisible({
      timeout: 15_000,
    });
    expect(await snapshotAgenticTurn(reloaded)).toEqual(live);
  });

  // FE contract role list (docs/plans/02-agent-architecture.md): `verifier` is a
  // first-class role, but the e2e backend never runs the judge (it is off by
  // default per spec open question 1 and enabling it in the shared BE env would
  // change every spec's cost and timing), so the cased label shipped unasserted
  // and degraded to the raw wire string. Inject the role the backend persists
  // (api/tests/test_agentic_safety.py pins that the wire/persist shape is
  // exactly this) into an otherwise-real transcript and assert what renders.
  test("verifier row renders a cased role label", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    const convId = await sendAndPauseOnPlan(page);
    await page.getByTestId("assistant-message").last().getByTestId("tool-approve").click();
    const resumed = page.getByTestId("assistant-message").last();
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 30_000,
    });

    await page.route(`**/api/conversations/${convId}`, async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const response = await route.fetch();
      const body = (await response.json()) as {
        messages: Array<{ parts: Array<Record<string, unknown>> }>;
      };
      const last = body.messages[body.messages.length - 1]!;
      last.parts.push(
        {
          type: "subagent",
          subagentId: "verifier",
          label: "Verification",
          role: "verifier",
          outcome: "succeeded",
        },
        { type: "text", text: "Verdict: pass.", subagentId: "verifier" },
      );
      await route.fulfill({ response, json: body });
    });

    await reloadIntoConversation(page, convId);
    const verifierRow = page
      .getByTestId("assistant-message")
      .last()
      .locator('[data-subagent-id="verifier"]');
    await expect(verifierRow).toBeVisible({ timeout: 15_000 });
    await expect(verifierRow.getByTestId("subagent-role-badge")).toHaveText(
      "Verifier",
    );
    // The screen-reader label reads the cased role too, not "Verification,
    // verifier — toggle details".
    await expect(
      verifierRow.getByRole("button", {
        name: "Verification, Verifier — toggle details",
      }),
    ).toBeVisible();
  });

  // FE-3: a reloaded paused run must not upgrade a reconstructed number to a
  // receipt. The plan card directly above the meter still says "(estimate)", so
  // an `exact` / `final` meter contradicts the same card in the same bubble.
  test("paused run keeps its estimate label after reload", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    const convId = await sendAndPauseOnPlan(page);
    const paused = page.getByTestId("assistant-message").last();
    const liveMeter = paused.getByTestId("run-cost-meter");
    await expect(liveMeter).toBeVisible();
    await expect(liveMeter).toHaveAttribute("data-confidence", "estimate");
    await expect(liveMeter).toHaveAttribute("data-phase", "plan");

    await reloadIntoConversation(page, convId);
    const reloaded = page.getByTestId("assistant-message").last();
    const meter = reloaded.getByTestId("run-cost-meter");
    await expect(meter).toBeVisible({ timeout: 15_000 });
    // The honesty labels survive the cold render: `Est.` prefix, the estimate /
    // plan data attributes, the cap, and the "estimated" aria clause. (The
    // reconstructed SUBTOTAL still differs from the live estimate until the
    // backend persists the plan-phase receipt — the other half of this fix.)
    await expect(meter).toHaveAttribute("data-confidence", "estimate");
    await expect(meter).toHaveAttribute("data-phase", "plan");
    await expect(meter).toContainText("Est. ");
    await expect(meter).toContainText("/ $1.00");
    expect(await meter.getAttribute("aria-label")).toContain("estimated");
    // ...and it no longer contradicts the plan card in the same bubble.
    await expect(reloaded.getByTestId("plan-approval-cost")).toContainText(
      "(estimate)",
    );
  });

  // FE-4, live half, on the path the audit measured: Stop during fan-out.
  // `orchestrator.py` `aclose`s the generator, so a cancelled worker's
  // `SubagentDone(stopped)` can never be yielded and the FE really does hold
  // `running` rows at terminal. The committed layout drops `status`, so every
  // cut-off row used to settle on the `succeeded` default and show a GREEN
  // CHECK for work that never finished.
  //
  // Reload parity is asserted in the pause case below instead: a stop after
  // plan approval never persists the fan-out at all — the row stays
  // `awaiting_approval` carrying only the planner — so there is no reloaded
  // worker row to compare against here.
  test("a worker cut off by Stop renders a non-success icon live", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);
    // Web search widens the per-worker window well past the bare fake
    // provider's ~100ms fan-out, so the Stop lands mid-flight rather than
    // racing the workers to completion.
    await enableWebSearch(page);

    // A stop is a race against the fan-out by nature, so retry the whole
    // produce-then-stop on a fresh chat until one lands mid-flight — the same
    // recovery shape streaming.spec.ts uses for its stop test. A fan-out that
    // finishes first simply recycles instead of failing the assertion.
    // `stopped` is the attempt that caught a worker in flight; `greenAfterStop`
    // records a turn the BE confirmed as `stopped` whose rows nonetheless all
    // claimed success — the FE-4 defect, which the failure message must
    // distinguish from simply losing the race.
    let stopped: AgenticTurnSnapshot | null = null;
    let greenAfterStop: AgenticTurnSnapshot | null = null;
    for (let attempt = 0; stopped === null && attempt < 6; attempt++) {
      if (attempt > 0) {
        await page.getByRole("button", { name: "New chat" }).first().click();
        await expect(page.getByTestId("user-message-text")).toHaveCount(0);
      }
      await sendAndPauseOnPlan(
        page,
        "DEEP_RESEARCH: alpha topic | beta topic | gamma topic",
      );
      await page
        .getByTestId("assistant-message")
        .last()
        .getByTestId("tool-approve")
        .click();

      const live = page.getByTestId("assistant-message").last();
      try {
        await expect(live.getByTestId("subagent-row").first()).toBeVisible({
          timeout: 10_000,
        });
        // Short timeout: if the fan-out already settled the button is gone and
        // this attempt recycles.
        await page
          .getByRole("button", { name: "Stop generating" })
          .click({ timeout: 5_000 });
        await expect(live).toHaveAttribute("data-status", /stopped|done/, {
          timeout: 20_000,
        });
      } catch {
        continue;
      }
      const snapshot = await snapshotAgenticTurn(live);
      // Only an attempt that actually caught a worker in flight proves the fix;
      // a fan-out that reached `done` on its own has every row legitimately
      // `succeeded` and simply recycles.
      if (snapshot.rows.some((r) => r.outcome === "cancelled")) {
        stopped = snapshot;
      } else if (
        snapshot.rows.length > 0 &&
        (await live.getAttribute("data-status")) === "stopped"
      ) {
        greenAfterStop = snapshot;
      }
    }

    // A green check on every row of a turn the BE marked `stopped` is the FE-4
    // defect itself, not a missed race — say so rather than blaming the timing.
    expect(
      stopped,
      greenAfterStop
        ? `turn stopped but every row still claimed success: ${JSON.stringify(greenAfterStop.rows)}`
        : "no Stop landed mid fan-out in 6 attempts",
    ).not.toBeNull();
    // Every row is accounted for as cut off, and none claims success: a worker
    // that never reported a terminal must not settle on the green check.
    expect(stopped!.rows.map((r) => r.outcome)).toEqual(
      stopped!.rows.map(() => "cancelled"),
    );
    await expect(
      page.getByTestId("assistant-message").last().getByTestId("subagent-outcome-succeeded"),
    ).toHaveCount(0);
  });

  // FE-4, reload half. A mid-fan-out worker HITL pause is the deterministic
  // form of the same "no terminal for an in-flight worker" path — the pause
  // stays non-terminal by design (B15) — and unlike a Stop it DOES persist the
  // fan-out, so live and reloaded rows can be compared tuple for tuple.
  test("a worker left unfinished at a pause renders a non-success icon live and after reload", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    const convId = await sendAndPauseOnPlan(
      page,
      "DEEP_RESEARCH: TOOL_APPROVE alpha topic | beta topic",
    );
    await page.getByTestId("assistant-message").last().getByTestId("tool-approve").click();

    // Worker 1 parks on the calendar approval; worker 2 finishes normally.
    const resumed = page.getByTestId("assistant-message").last();
    await expect(resumed).toHaveAttribute("data-status", "awaiting_approval", {
      timeout: 30_000,
    });
    await expect(resumed.getByTestId("subagent-row")).toHaveCount(2, {
      timeout: 15_000,
    });

    const live = await snapshotAgenticTurn(resumed);
    expect(live.rows).toEqual([
      {
        subagentId: "worker-0",
        label: "Worker 1",
        role: "Worker",
        outcome: "cancelled",
      },
      {
        subagentId: "worker-1",
        label: "Worker 2",
        role: "Worker",
        outcome: "succeeded",
      },
    ]);

    await reloadIntoConversation(page, convId);
    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("subagent-row")).toHaveCount(2, {
      timeout: 15_000,
    });
    expect((await snapshotAgenticTurn(reloaded)).rows).toEqual(live.rows);
  });

  // FE-9 / GAP-5: every non-success outcome must round-trip through the reload
  // path with the right icon, and an outcome the FE does not recognize must
  // degrade to the neutral non-success state instead of being laundered into a
  // green check. `failed` also gets live coverage below via FAIL_WORKER, and
  // `stopped` via the unfinished-pause case above.
  test("non-success worker outcomes render the right icon", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    const convId = await sendAndPauseOnPlan(page);
    await page.getByTestId("assistant-message").last().getByTestId("tool-approve").click();
    await expect(page.getByTestId("assistant-message").last()).toHaveAttribute(
      "data-status",
      "done",
      { timeout: 30_000 },
    );

    // One handler, one mutable pair of outcomes: reload once per case so each
    // value is read back off a real persisted transcript.
    let persistedOutcomes: string[] = [];
    await page.route(`**/api/conversations/${convId}`, async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const response = await route.fetch();
      const body = (await response.json()) as {
        messages: Array<{ parts: Array<Record<string, unknown>> }>;
      };
      const last = body.messages[body.messages.length - 1]!;
      let next = 0;
      for (const part of last.parts) {
        if (
          part.type === "subagent" &&
          part.role === "worker" &&
          next < persistedOutcomes.length
        ) {
          part.outcome = persistedOutcomes[next++];
        }
      }
      await route.fulfill({ response, json: body });
    });

    const cases: Array<[string, string]> = [
      ["failed", "subagent-outcome-failed"],
      ["cancelled", "subagent-outcome-cancelled"],
      ["budget_cancelled", "subagent-outcome-cancelled"],
      ["stopped", "subagent-outcome-cancelled"],
      // Not in the union the FE knows: must NOT become a green check.
      ["a_future_outcome", "subagent-outcome-cancelled"],
    ];
    for (const [outcome, iconTestId] of cases) {
      persistedOutcomes = [outcome, "succeeded"];
      await reloadIntoConversation(page, convId);
      const rows = page.getByTestId("assistant-message").last().getByTestId("subagent-row");
      await expect(rows.first()).toBeVisible({ timeout: 15_000 });
      await expect(
        rows.first().getByTestId(iconTestId),
        `worker outcome ${outcome}`,
      ).toBeVisible();
      await expect(
        rows.first().getByTestId("subagent-outcome-succeeded"),
      ).toHaveCount(0);
    }
  });

  // GAP-7 / FE-1: the citation chain is otherwise covered only on the
  // single-stream path (streaming.spec.ts). Here two workers each retrieve their
  // own sources, the orchestrator remaps their local `[n]` ids into one globally
  // unique catalog, and the aggregator's synthesis cites across workers — so a
  // chip must reveal the source of the worker that actually retrieved it, not a
  // sibling's.
  test("a citation chip in the aggregator answer resolves to the worker that retrieved it", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);
    await enableWebSearch(page);

    const convId = await sendAndPauseOnPlan(
      page,
      "DEEP_RESEARCH: alpha topic | beta [1] topic",
    );
    await page.getByTestId("assistant-message").last().getByTestId("tool-approve").click();
    const resumed = page.getByTestId("assistant-message").last();
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 30_000,
    });

    // Read the retrieving worker's own catalog off the persisted transcript
    // rather than assuming an allocation order: worker 2's `[1]` was remapped to
    // the first id in ITS sources part.
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = (await fetched.json()) as {
      messages: Array<{
        parts: Array<{
          type: string;
          subagentId?: string | null;
          items?: Array<{ id: number; url: string }>;
        }>;
      }>;
    };
    const parts = body.messages[body.messages.length - 1]!.parts;
    const sourcesFor = (subagentId: string) =>
      parts.find((p) => p.type === "sources" && p.subagentId === subagentId)
        ?.items ?? [];
    const worker1Sources = sourcesFor("worker-1");
    const worker0Sources = sourcesFor("worker-0");
    expect(worker1Sources.length).toBeGreaterThan(0);
    expect(worker0Sources.length).toBeGreaterThan(0);
    const citedId = worker1Sources[0]!.id;
    const citedUrl = worker1Sources[0]!.url;
    expect(worker0Sources.map((s) => s.id)).not.toContain(citedId);

    const assertChipResolvesToWorker1 = async (scope: Locator) => {
      const chip = scope.locator(
        `[data-testid="citation-marker"][data-citation-id="${citedId}"]`,
      );
      await expect(chip.first()).toBeVisible({ timeout: 15_000 });
      await chip.first().click();
      const card = scope.locator(`[data-source-id="${citedId}"]`).first();
      await expect(card).toBeVisible();
      expect(await card.getAttribute("href")).toBe(citedUrl);
      // The revealed card picks up the transient highlight ring.
      await expect
        .poll(async () => card.evaluate((el) => getComputedStyle(el).boxShadow))
        .not.toBe("none");
    };

    await assertChipResolvesToWorker1(resumed);

    await reloadIntoConversation(page, convId);
    await assertChipResolvesToWorker1(
      page.getByTestId("assistant-message").last(),
    );
  });

  // GAP-4: the partial-synthesis chip was unasserted in both directions. A
  // FAIL_WORKER sub-question drives the real failed-worker branch live; the
  // budget and generic branches are re-derived from a persisted
  // `agentic_run_summary` so the branch order (budget copy wins only when
  // `budgetHalted` is true) is pinned rather than assumed.
  test("partial-synthesis chip copy matches across reload", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await enableDeepResearch(page);

    const convId = await sendAndPauseOnPlan(
      page,
      "DEEP_RESEARCH: alpha topic | FAIL_WORKER beta topic",
    );
    await page.getByTestId("assistant-message").last().getByTestId("tool-approve").click();

    const resumed = page.getByTestId("assistant-message").last();
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 30_000,
    });
    const live = await snapshotAgenticTurn(resumed);
    expect(live.partialChip).toBe("Partial answer — 1 worker failed.");
    expect(live.rows.map((r) => r.outcome)).toEqual([
      "succeeded",
      "failed",
      "succeeded",
    ]);

    await reloadIntoConversation(page, convId);
    const reloaded = page.getByTestId("assistant-message").last();
    await expect(reloaded.getByTestId("partial-synthesis-warning")).toBeVisible({
      timeout: 15_000,
    });
    expect(await snapshotAgenticTurn(reloaded)).toEqual(live);

    // The other two copy branches, re-derived from the persisted receipt.
    let summaryOverride: Record<string, unknown> = {};
    await page.route(`**/api/conversations/${convId}`, async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const response = await route.fetch();
      const body = (await response.json()) as {
        messages: Array<{ parts: Array<Record<string, unknown>> }>;
      };
      const last = body.messages[body.messages.length - 1]!;
      for (const part of last.parts) {
        if (part.type === "agentic_run_summary") {
          Object.assign(part, summaryOverride);
        }
      }
      await route.fulfill({ response, json: body });
    });

    summaryOverride = { budgetHalted: true, failedWorkers: 2 };
    await reloadIntoConversation(page, convId);
    // Budget copy wins over the failed-worker copy when the run was halted.
    await expect(
      page.getByTestId("assistant-message").last().getByTestId("partial-synthesis-warning"),
    ).toHaveText(
      "Partial answer — stopped early to stay within the run budget.",
      { timeout: 15_000 },
    );

    summaryOverride = { budgetHalted: false, failedWorkers: 0 };
    await reloadIntoConversation(page, convId);
    // Neither flag set but still partial (e.g. a synthesis that degraded): the
    // generic copy, never the budget copy.
    await expect(
      page.getByTestId("assistant-message").last().getByTestId("partial-synthesis-warning"),
    ).toHaveText("Partial answer — some research steps did not finish.", {
      timeout: 15_000,
    });
  });
});
