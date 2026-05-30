// Auth dialog — sign-in / create-account UI.
//
// The auth dialog is reachable only for anonymous (guest) sessions, which the
// real BE bootstrap mints on first hit (empty email => the FE treats the
// session as a guest, so the "Sign in" CTA appears in the account menu).
//
// The /api/auth/login + /api/auth/upgrade endpoints are exercised here via
// page.route() stubs rather than the live BE: this spec owns the FE dialog
// behaviour (render, mode toggle, error mapping, request shape), and stubbing
// keeps it green regardless of whether the parallel BE half has shipped those
// routes yet. Bootstrap itself still goes to the real BE on :8000.

import { expect, test, type Page } from "@playwright/test";

import { waitForBootstrap } from "./helpers";

// Open the account menu and click the guest-only "Sign in" item, landing us in
// the auth dialog. Asserts the dialog's sign-in heading is visible.
async function openAuthDialog(page: Page): Promise<void> {
  await page.goto("/");
  await waitForBootstrap(page);

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign in" }).click();

  await expect(
    page.getByRole("heading", { name: "Sign in" }),
  ).toBeVisible();
}

test.describe("auth dialog", () => {
  test("opens from the account menu and renders the sign-in form", async ({
    page,
  }) => {
    await openAuthDialog(page);

    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();
  });

  test("toggles between sign-in and create-account modes", async ({ page }) => {
    await openAuthDialog(page);

    // Switch to create-account mode.
    await page.getByRole("button", { name: "Create an account" }).click();
    await expect(
      page.getByRole("heading", { name: "Create account" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Create account", exact: true }),
    ).toBeVisible();

    // Switch back.
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Sign in" }),
    ).toBeVisible();
  });

  test("shows an inline error when the credentials are rejected", async ({
    page,
  }) => {
    // Stub the login endpoint to reject with the frozen INVALID_CREDENTIALS
    // envelope. The proxy path means the request hits /api/auth/login on the
    // FE origin; match both that and the direct BE origin to be safe.
    await page.route("**/api/auth/login", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "INVALID_CREDENTIALS",
            severity: "error",
            title: "Sign in failed",
            body: "Wrong email or password.",
          },
        }),
      });
    });

    await openAuthDialog(page);

    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(
      page.getByText("Incorrect email or password."),
    ).toBeVisible();

    // The dialog stays open on failure (no reload / no navigation).
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("submits sign-in to /api/auth/login with the entered credentials", async ({
    page,
  }) => {
    let loginBody: unknown = null;
    await page.route("**/api/auth/login", async (route) => {
      loginBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          name: "Ada Lovelace",
          email: "ada@example.com",
          planLabel: "Free",
          byokEnabled: false,
          isAnonymous: false,
        }),
      });
    });

    await openAuthDialog(page);

    await page.getByLabel("Email").fill("ada@example.com");
    await page.getByLabel("Password").fill("correct-horse");

    // Success triggers a full reload; wait for the request to be observed
    // before the navigation tears the page down.
    const loginRequest = page.waitForRequest("**/api/auth/login");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await loginRequest;

    expect(loginBody).toEqual({
      email: "ada@example.com",
      password: "correct-horse",
    });
  });

  test("create-account submits to /api/auth/upgrade", async ({ page }) => {
    let upgradeBody: unknown = null;
    await page.route("**/api/auth/upgrade", async (route) => {
      upgradeBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          name: "Grace Hopper",
          email: "grace@example.com",
          planLabel: "Free",
          byokEnabled: false,
          isAnonymous: false,
        }),
      });
    });

    await openAuthDialog(page);
    await page.getByRole("button", { name: "Create an account" }).click();

    await page.getByLabel("Email").fill("grace@example.com");
    await page.getByLabel("Password").fill("amazing-grace");

    const upgradeRequest = page.waitForRequest("**/api/auth/upgrade");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await upgradeRequest;

    expect(upgradeBody).toEqual({
      email: "grace@example.com",
      password: "amazing-grace",
    });
  });
});
