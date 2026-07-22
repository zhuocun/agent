// Leaked tool-call markup — FE render-time scrub regression.
//
// A stubborn real provider can dump raw tool-call special tokens (the captured
// prod leak `<｜｜DSML｜｜tool_calls>…`) straight into answer content. The BE
// stream sanitizer scrubs the real-provider path, but the final safety net is
// the FE render-time scrub (`stripToolMarkup` in markdown-renderer.tsx), which
// also protects already-persisted transcripts.
//
// The fake provider bypasses the BE sanitizer, so a `LEAK_MARKUP:` prompt (see
// api/app/providers/fake.py) streams clean prose FOLLOWED by a raw DSML block as
// answer content — reaching the FE intact. This asserts the rendered answer keeps
// the prose and shows NONE of the markup, both live and after a reload (the
// persisted-transcript path).

import { expect, test } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

// Substrings that must NEVER appear in the rendered answer. `｜` is U+FF5C.
const FORBIDDEN = ["DSML", "tool_calls", 'invoke name=', "web_search", "<\uFF5C"];

test.describe("leaked tool-call markup", () => {
  test("answer UI scrubs leaked DSML markup, live and after reload", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    let convId = "";
    page.on("response", async (response) => {
      const url = response.url();
      if (
        response.request().method() === "POST" &&
        url === `${BE_URL}/api/conversations`
      ) {
        try {
          const json = (await response.json()) as { id?: unknown };
          if (typeof json.id === "string") convId = json.id;
        } catch {
          // Body may already be consumed by the FE — the SSE URL below recovers it.
        }
      }
    });

    const composer = page.getByTestId("composer-textarea");
    await composer.fill("LEAK_MARKUP: please leak tool markup");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toBeVisible();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // The clean lead-in prose survives; none of the raw markup renders.
    const answer = assistant.getByTestId("assistant-answer");
    await expect(answer).toContainText("Sure, here is the answer you asked for.");
    for (const forbidden of FORBIDDEN) {
      await expect(answer).not.toContainText(forbidden);
    }

    // Sanity: the BE actually persisted the raw leak (the FE scrub is what hides
    // it), so this is a genuine render-time regression guard, not a no-op.
    await expect.poll(() => convId, { timeout: 15_000 }).toBeTruthy();
    const fetched = await page.request.get(
      `${BE_URL}/api/conversations/${convId}`,
    );
    expect(fetched.status()).toBe(200);
    const body = (await fetched.json()) as {
      messages: Array<{ role: string; parts: Array<{ type: string; text?: string }> }>;
    };
    const assistantMsg = body.messages.find((m) => m.role === "assistant");
    const persistedText = (assistantMsg?.parts ?? [])
      .filter((p) => p.type === "text")
      .map((p) => p.text ?? "")
      .join("");
    expect(persistedText).toContain("DSML");

    // Reload → the persisted (still-raw) transcript re-renders through the same
    // scrub, so the markup stays hidden on the cold path too.
    await page.reload();
    await waitForBootstrap(page);
    const row = page.locator(`[data-conversation-id="${convId}"]`);
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.getByTestId("sidebar-conversation-link").click();

    const reloaded = page.getByTestId("assistant-message").last();
    const reloadedAnswer = reloaded.getByTestId("assistant-answer");
    await expect(reloadedAnswer).toContainText(
      "Sure, here is the answer you asked for.",
    );
    for (const forbidden of FORBIDDEN) {
      await expect(reloadedAnswer).not.toContainText(forbidden);
    }
  });
});
