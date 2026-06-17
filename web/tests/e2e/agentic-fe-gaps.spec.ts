// Share-view agentic rendering (PRD 01 "Remaining gaps"): the public-by-link
// snapshot must replay the same subagent panel / grouped worker content /
// aggregator answer as the private thread, including the per-subagent
// served-model / substitution callout (FR-26e) and the PRD 08 partial-synthesis
// warning chip (FR-26g) — all COST-STRIPPED (PRD 07 §6.4).
//
// The cost hint (FR-26f) and the private-thread partial chip are covered by the
// real-backend flows in `agentic.spec.ts`. This spec targets the share surface,
// which the BE does not yet populate with per-subagent attribution (a noted
// backend gap), so a wire-shaped fixture is the only way to exercise the
// substitution callout's render path end-to-end. Everything asserted is pure FE
// rendering of a mocked public-share payload (no BE required for this route).

import { expect, test } from "@playwright/test";

const ARTIFACTS = "/opt/cursor/artifacts";

test("share view replays subagents, the substitution callout, and the partial chip", async ({
  page,
}) => {
  const now = new Date().toISOString();
  const snapshot = {
    id: "conv-share-demo",
    title: "Deep research — shared",
    messages: [
      {
        id: "u1",
        role: "user",
        createdAt: now,
        parts: [{ type: "text", text: "DEEP_RESEARCH: alpha topic | beta topic" }],
      },
      {
        id: "a1",
        role: "assistant",
        createdAt: now,
        attribution: {
          requestedTierId: "pro",
          servedTierId: "pro",
          servedModelLabel: "DeepSeek Reasoner",
          isByok: false,
        },
        parts: [
          {
            type: "subagent",
            subagentId: "w1",
            label: "Worker 1",
            role: "worker",
            // Per-subagent reroute (FR-26e): served Fast instead of the
            // requested Pro tier. The public surface keeps model identity +
            // substitution, never cost.
            attribution: {
              requestedTierId: "pro",
              servedTierId: "fast",
              servedModelLabel: "DeepSeek Chat",
              isByok: false,
              substitution: {
                reasonCode: "rate_limited",
                reasonText: "answered by Fast because Pro was rate-limited",
              },
            },
          },
          { type: "reasoning", text: "Investigating alpha topic.", subagentId: "w1" },
          {
            type: "text",
            text: "Worker 1 finding on alpha topic: result ready.",
            subagentId: "w1",
          },
          { type: "subagent", subagentId: "w2", label: "Worker 2", role: "worker" },
          {
            type: "text",
            text: "Worker 2 finding on beta topic: result ready.",
            subagentId: "w2",
          },
          {
            type: "subagent",
            subagentId: "agg",
            label: "Synthesis",
            role: "aggregator",
          },
          {
            type: "text",
            subagentId: "agg",
            text:
              "Synthesis of 2 findings on alpha topic and beta topic.\n\n" +
              "[Partial answer: stopped early to stay within the run budget; " +
              "answered 1 of 2 planned steps.]",
          },
        ],
      },
    ],
  };

  await page.route("**/api/share/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot),
    });
  });

  await page.goto("/share/demo-token");

  const assistant = page.getByTestId("public-assistant-message");
  await expect(assistant).toBeVisible({ timeout: 10_000 });

  // The subagent panel replays one row per subagent (2 workers + synthesis).
  const panel = assistant.getByTestId("subagent-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("subagent-row")).toHaveCount(3);
  await expect(panel).toContainText("Worker 1");
  await expect(panel).toContainText("Worker 2");
  await expect(panel).toContainText("Synthesis");

  // Per-subagent substitution callout (FR-26e).
  await expect(panel.getByTestId("subagent-substitution")).toBeVisible();
  await expect(panel.getByTestId("subagent-attribution")).toContainText(
    "Rerouted from Pro tier",
  );

  // No per-subagent cost leaks on the public surface (PRD 07 §6.4): the run-cost
  // meter never renders (no cost was passed into the derived sections).
  await expect(panel.getByTestId("run-cost-meter")).toHaveCount(0);

  // The aggregator's synthesis is the main answer; worker findings stay
  // panel-only and never become sibling markdown blocks.
  const answer = assistant.getByTestId("public-assistant-answer");
  await expect(answer).toContainText("Synthesis of 2 findings");

  // Partial-synthesis chip is lifted out; the raw bracket is stripped from the
  // rendered main answer.
  await expect(assistant.getByTestId("partial-synthesis-warning")).toBeVisible();
  await expect(answer).not.toContainText("[Partial answer:");

  await page.screenshot({
    path: `${ARTIFACTS}/share_view_subagents.png`,
    fullPage: true,
  });
});
