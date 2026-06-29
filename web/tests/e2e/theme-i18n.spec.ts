// Theme toggle + i18n direction (Flow 19) E2E.
//
// Closes the ST-4 gaps on `theme-toggle.tsx` and `lib/i18n/context.tsx`. Both
// surfaces are reachable on the PUBLIC `/status` route (it mounts `ThemeToggle`
// in its header, and `DirController` lives in the root layout so it runs on
// every route) — so these tests need no BE bootstrap and stay fast/deterministic.
//
//   - ThemeToggle: cycle System -> Dark -> Light, asserting the `class`
//     attribute on <html> (next-themes `attribute="class"`) and the active-row
//     check mark.
//   - DirController: the `?rtl=1` / `?rtl=0` query hook flips
//     `document.documentElement.dir` live AND persists the choice to the `rtl`
//     cookie, so a subsequent param-less load stays in the chosen direction.

import { expect, test } from "./coverage-fixture";

test.describe("theme toggle", () => {
  test("selecting Dark / Light / System updates the document theme class", async ({
    page,
  }) => {
    await page.goto("/status");
    const trigger = page.getByRole("button", { name: "Change theme" });
    await expect(trigger).toBeVisible();
    // The trigger renders an empty slot until next-themes mounts (post-hydration);
    // the icon <svg> appears only once `mounted` is true. Wait for it so the
    // click lands on a hydrated, interactive trigger rather than a no-op.
    await expect(trigger.locator("svg")).toBeVisible();

    // Dark.
    await trigger.click();
    await page.getByRole("menuitem", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);

    // The active row renders a check mark (theme-toggle.tsx:60-62).
    await trigger.click();
    const darkItem = page.getByRole("menuitem", { name: "Dark" });
    await expect(darkItem.locator("svg.ml-auto")).toBeVisible();

    // Light.
    await page.getByRole("menuitem", { name: "Light" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);

    // System (resolves to the runner's light preference, so still not dark).
    await trigger.click();
    await page.getByRole("menuitem", { name: "System" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
  });
});

test.describe("i18n direction controller", () => {
  test("?rtl=1 flips direction to RTL and persists across a param-less reload", async ({
    page,
  }) => {
    // Query hook → RTL (the DirController `query === "1"` branch + cookie write).
    await page.goto("/status?rtl=1");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    // Param-less navigation: the layout reads the persisted `rtl` cookie
    // server-side and the controller honours it client-side too.
    await page.goto("/status");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    // ?rtl=0 flips back to LTR and rewrites the cookie.
    await page.goto("/status?rtl=0");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await page.goto("/status");
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  });
});
