import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { getUsagePresentation } from "../src/components/chat/usage-presentation";
import type { UsageBudget } from "../src/lib/types";

function budget(overrides: Partial<UsageBudget>): UsageBudget {
  return {
    used: 0,
    limit: 1000,
    periodLabel: "this month",
    isByok: false,
    monthlySpendUsd: 0,
    effectiveQuotaUsd: 1,
    ...overrides,
  };
}

describe("getUsagePresentation platform allowance", () => {
  it("uses platformRemainingUsd 2.25 instead of quota minus spend", () => {
    const presentation = getUsagePresentation(
      budget({ monthlySpendUsd: 0.25, platformRemainingUsd: 2.25 }),
    );
    // Settings shows "Usage limit reached" only when tone is exhausted.
    assert.equal(presentation.remainingText, "$2.25 left");
    assert.equal(presentation.spendRemainingUsd, 2.25);
    assert.notEqual(presentation.tone, "exhausted");
    assert.equal(presentation.remainingText.includes("Budget reached"), false);
    assert.equal(presentation.spendPct, 10);
    assert.ok(presentation.spendPct >= 0 && presentation.spendPct <= 100);
  });

  it("keeps spent credits in the bar after spend passes the quota", () => {
    const presentation = getUsagePresentation(
      budget({
        monthlySpendUsd: 1.5,
        platformRemainingUsd: 1,
        creditBalanceUsd: 1,
      }),
    );
    assert.equal(presentation.spendPct, 60);
    assert.equal(presentation.tone, "critical");
    assert.equal(presentation.remainingText, "$1.00 left");
  });

  it("stays critical when spend has hit the quota but allowance remains", () => {
    const presentation = getUsagePresentation(
      budget({ monthlySpendUsd: 1, platformRemainingUsd: 1.5 }),
    );
    assert.equal(presentation.tone, "critical");
    assert.notEqual(presentation.tone, "exhausted");
    assert.equal(presentation.remainingText, "$1.50 left");
    assert.equal(presentation.spendPct, 40);
    assert.ok(presentation.spendPct >= 0 && presentation.spendPct <= 100);
  });

  it("falls back to quota minus spend when the server field is absent", () => {
    const missing = getUsagePresentation(budget({ monthlySpendUsd: 1 }));
    const nulled = getUsagePresentation(
      budget({ monthlySpendUsd: 1, platformRemainingUsd: null }),
    );
    for (const presentation of [missing, nulled]) {
      assert.equal(presentation.tone, "exhausted");
      assert.equal(presentation.remainingText, "Budget reached");
      assert.equal(presentation.spendRemainingUsd, 0);
      assert.equal(presentation.spendPct, 100);
    }

    const partial = getUsagePresentation(budget({ monthlySpendUsd: 0.25 }));
    assert.equal(partial.remainingText, "$0.7500 left");
    assert.equal(partial.tone, "normal");
    assert.equal(partial.spendPct, 25);
  });
});
