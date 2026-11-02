// Transparent long-term memory (D19) — runtime coverage against the live BE.
//
// Drives the real shell + real bootstrap (no stubbing). Two flows:
//   1. The memory manager CRUD: open Settings → "Memory", toggle the opt-in,
//      add / edit / delete a fact, asserting the ledger updates each step.
//   2. The "Memory used here" indicator: with memory ON and a fact saved, send a
//      real (fake-provider) turn and assert the chip appears on the assistant
//      message and opens the manager on click.

import { expect, test, type Page } from "./coverage-fixture";

import { waitForBootstrap } from "./helpers";

async function openMemory(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByTestId("open-memory-button").click();
  await expect(page.getByTestId("memory-dialog")).toBeVisible();
}

test.describe("transparent long-term memory", () => {
  test("manage facts: opt-in, add, edit, delete", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await openMemory(page);
    const dialog = page.getByTestId("memory-dialog");

    // Opt in.
    await dialog.getByTestId("memory-enabled-switch").click();

    // Add a fact.
    await dialog.getByTestId("memory-add-input").fill("I prefer metric units.");
    await dialog.getByTestId("memory-add-button").click();

    const list = dialog.getByTestId("memory-list");
    await expect(list).toBeVisible();
    await expect(
      list.getByText("I prefer metric units.", { exact: true }),
    ).toBeVisible();

    // Edit it.
    await dialog.getByTestId("memory-edit-button").first().click();
    const editInput = dialog.getByTestId("memory-edit-input");
    await editInput.fill("I prefer imperial units.");
    await dialog.getByTestId("memory-edit-save").click();
    await expect(
      list.getByText("I prefer imperial units.", { exact: true }),
    ).toBeVisible();
    await expect(
      list.getByText("I prefer metric units.", { exact: true }),
    ).toHaveCount(0);

    // Delete it.
    await dialog.getByTestId("memory-delete-button").first().click();
    await expect(dialog.getByTestId("memory-fact")).toHaveCount(0);

    await dialog.screenshot({
      path: "/opt/cursor/artifacts/memory_dialog.png",
    });
  });

  test("locks every fact row while a save is in flight", async ({ page }) => {
    let releasePatch: (() => void) | undefined;
    let patches = 0;
    let markStarted: (() => void) | undefined;
    const patchStarted = new Promise<void>((resolve) => {
      markStarted = resolve;
    });
    await page.route("**/api/account/memory/*", async (route) => {
      if (route.request().method() !== "PATCH") return route.fallback();
      patches += 1;
      if (patches === 1) {
        markStarted?.();
        await new Promise<void>((resolve) => {
          releasePatch = resolve;
        });
      }
      return route.fallback();
    });

    await page.goto("/");
    await waitForBootstrap(page);
    await openMemory(page);
    const dialog = page.getByTestId("memory-dialog");

    await dialog.getByTestId("memory-add-input").fill("Fact A");
    await dialog.getByTestId("memory-add-button").click();
    // Wait on the ledger row. getByText also matches the add field's value, so
    // it can pass before the create response clears that field.
    const facts = dialog.getByTestId("memory-fact");
    await expect(facts.filter({ hasText: "Fact A" })).toBeVisible();
    await dialog.getByTestId("memory-add-input").fill("Fact B");
    await dialog.getByTestId("memory-add-button").click();
    await expect(facts.filter({ hasText: "Fact B" })).toBeVisible();

    const rows = facts;
    await expect(rows).toHaveCount(2);
    // Newest first: row 0 is Fact B, row 1 is Fact A.
    await rows.nth(1).getByTestId("memory-edit-button").click();
    await dialog.getByTestId("memory-edit-input").fill("Fact A revised");
    const save = dialog.getByTestId("memory-edit-save");
    await save.click();
    await patchStarted;

    await expect(save).toBeDisabled();
    await expect(rows.nth(0).getByTestId("memory-edit-button")).toBeDisabled();
    await expect(
      rows.nth(0).getByTestId("memory-delete-button"),
    ).toBeDisabled();

    await save.click({ force: true });
    expect(patches).toBe(1);

    releasePatch?.();
    await expect(dialog.getByTestId("memory-edit-input")).toHaveCount(0);
    await expect(
      dialog.getByText("Fact A revised", { exact: true }),
    ).toBeVisible();
    await expect(dialog.getByText("Fact B", { exact: true })).toBeVisible();
  });

  test("memory used here indicator appears on a turn that used memory", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Opt in + save a fact via the manager.
    await openMemory(page);
    const dialog = page.getByTestId("memory-dialog");
    await dialog.getByTestId("memory-enabled-switch").click();
    await dialog.getByTestId("memory-add-input").fill("I am a pilot.");
    await dialog.getByTestId("memory-add-button").click();
    await expect(
      dialog.getByTestId("memory-list").getByText("I am a pilot.", {
        exact: true,
      }),
    ).toBeVisible();
    // Close the dialog (Escape) and return to the composer.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("memory-dialog")).toHaveCount(0);

    // Send a real turn through the fake provider.
    await page.getByTestId("composer-textarea").fill("Where am I based?");
    await page.getByTestId("composer-send").click();

    const assistant = page.getByTestId("assistant-message").last();
    await expect(assistant).toHaveAttribute("data-status", "done", {
      timeout: 15_000,
    });

    // The "Memory used here" chip is shown for this turn and opens the manager.
    const chip = assistant.getByTestId("memory-used-chip");
    await expect(chip).toBeVisible();
    await chip.click();
    await expect(page.getByTestId("memory-dialog")).toBeVisible();
  });
});
