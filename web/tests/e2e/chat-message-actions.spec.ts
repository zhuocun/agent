// Per-message actions — the user/assistant message toolbars end-to-end (ST-3).
//
// Closes the big coverage gaps on the message-action surfaces that the existing
// suite barely touched:
//   - user-message.tsx (edit-in-place / cancel, copy, branch button, attachment
//     preview is covered in composer-extras.spec.ts)
//   - message-actions.tsx (copy, plain Regenerate, thumbs up/down feedback)
//   - chat-thread.tsx handlers (handleEditUserMessage, handleRegenerate,
//     handleBranchFromMessage, setFeedback) + their toasts
//   - follow-up-chips.tsx (chip click → composer prefill)
//
// Runs against the REAL integrated BE + FakeProvider (PROVIDER_BACKEND=fake),
// mirroring streaming.spec.ts: a send streams a deterministic canned reply and
// both the user + assistant rows reconcile to server uuids at terminal time, so
// the edit/branch/feedback affordances (which skip `local-` ids) light up.

import { expect, test, type Page } from "./coverage-fixture";

import { waitForBootstrap } from "./helpers";

// Send one turn through the composer and wait for the assistant turn to settle.
// After terminal the user + assistant ids are server uuids, so canEdit /
// canBranch / canRegenerate are all true on the live thread (no reload needed).
async function sendAndSettle(page: Page, text: string): Promise<void> {
  await page.getByTestId("composer-textarea").fill(text);
  await page.getByTestId("composer-send").click();
  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toHaveAttribute("data-status", "done", {
    timeout: 15_000,
  });
}

test.describe("user message actions", () => {
  test("edit-in-place: cancel restores the original, save resubmits and updates the bubble", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await sendAndSettle(page, "First question");

    const userMsg = page.getByRole("article", { name: "You" }).first();
    await expect(userMsg.getByTestId("user-message-text")).toHaveText(
      "First question",
    );

    // --- Cancel path (Escape) ------------------------------------------------
    await userMsg.getByRole("button", { name: "Edit" }).click();
    const editBox = page.getByRole("textbox", { name: "Edit message" });
    await expect(editBox).toBeVisible();
    await expect(editBox).toBeFocused();
    // Draft seeds from the current text; Save is disabled until it changes.
    await expect(editBox).toHaveValue("First question");
    await expect(
      page.getByRole("button", { name: "Save and resubmit" }),
    ).toBeDisabled();
    await editBox.fill("Throwaway edit");
    await editBox.press("Escape");
    // Back to display mode with the ORIGINAL text — the edit was discarded.
    await expect(page.getByRole("textbox", { name: "Edit message" })).toHaveCount(
      0,
    );
    await expect(userMsg.getByTestId("user-message-text")).toHaveText(
      "First question",
    );

    // --- Save path (Enter resubmits) -----------------------------------------
    // Capture the edit POST so we confirm it rode the wire with editMessageId.
    let sentEditId: unknown;
    page.on("request", (request) => {
      const url = request.url();
      if (
        request.method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(url)
      ) {
        try {
          const body = request.postDataJSON() as { editMessageId?: unknown };
          if (body.editMessageId !== undefined) sentEditId = body.editMessageId;
        } catch {
          /* non-JSON body — assertion below flags it */
        }
      }
    });

    await userMsg.getByRole("button", { name: "Edit" }).click();
    const editBox2 = page.getByRole("textbox", { name: "Edit message" });
    await editBox2.fill("Edited question");
    await expect(
      page.getByRole("button", { name: "Save and resubmit" }),
    ).toBeEnabled();
    await editBox2.press("Enter");

    // The bubble now shows the edited text and a fresh assistant turn streams.
    await expect(
      page.getByRole("article", { name: "You" }).first().getByTestId(
        "user-message-text",
      ),
    ).toHaveText("Edited question", { timeout: 15_000 });
    const regenerated = page.getByTestId("assistant-message").last();
    await expect(regenerated).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    await expect.poll(() => typeof sentEditId).toBe("string");

    // Exactly one user bubble remains (edit replaces, never duplicates).
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);
  });

  test("copy puts the user's text on the clipboard and flips the control to Copied", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/");
    await waitForBootstrap(page);
    await sendAndSettle(page, "Copy me please");

    const userMsg = page.getByRole("article", { name: "You" }).first();
    await userMsg.getByRole("button", { name: "Copy" }).click();

    // The control announces success (icon + aria-label swap to "Copied").
    await expect(userMsg.getByRole("button", { name: "Copied" })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
      "Copy me please",
    );
  });

  test("branch in new chat forks the conversation and toasts", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await sendAndSettle(page, "Branch from here");

    let branchOk = false;
    page.on("response", (response) => {
      if (
        /\/api\/conversations\/[^/]+\/branch$/.test(response.url()) &&
        response.request().method() === "POST"
      ) {
        branchOk = response.ok();
      }
    });

    const userMsg = page.getByRole("article", { name: "You" }).first();
    await userMsg.getByRole("button", { name: "Branch in new chat" }).click();

    // Success surfaces as an info toast, and the branch POST returned 2xx.
    // ("Branched into new chat" also renders in the sr-only live region, so
    // scope to the toast to avoid a strict-mode collision.)
    await expect(
      page.getByLabel("Information").getByText("Branched into new chat"),
    ).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => branchOk).toBe(true);
    // The forked thread keeps the originating user turn.
    await expect(
      page.getByTestId("user-message-text").filter({ hasText: "Branch from here" }),
    ).toHaveCount(1);
  });
});

test.describe("assistant message actions", () => {
  test("copy puts the answer on the clipboard and flips the control to Copied", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/");
    await waitForBootstrap(page);
    await sendAndSettle(page, "Tell me something");

    const assistant = page.getByTestId("assistant-message").last();
    const answerText =
      (await assistant.getByTestId("assistant-answer").textContent()) ?? "";
    expect(answerText.trim().length).toBeGreaterThan(0);

    await assistant.getByTestId("copy").click();
    // The inline copy control swaps its accessible name to "Copied".
    await expect(assistant.getByRole("button", { name: "Copied" })).toBeVisible();
    const clipboard = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboard.trim()).toBe(answerText.trim());
  });

  test("thumbs up then down persists the reaction through the feedback endpoint", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const feedbackBodies: Array<{ feedback?: unknown }> = [];
    page.on("request", (request) => {
      if (
        /\/api\/messages\/[^/]+\/feedback$/.test(request.url()) &&
        request.method() === "POST"
      ) {
        try {
          feedbackBodies.push(request.postDataJSON() as { feedback?: unknown });
        } catch {
          /* ignore non-JSON */
        }
      }
    });

    await sendAndSettle(page, "Rate this answer");

    const assistant = page.getByTestId("assistant-message").last();
    await assistant.getByTestId("message-actions-overflow").click();

    // The overflow portals to body; the ratings are menuitemcheckbox rows that
    // stay open on click (closeOnClick={false}), so we can toggle both here.
    const helpful = page.getByRole("menuitemcheckbox", {
      name: "Helpful",
      exact: true,
    });
    await helpful.click();
    await expect(helpful).toHaveAttribute("aria-checked", "true");
    await expect.poll(() => feedbackBodies.at(-1)?.feedback).toBe("up");

    const notHelpful = page.getByRole("menuitemcheckbox", {
      name: "Not helpful",
      exact: true,
    });
    await notHelpful.click();
    await expect(notHelpful).toHaveAttribute("aria-checked", "true");
    await expect(helpful).toHaveAttribute("aria-checked", "false");
    await expect.poll(() => feedbackBodies.at(-1)?.feedback).toBe("down");
  });

  test("plain Regenerate drops the trailing turn and re-streams a new one", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    let regenerateRequested = false;
    page.on("request", (request) => {
      const url = request.url();
      if (
        request.method() === "POST" &&
        /\/api\/conversations\/[^/]+\/messages$/.test(url)
      ) {
        try {
          const body = request.postDataJSON() as { regenerate?: unknown };
          if (body.regenerate === true) regenerateRequested = true;
        } catch {
          /* ignore */
        }
      }
    });

    await sendAndSettle(page, "Original answer please");
    await expect(page.getByTestId("assistant-message")).toHaveCount(1);

    await page.getByTestId("message-actions-overflow").last().click();
    await page.getByRole("menuitem", { name: "Regenerate", exact: true }).click();

    // A fresh turn streams to terminal and the wire carried regenerate: true.
    await expect.poll(() => regenerateRequested).toBe(true);
    const regenerated = page.getByTestId("assistant-message").last();
    await expect(regenerated).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
    // Still one user turn + one assistant turn (regenerate replaces, not appends).
    await expect(page.getByTestId("user-message-text")).toHaveCount(1);
    await expect(page.getByTestId("assistant-message")).toHaveCount(1);
  });

  test("a follow-up chip prefills the composer (never auto-sends)", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await sendAndSettle(page, "Give me a plain answer");

    const assistant = page.getByTestId("assistant-message").last();
    const chips = assistant.getByTestId("follow-up-chips");
    await expect(chips).toBeVisible({ timeout: 15_000 });

    const firstChip = chips.getByTestId("follow-up-chip").first();
    const chipText = (await firstChip.innerText()).trim();
    expect(chipText.length).toBeGreaterThan(0);
    await firstChip.click();

    // The chip text lands in the composer for review — the turn is NOT sent.
    await expect(page.getByTestId("composer-textarea")).toHaveValue(chipText);
    await expect(page.getByTestId("assistant-message")).toHaveCount(1);
  });
});
