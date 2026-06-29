// Auth dialog — sign-in / create-account UI.
//
// The auth dialog is reachable only for anonymous (guest) sessions, which the
// real BE bootstrap mints on first hit (empty email => the FE treats the
// session as a guest, so the "Sign in" CTA appears in the account menu).
//
// This spec exercises /api/auth/login + /api/auth/upgrade two ways:
//   - REAL round-trips against the live BE (sign-up, sign-in, wrong password,
//     taken email) so the apiClient success/error decode paths run end-to-end.
//   - page.route() stubs for the error envelopes that can't be produced
//     deterministically against the live BE (429 throttle, network abort,
//     ALREADY_UPGRADED, generic 400/401) so the dialog's error-mapping
//     branches are all covered. Bootstrap always goes to the real BE.

import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "./coverage-fixture";

import { BE_URL, waitForBootstrap } from "./helpers";

// A throwaway email unique per test invocation so real-BE registrations never
// collide across re-runs of the ephemeral SQLite DB.
function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 8)}@example.com`;
}

// Register an account on an INDEPENDENT session. The top-level `request` fixture
// is an isolated APIRequestContext with its own cookie jar (it does NOT share
// the page's anon `sid`), so the page can later collide with this account
// (EMAIL_TAKEN) or sign into it (INVALID_CREDENTIALS on a wrong password)
// exactly as a second visitor would.
async function registerOnSeparateSession(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<void> {
  const boot = await request.get(`${BE_URL}/api/bootstrap`);
  expect(boot.ok()).toBe(true);
  const upgrade = await request.post(`${BE_URL}/api/auth/upgrade`, {
    data: { email, password },
  });
  expect(upgrade.ok()).toBe(true);
}

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
    await page.route("**/api/auth/login", async (route) => {
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
    const request = await loginRequest;

    expect(request.postDataJSON()).toEqual({
      email: "ada@example.com",
      password: "correct-horse",
    });
  });

  test("create-account submits to /api/auth/upgrade", async ({ page }) => {
    await page.route("**/api/auth/upgrade", async (route) => {
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
    const request = await upgradeRequest;

    expect(request.postDataJSON()).toEqual({
      email: "grace@example.com",
      password: "amazing-grace",
    });
  });

  // --- REAL round-trips against the live BE (no route stubs) ----------------
  // These drive the actual /api/auth/* endpoints so the apiClient success /
  // error decode paths are exercised, not just the dialog's request shape.

  test("real create-account upgrades the guest and reloads signed in", async ({
    page,
  }) => {
    await openAuthDialog(page);
    await page.getByRole("button", { name: "Create an account" }).click();

    const email = uniqueEmail("signup");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("create-e2e-password");

    // Watch the upgrade land before onSuccess reloads the shell out from under
    // us. A 200 means the anon session was promoted to this account.
    const upgrade = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/auth/upgrade` &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    expect((await upgrade).status()).toBe(200);

    // The reload re-bootstraps as the now-registered user, so the account menu
    // offers "Sign out" (guests get "Sign in").
    await waitForBootstrap(page);
    await page.getByRole("button", { name: "Account menu" }).click();
    await expect(
      page.getByRole("menuitem", { name: "Sign out" }),
    ).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Sign in" })).toHaveCount(0);
  });

  test("real sign-in authenticates against an existing account", async ({
    page,
    request,
  }) => {
    const email = uniqueEmail("signin");
    const password = "signin-e2e-password";
    await registerOnSeparateSession(request, email, password);

    await openAuthDialog(page);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);

    const login = page.waitForResponse(
      (r) =>
        r.url() === `${BE_URL}/api/auth/login` &&
        r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    expect((await login).status()).toBe(200);

    await waitForBootstrap(page);
    await page.getByRole("button", { name: "Account menu" }).click();
    await expect(
      page.getByRole("menuitem", { name: "Sign out" }),
    ).toBeVisible();
  });

  test("real wrong password shows the invalid-credentials message", async ({
    page,
    request,
  }) => {
    const email = uniqueEmail("wrongpw");
    await registerOnSeparateSession(request, email, "the-correct-password");

    await openAuthDialog(page);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(
      page.getByText("Incorrect email or password."),
    ).toBeVisible();
    // The form stays open on failure (no reload / navigation).
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });

  test("real create-account with a taken email surfaces the conflict", async ({
    page,
    request,
  }) => {
    const email = uniqueEmail("dupe");
    await registerOnSeparateSession(request, email, "first-owner-password");

    await openAuthDialog(page);
    await page.getByRole("button", { name: "Create an account" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("second-tries-password");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();

    await expect(
      page.getByText("An account with that email already exists."),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Create account" }),
    ).toBeVisible();
  });

  test("submitting with empty fields shows an inline validation error", async ({
    page,
  }) => {
    await openAuthDialog(page);
    // No email/password entered — the client-side guard fires before any
    // network call (the form is noValidate).
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByText("Enter your email and password."),
    ).toBeVisible();
  });

  test("password visibility toggle reveals and hides the entered text", async ({
    page,
  }) => {
    await openAuthDialog(page);
    const pw = page.getByLabel("Password");
    await pw.fill("peekaboo");
    await expect(pw).toHaveAttribute("type", "password");

    await page.getByRole("button", { name: "Show entered text" }).click();
    await expect(pw).toHaveAttribute("type", "text");

    await page.getByRole("button", { name: "Hide entered text" }).click();
    await expect(pw).toHaveAttribute("type", "password");
  });

  test("closing the dialog resets mode and fields", async ({ page }) => {
    await openAuthDialog(page);
    await page.getByRole("button", { name: "Create an account" }).click();
    await page.getByLabel("Email").fill("temp@example.com");
    await expect(
      page.getByRole("heading", { name: "Create account" }),
    ).toBeVisible();

    // Escape closes the dialog, which runs the reset (mode → signin, fields
    // cleared).
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Create account" }),
    ).toHaveCount(0);

    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByLabel("Email")).toHaveValue("");
  });

  test("maps a 429 to a throttle message", async ({ page }) => {
    await page.route("**/api/auth/login", async (route) => {
      await route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "RATE_LIMITED",
            severity: "error",
            title: "Slow down",
            body: "Too many requests.",
          },
        }),
      });
    });

    await openAuthDialog(page);
    await page.getByLabel("Email").fill("someone@example.com");
    await page.getByLabel("Password").fill("whatever-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(
      page.getByText("Too many attempts. Try again in a minute."),
    ).toBeVisible();
  });

  test("maps a network failure to a connection message", async ({ page }) => {
    await openAuthDialog(page);
    // Abort only after the dialog is open so the bootstrap fetch isn't harmed.
    await page.route("**/api/auth/login", (route) => route.abort());

    await page.getByLabel("Email").fill("someone@example.com");
    await page.getByLabel("Password").fill("whatever-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(
      page.getByText(
        "Couldn't reach the server. Check your connection and try again.",
      ),
    ).toBeVisible();
  });

  test("maps ALREADY_UPGRADED on create-account", async ({ page }) => {
    await page.route("**/api/auth/upgrade", async (route) => {
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "ALREADY_UPGRADED",
            severity: "error",
            title: "Already linked",
            body: "Session already has an account.",
          },
        }),
      });
    });

    await openAuthDialog(page);
    await page.getByRole("button", { name: "Create an account" }).click();
    await page.getByLabel("Email").fill("dupe-session@example.com");
    await page.getByLabel("Password").fill("whatever-123");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();

    await expect(
      page.getByText(
        "This session is already linked to an account. Sign in instead.",
      ),
    ).toBeVisible();
  });

  test("surfaces the server's own copy for a 400 validation error", async ({
    page,
  }) => {
    await page.route("**/api/auth/login", async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "VALIDATION",
            severity: "error",
            title: "Invalid",
            body: "Email looks malformed.",
          },
        }),
      });
    });

    await openAuthDialog(page);
    await page.getByLabel("Email").fill("malformed");
    await page.getByLabel("Password").fill("whatever-123");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();

    await expect(page.getByText("Email looks malformed.")).toBeVisible();
  });
});
