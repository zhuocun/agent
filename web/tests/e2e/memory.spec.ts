// Transparent long-term memory (D19) — runtime coverage against the live BE.
//
// Drives the real shell + real bootstrap (no stubbing). Two flows:
//   1. The memory manager CRUD: open Settings → "Memory", toggle the opt-in,
//      add / edit / delete a fact, asserting the ledger updates each step.
//   2. The "Memory used here" indicator: with memory ON and a fact saved, send a
//      real (fake-provider) turn and assert the chip appears on the assistant
//      message and opens the manager on click.

import { expect, test, type Page } from "@playwright/test";

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
