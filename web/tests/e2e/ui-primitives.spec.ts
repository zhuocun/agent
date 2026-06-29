// UI primitives (`src/components/ui/*`) exercised through their real consuming
// surfaces, per ST-7. We deliberately avoid isolated component tests: every
// primitive below is driven the way a user reaches it (the chat-menu dropdown,
// a failed send's error toast, the sidebar bulk-tag submenu, the mobile nav
// drawer, and a mobile bottom-sheet swipe-to-dismiss).
//
// The genuinely unreachable branches (toast `actions`/`ToastHandle`, the
// `<Badge>` default variant, the `<TooltipProvider>` default delay, the unused
// `Drawer*` subcomponents, and the right-side drawer variant) are covered by
// justified `istanbul ignore` comments in the primitives themselves rather than
// by contrived render harnesses. The mobile nav drawer now mounts with
// `showClose`, so its visible close affordance is exercised below.

import { expect, test } from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

async function sendAndSettle(
  page: import("@playwright/test").Page,
  text: string,
): Promise<void> {
  const composer = page.getByTestId("composer-textarea");
  await composer.fill(text);
  await page.getByTestId("composer-send").click();
  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toBeVisible({ timeout: 15_000 });
  await expect(assistant).toHaveAttribute("data-status", "done", {
    timeout: 15_000,
  });
}

test.describe("ui primitives via real flows", () => {
  // The "Copy conversation" item writes to the clipboard before toasting; grant
  // the permission so the success branch (and the resulting toast) runs.
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("chat-menu dropdown: checkbox + items render, copy fires an auto-dismissing toast", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);
    await sendAndSettle(page, "Hello primitives");

    // Open the app-header overflow menu — a DropdownMenuContent hosting a
    // DropdownMenuCheckboxItem ("Temporary chat") plus several DropdownMenuItems
    // gated by `disabled`.
    await page.getByRole("button", { name: "Chat menu" }).click();
    await expect(
      page.getByRole("menuitemcheckbox", { name: "Temporary chat" }),
    ).toBeVisible();

    const copyItem = page.getByRole("menuitem", { name: "Copy conversation" });
    await expect(copyItem).toBeVisible();
    await copyItem.click();

    // info-severity toast renders as <li role="status" aria-label="Information">
    // (scoped by the aria-label to avoid the sr-only live region). It
    // auto-dismisses after ~5s, driving the ToastItem auto-dismiss timer path.
    const toast = page.getByRole("status", { name: "Information" });
    await expect(toast).toBeVisible({ timeout: 5_000 });
    await expect(toast).toContainText("Conversation copied");
    await expect(toast).toHaveCount(0, { timeout: 9_000 });
  });

  test("toast: a failed send surfaces an error toast dismissable via its close button", async ({
    page,
  }) => {
    // Force the lazy create-on-send to fail so chat-thread raises a persistent
    // (manual-dismiss) error toast.
    await page.route(/\/api\/conversations$/, async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            title: "Couldn't create conversation",
            detail: "Injected failure",
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto("/");
    await waitForBootstrap(page);

    await page.getByTestId("composer-textarea").fill("This send will fail");
    await page.getByTestId("composer-send").click();

    // error-severity toast renders as <li role="alert" aria-label="Error">.
    const toast = page.getByRole("alert", { name: "Error" });
    await expect(toast).toBeVisible({ timeout: 10_000 });

    // The close button drives the dismiss() store path.
    await toast.getByRole("button", { name: "Dismiss notification" }).click();
    await expect(toast).toHaveCount(0);
  });

  test("dropdown submenu: the sidebar bulk-tag menu opens a nested submenu", async ({
    page,
  }) => {
    await page.request.get(`${BE_URL}/api/bootstrap`);
    const created = await page.request.post(`${BE_URL}/api/conversations`, {
      data: { selectedTierId: "smart", isTemporary: false },
    });
    expect(created.status()).toBe(201);

    await page.goto("/");
    await waitForBootstrap(page);

    // Create a tag so the bulk-tag affordance (gated on `tags.length > 0`)
    // renders.
    await page.getByTestId("sidebar-collections-toggle").click();
    await page.getByTestId("sidebar-new-tag").click();
    await page.getByTestId("sidebar-tag-name-input").fill("Bulkable");
    await page.getByTestId("sidebar-tag-save").click();
    await expect(page.getByTestId("sidebar-tags")).toContainText("Bulkable");

    // Enter selection mode and select the conversation so the bulk bar shows.
    await page.getByTestId("sidebar-select-toggle").click();
    await page
      .locator("[data-conversation-id]")
      .first()
      .getByTestId("sidebar-conversation-checkbox")
      .click();
    await expect(page.getByTestId("sidebar-bulk-bar")).toBeVisible();

    // Open the bulk-tag DropdownMenu, then its "Add tag" submenu — this renders
    // the DropdownMenuSubContent (the submenu default-positioning branch).
    await page.getByTestId("sidebar-bulk-tag").click();
    const addTag = page.getByTestId("sidebar-bulk-add-tag");
    await expect(addTag).toBeVisible();
    await addTag.hover();
    await addTag.click();

    await expect(page.getByRole("menuitem", { name: "Bulkable" })).toBeVisible({
      timeout: 5_000,
    });
  });
});

test.describe("ui primitives on mobile", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });

  test("drawer: the touch hamburger opens the slide-in nav drawer", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // The touch-only hamburger (md:hidden) opens the mobile nav Drawer.
    await page.locator('button[aria-label="Open sidebar"]:visible').click();

    const drawer = page.locator('[data-slot="drawer-content"]');
    await expect(drawer).toBeVisible();
    // The drawer hosts the sidebar, so its primary affordance is reachable.
    await expect(drawer.getByTestId("sidebar-new-chat")).toBeVisible();

    // The rail-only collapse chevron is hidden inside the drawer; the visible
    // close (X) affordance is what the drawer offers instead.
    await expect(drawer.locator("[data-sidebar-collapse]")).toBeHidden();

    // The visible close button (showClose) routes through Base UI's close path.
    await drawer.getByRole("button", { name: "Close" }).click();
    await expect(drawer).toHaveCount(0);
  });

  test("dialog: a mobile bottom sheet dismisses on swipe-down", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Reach Settings (a DialogContent) via the drawer-hosted sidebar account
    // menu.
    await page.locator('button[aria-label="Open sidebar"]:visible').click();
    await expect(page.locator('[data-slot="drawer-content"]')).toBeVisible();
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Settings" }).click();

    const dialog = page.getByRole("dialog", { name: "Settings" });
    await expect(dialog).toBeVisible();

    // The bottom sheet carries the iOS grabber; a downward pointer drag past the
    // dismiss threshold runs useSwipeDismiss -> DialogContent's onDismiss
    // (clicking the hidden close ref), closing the sheet.
    const grabber = dialog.locator('[aria-hidden="true"].cursor-grab').first();
    const box = await grabber.boundingBox();
    expect(box).not.toBeNull();
    const startX = box!.x + box!.width / 2;
    const startY = box!.y + box!.height / 2;

    await page.mouse.move(startX, startY);
    await page.mouse.down();
    // Several incremental moves so velocity/drag state accumulate, traveling
    // well past 25% of the sheet height.
    for (let i = 1; i <= 8; i++) {
      await page.mouse.move(startX, startY + i * 70, { steps: 2 });
    }
    await page.mouse.up();

    await expect(dialog).toBeHidden({ timeout: 5_000 });
  });
});
