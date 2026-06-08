// Projects/Spaces (D20) — sidebar + settings ↔ BE round-trip.
//
// Mirrors retention.spec.ts / conversation.spec.ts: drive the real FE against
// the real BE on :8000. Covers the project lifecycle end-to-end:
//   - create a project from the sidebar (POST /api/projects)
//   - assign a conversation to it via the row kebab (PATCH projectId), and see
//     the conversation regroup under the project section
//   - edit a project setting in the settings dialog (PATCH a setting)
//   - delete the project (DELETE /api/projects/:id), which un-files (keeps) its
//     conversations
//
// Each test gets a fresh browser context => fresh anon user => clean slate.

import { expect, test } from "@playwright/test";

import { BE_URL, waitForBootstrap } from "./helpers";

test.describe("projects / spaces", () => {
  test("create a project, assign a conversation, edit a setting, delete it", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    // A conversation to file under the project (BE row minted via the API).
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    expect(created.status()).toBe(201);
    const { id: convoId } = await created.json();

    await page.goto("/");
    await waitForBootstrap(page);

    // --- Create a project from the sidebar -----------------------------------
    const createPost = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/projects` &&
        r.request().method() === "POST",
    );
    // Projects + Tags now live inside the collapsed-by-default "Collections"
    // disclosure; expand it before the first projects interaction (it stays open
    // for the rest of the test).
    await page.getByTestId("sidebar-collections-toggle").click();
    await page.getByTestId("sidebar-new-project").click();
    const nameInput = page.getByTestId("sidebar-project-name-input");
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Research");
    await page.getByTestId("sidebar-project-save").click();
    expect((await createPost).status()).toBe(201);

    // The project appears in the Projects section.
    const projectsSection = page.getByTestId("sidebar-projects");
    await expect(projectsSection).toContainText("Research");

    // --- Assign the conversation to the project ------------------------------
    const row = page.locator(`[data-conversation-id="${convoId}"]`);
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Conversation actions" }).click();
    // "Organize…" now opens a flat dialog (no nested submenus); the "Assign to
    // project" section lists radio rows. Pick "Research".
    await page.getByTestId("sidebar-conversation-organize").click();
    const projectGroup = page.getByTestId("sidebar-conversation-assign-project");
    await expect(projectGroup).toBeVisible();
    const projectItem = projectGroup.getByRole("radio", { name: "Research" });
    await expect(projectItem).toBeVisible();

    const assignPatch = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/conversations/${convoId}` &&
        r.request().method() === "PATCH",
    );
    await projectItem.click();
    const assignResponse = await assignPatch;
    expect(assignResponse.status()).toBe(200);
    const assignedProjectId = (await assignResponse.json()).projectId as string;
    expect(assignedProjectId).toBeTruthy();

    // Close the organize dialog (a selection leaves it open) before touching the
    // sidebar again.
    await page.keyboard.press("Escape");
    await expect(projectGroup).toHaveCount(0);

    // The conversation now renders grouped under the project (the project
    // section lists its filed conversations).
    await expect(
      projectsSection.locator(`[data-conversation-id="${convoId}"]`),
    ).toBeVisible();

    // --- Edit a project setting in the settings dialog -----------------------
    await page.getByTestId("sidebar-new-chat"); // ensure sidebar is interactive
    // Open settings via the project kebab "Project settings" entry point.
    await projectsSection
      .getByRole("button", { name: "Project actions" })
      .first()
      .click();
    await page.getByRole("menuitem", { name: "Project settings" }).click();

    // Project defaults collapsed by default — expand before editing.
    await page.getByTestId("project-defaults-toggle").click();

    const panel = page.getByTestId("project-settings-panel");
    await expect(panel).toBeVisible();

    // Change the project's default model to "Fast" — PATCHes defaultTierId.
    const tierPatch = page.waitForResponse(
      (r) =>
        r.url() ===
          `${BE_URL}/api/projects/${encodeURIComponent(assignedProjectId)}` &&
        r.request().method() === "PATCH",
    );
    await panel.getByRole("button", { name: "Fast", exact: true }).click();
    const tierResponse = await tierPatch;
    expect(tierResponse.status()).toBe(200);
    expect((await tierResponse.json()).defaultTierId).toBe("fast");

    // Close the settings dialog (Escape).
    await page.keyboard.press("Escape");

    // --- Delete the project --------------------------------------------------
    await projectsSection
      .getByRole("button", { name: "Project actions" })
      .first()
      .click();
    await page.getByRole("menuitem", { name: "Delete" }).click();

    const deleteReq = page.waitForResponse(
      (r) =>
        r.url() ===
          `${BE_URL}/api/projects/${encodeURIComponent(assignedProjectId)}` &&
        r.request().method() === "DELETE",
    );
    await page.getByTestId("sidebar-project-delete-confirm").click();
    expect((await deleteReq).status()).toBe(204);

    // The project is gone from the sidebar; the conversation survives, un-filed.
    await expect(projectsSection).not.toContainText("Research");
    const afterDelete = await page.request.get(
      `${BE_URL}/api/conversations/${convoId}`,
    );
    expect(afterDelete.status()).toBe(200);
    expect((await afterDelete.json()).projectId).toBeNull();
  });
});
