// Composer surfaces that the baseline suite under-exercised (ST-3):
//   - slash-command popover: open / filter (match + no-match) / keyboard nav /
//     pick (composer.tsx onKeyDown slash layer + pickCommand) / Escape dismiss
//   - offline draft persistence across a full reload (offline-store.ts
//     saveDraft + loadDraft, driven through the composer's persistence effects)
//   - attachment add / size formatting / remove, and the user-message
//     attachment preview after send (composer.tsx onPickFiles/removeAttachment,
//     user-message.tsx attachment branch, format-attachment-size MB branch)
//
// Runs against the REAL integrated BE + FakeProvider, like the sibling specs.

import { expect, test, type Page } from "./coverage-fixture";

import { modelModeTrigger, waitForBootstrap } from "./helpers";

// Pick a tier from the model-mode dropdown by its visible label (mirrors
// vision.spec.ts). Smart is attachment- AND vision-capable in the fake registry.
async function selectTier(page: Page, label: string): Promise<void> {
  await modelModeTrigger(page).click();
  await page
    .locator('[data-slot="dropdown-menu-item"]:visible', { hasText: label })
    .first()
    .click();
  await expect(
    page.locator('[data-slot="dropdown-menu-item"]:visible'),
  ).toHaveCount(0);
}

test.describe("composer slash commands", () => {
  test("open, filter, keyboard-navigate, pick, and Escape-dismiss", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const composer = page.getByTestId("composer-textarea");
    const options = page.getByRole("option");

    // A lone "/" opens the popover with the full command list.
    await composer.fill("/");
    await expect(options.first()).toBeVisible();
    expect(await options.count()).toBeGreaterThanOrEqual(2);

    // ArrowDown moves the highlight to the second row (aria-selected tracks it).
    await composer.press("ArrowDown");
    await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");

    // Enter picks the highlighted command and prefills the composer with its
    // full prompt — the "/" token is replaced, so the popover closes.
    await composer.press("Enter");
    await expect(options).toHaveCount(0);
    const picked = await composer.inputValue();
    expect(picked).not.toBe("/");
    expect(picked.length).toBeGreaterThan(2);
    expect(picked.startsWith("/")).toBe(false);

    // A "/" token that matches nothing shows the no-match hint (empty listbox).
    await composer.fill("");
    await composer.fill("/zzzzz");
    await expect(
      page.getByText("No commands match — keep typing for a regular message."),
    ).toBeVisible();
    await expect(options).toHaveCount(0);

    // A partial token filters to the matching command(s).
    await composer.fill("/sum");
    await expect(options).toHaveCount(1);
    await expect(options.first()).toContainText("/summarize");

    // Escape dismisses the popover but leaves the typed token in place.
    await composer.press("Escape");
    await expect(options).toHaveCount(0);
    await expect(composer).toHaveValue("/sum");
  });
});

test.describe("composer draft persistence", () => {
  test("an unsent draft survives a full page reload", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    const draft = "An in-progress message I have not sent yet";
    await page.getByTestId("composer-textarea").fill(draft);

    // The composer debounces the IndexedDB write (~500ms). Poll the store
    // directly so we reload only AFTER the draft is durably persisted, keeping
    // the test free of a fixed waitForTimeout race.
    await expect
      .poll(
        () =>
          page.evaluate(
            () =>
              new Promise<string | null>((resolve) => {
                const req = indexedDB.open("olune-offline", 1);
                req.onsuccess = () => {
                  const db = req.result;
                  try {
                    const tx = db.transaction("drafts", "readonly");
                    const get = tx.objectStore("drafts").get("__new_chat__");
                    get.onsuccess = () =>
                      resolve(
                        typeof get.result === "string" ? get.result : null,
                      );
                    get.onerror = () => resolve(null);
                  } catch {
                    resolve(null);
                  }
                };
                req.onerror = () => resolve(null);
              }),
          ),
        { timeout: 10_000 },
      )
      .toBe(draft);

    // Full reload: the composer's restore effect reads the draft back.
    await page.reload();
    await waitForBootstrap(page);
    await expect(page.getByTestId("composer-textarea")).toHaveValue(draft);
  });
});

test.describe("composer attachments", () => {
  // A >1MB text file so the size renders via the MB branch of
  // formatAttachmentSize (the byte/KB branch is already exercised elsewhere).
  const BIG_TEXT = Buffer.alloc(Math.round(1.5 * 1024 * 1024), 0x61);

  test("attach a file, see its preview + size, remove it, then send and see the user-bubble preview", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Smart accepts files (and images); the file input mounts only when the
    // tier supports attachments.
    await selectTier(page, "Smart");

    await page.getByTestId("composer-file-input").setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: BIG_TEXT,
    });

    // The composer shows the attachment chip with its name and MB-formatted size.
    await expect(page.getByText("notes.txt")).toBeVisible();
    await expect(page.getByText("1.5 MB").first()).toBeVisible();

    // Remove it — the chip disappears.
    await page.getByRole("button", { name: "Remove notes.txt" }).click();
    await expect(page.getByText("notes.txt")).toHaveCount(0);

    // Re-attach and send with text; the fake provider echoes the attachment.
    await page.getByTestId("composer-file-input").setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: BIG_TEXT,
    });
    await expect(page.getByText("notes.txt")).toBeVisible();
    await page.getByTestId("composer-textarea").fill("Summarize my notes");
    await page.getByTestId("composer-send").click();

    // The user bubble renders the attachment preview (name, size, "Request
    // only" transience marker) — the user-message attachment branch.
    const userMsg = page.getByRole("article", { name: "You" }).first();
    await expect(userMsg.getByText("notes.txt")).toBeVisible({ timeout: 15_000 });
    await expect(userMsg.getByText("1.5 MB")).toBeVisible();
    await expect(userMsg.getByText("Request only")).toBeVisible();

    // The turn streams to terminal.
    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });
  });
});
