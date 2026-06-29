// Prompt library + user-authored templates (D23) — runtime coverage against
// the live BE. Drives the real shell + real bootstrap (no stubbing). Two flows:
//   1. The template manager CRUD: open Settings → "Prompt templates", add /
//      edit / delete a template, asserting the library updates each step.
//   2. The composer picker: open the toolbar picker, choose a template, and
//      assert the rendered body lands in the composer with the cursor parked on
//      the first `{{placeholder}}`.

import { expect, test, type Page } from "./coverage-fixture";

import { waitForBootstrap } from "./helpers";

async function openTemplates(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByTestId("open-templates-button").click();
  await expect(page.getByTestId("template-dialog")).toBeVisible();
}

test.describe("prompt library + user-authored templates", () => {
  test("manage templates: add, edit, delete", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    await openTemplates(page);
    const dialog = page.getByTestId("template-dialog");

    // Add a template.
    await dialog.getByTestId("template-add-title").fill("Blog outline");
    await dialog
      .getByTestId("template-add-body")
      .fill("Outline a blog post about {{topic}}.");
    await dialog
      .getByTestId("template-add-description")
      .fill("Long-form draft");
    await dialog.getByTestId("template-add-button").click();

    const list = dialog.getByTestId("template-list");
    await expect(list).toBeVisible();
    await expect(
      list.getByText("Blog outline", { exact: true }),
    ).toBeVisible();
    await expect(
      list.getByText("Outline a blog post about {{topic}}.", { exact: true }),
    ).toBeVisible();

    // Edit it.
    await dialog.getByTestId("template-edit-button").first().click();
    await dialog.getByTestId("template-edit-title").fill("Blog outline v2");
    await dialog
      .getByTestId("template-edit-body")
      .fill("Outline a detailed post about {{topic}} for {{audience}}.");
    await dialog.getByTestId("template-edit-save").click();
    await expect(
      list.getByText("Blog outline v2", { exact: true }),
    ).toBeVisible();
    await expect(
      list.getByText("Blog outline", { exact: true }),
    ).toHaveCount(0);

    // Delete it.
    await dialog.getByTestId("template-delete-button").first().click();
    await expect(dialog.getByTestId("template-item")).toHaveCount(0);

    await dialog.screenshot({
      path: "/opt/cursor/artifacts/template_dialog.png",
    });
  });

  test("insert a template into the composer via the toolbar picker", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Seed a template through the manager.
    await openTemplates(page);
    const dialog = page.getByTestId("template-dialog");
    await dialog.getByTestId("template-add-title").fill("Standup update");
    await dialog
      .getByTestId("template-add-body")
      .fill("Write a standup update about {{project}} for {{date}}.");
    await dialog.getByTestId("template-add-button").click();
    await expect(
      dialog
        .getByTestId("template-list")
        .getByText("Write a standup update about {{project}} for {{date}}.", {
          exact: true,
        }),
    ).toBeVisible();

    // Close the dialog and return to the composer.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("template-dialog")).toHaveCount(0);

    // Open the composer's template picker and choose the template. The
    // templates control lives behind the "More actions" (+) disclosure.
    await page.getByTestId("composer-more-actions").click();
    await page.getByTestId("composer-templates").click();
    const picker = page.getByTestId("template-picker");
    await expect(picker).toBeVisible();
    await picker
      .getByTestId("template-picker-option")
      .getByText("Standup update", { exact: true })
      .click();

    // The body is prefilled verbatim (placeholders are literal text).
    const textarea = page.getByTestId("composer-textarea");
    await expect(textarea).toHaveValue(
      "Write a standup update about {{project}} for {{date}}.",
    );

    // The cursor is parked on the FIRST `{{…}}` placeholder so the user types
    // straight into it. `{{project}}` starts right after "Write a standup
    // update about ".
    const expectedOffset = "Write a standup update about ".length;
    const selectionStart = await textarea.evaluate(
      (el) => (el as HTMLTextAreaElement).selectionStart,
    );
    expect(selectionStart).toBe(expectedOffset);

    // The picker closed on pick.
    await expect(page.getByTestId("template-picker")).toHaveCount(0);
  });
});
