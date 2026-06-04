// Vision gating — image attachments on a non-vision tier (the real prod bug).
//
// Runs against the REAL BE + FakeProvider (PROVIDER_BACKEND=fake), where the
// fake tier registry deliberately makes `fast` attachment-capable-but-NOT-vision
// while `smart`/`auto`/`pro` are vision-capable
// (api/app/providers/tiers.py::_FAKE_SUPPORTS_VISION). This lets us drive BOTH
// the vision-allowed and the vision-removed paths from one fixture.
//
// What this exercises:
//   (a) on a VISION tier (Smart) an attached image is kept
//   (b) switching to a NON-vision tier (Fast) auto-removes ONLY the image and
//       surfaces the "Images aren't supported by this model" notice
//   (c) PDFs/text are NOT image attachments, so they are unaffected by the
//       vision gate (covered implicitly — the gate filters on mediaType image)

import { expect, test } from "@playwright/test";

import { waitForBootstrap } from "./helpers";

// A tiny valid 1x1 PNG so the composer's image-type detection treats it as an
// image attachment.
const PNG_1x1 = Buffer.from(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4" +
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae426082",
  "hex",
);

async function selectTier(
  page: import("@playwright/test").Page,
  label: string,
): Promise<void> {
  await page.getByTestId("model-mode-trigger").click();
  await page
    .locator('[data-slot="dropdown-menu-item"]:visible', { hasText: label })
    .first()
    .click();
  // Dismiss the menu so it doesn't overlay the composer.
  await expect(
    page.locator('[data-slot="dropdown-menu-item"]:visible'),
  ).toHaveCount(0);
}

test.describe("vision gating", () => {
  test("switching to a non-vision tier removes image attachments (PDF/text would stay)", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Start on a vision-capable tier so the image is accepted and kept.
    await selectTier(page, "Smart");

    await page.getByTestId("composer-file-input").setInputFiles({
      name: "sketch.png",
      mimeType: "image/png",
      buffer: PNG_1x1,
    });
    await expect(page.getByText("sketch.png")).toBeVisible();

    // Switch to the non-vision tier (Fast): the image is auto-removed with a
    // clear notice.
    await selectTier(page, "Fast");
    await expect(
      page.getByText("Images aren't supported by this model and were removed."),
    ).toBeVisible();
    await expect(page.getByText("sketch.png")).toHaveCount(0);
  });

  test("a vision tier keeps an attached image", async ({ page }) => {
    await page.goto("/");
    await waitForBootstrap(page);

    // Auto is vision-capable in the fake registry.
    await selectTier(page, "Smart");

    await page.getByTestId("composer-file-input").setInputFiles({
      name: "kept.png",
      mimeType: "image/png",
      buffer: PNG_1x1,
    });
    await expect(page.getByText("kept.png")).toBeVisible();

    // Staying on / re-selecting a vision tier keeps the image attached.
    await selectTier(page, "Auto");
    await expect(page.getByText("kept.png")).toBeVisible();
    await expect(
      page.getByText("Images aren't supported by this model and were removed."),
    ).toHaveCount(0);
  });
});
