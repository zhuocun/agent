// Agentic mode (Deep Research) — FE↔BE e2e against the fake provider.
//
// The BE runs with AGENTIC_ENABLED + AGENTIC_PLAN_APPROVAL + BILLING_BACKEND=fake
// (see shared-config.ts), so:
//   - bootstrap advertises `agenticEnabled: true` → the Deep Research toggle
//     renders in the model-mode picker
//   - `deep_research` is Pro/BYOK-gated server-side (a non-entitled caller is
//     coerced down to `single`), so each fan-out test first grants Pro over
//     HTTP via the fake billing webhook
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

import { expect, test, type Page } from "@playwright/test";

import { BE_URL, modelModeTrigger, waitForBootstrap } from "./helpers";

// Grant the CURRENT browser session an active Pro entitlement through the fake
// billing backend, entirely over HTTP (mirrors api/tests/test_billing.py):
//   1. promote the anonymous session to a registered user (checkout requires
//      a registered caller)
//   2. start a fake checkout — the fake backend returns a redirect URL of the
//      shape `/settings?billing=fake-pro_subscription&user=<uuid>`, which is
//      the only place the test can learn its own user id
//   3. post an unsigned `customer.subscription.created` webhook for that user
//      (the fake backend skips Stripe signature verification)
// `page.request` shares the browser context's cookie jar, so the BE-origin
// `sid` cookie minted at bootstrap rides along on every call.
async function grantPro(page: Page): Promise<void> {
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  const upgrade = await page.request.post(`${BE_URL}/api/auth/upgrade`, {
    data: {
      email: `agentic-${unique}@example.com`,
      password: "agentic-e2e-password",
    },
  });
  expect(upgrade.ok()).toBe(true);

  const checkout = await page.request.post(`${BE_URL}/api/billing/checkout`, {
    data: { kind: "pro_subscription" },
  });
  expect(checkout.ok()).toBe(true);
  const { url } = (await checkout.json()) as { url: string };
  const userId = new URL(url, BE_URL).searchParams.get("user");
  expect(userId).toBeTruthy();

  const webhook = await page.request.post(`${BE_URL}/api/billing/webhook`, {
    data: {
      id: `evt_agentic_${unique}`,
      type: "customer.subscription.created",
      created: Math.floor(Date.now() / 1000),
      data: {
        object: {
          id: `sub_agentic_${unique}`,
          customer: `cus_agentic_${unique}`,
          status: "active",
          current_period_end:
            Math.floor(Date.now() / 1000) + 30 * 24 * 60 * 60,
          metadata: { user_id: userId },
        },
      },
    },
  });
  expect(webhook.ok()).toBe(true);
  const webhookBody = (await webhook.json()) as { processed?: boolean };
  expect(webhookBody.processed).toBe(true);
}

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

// Drive a Pro session to the plan-approval pause. Returns the conversation id
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
    await grantPro(page);
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

    // The aggregator's synthesized answer renders as the bubble's main answer
    // (the deterministic fake-worker findings, merged in plan order).
    await expect(resumed).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    const answer = resumed.getByTestId("assistant-answer");
    await expect(answer).toContainText("Synthesis of 2 findings");
    await expect(answer).toContainText("alpha topic");
    await expect(answer).toContainText("beta topic");

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
  });

  test("deny the plan: no fan-out, a labeled declined synthesis streams", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await grantPro(page);
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
    // Only the synthesis row — no workers ran.
    const panel = resumed.getByTestId("subagent-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("subagent-row")).toHaveCount(1);
    await expect(panel).toContainText("Synthesis");

    // The resume reused the user turn (continue-style invariant).
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);
  });
});
