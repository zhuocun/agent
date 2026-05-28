// Visual-regression screenshots for the chat UI. Captures the thread, the
// surrounding chrome (sidebar, onboarding, trust surfaces), and the mobile
// layout across light/dark. Run against a dev server:
//   PORT=3100 pnpm dev   # in one shell
//   node scripts/shoot.mjs
// Output: /tmp/shots/*.png
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const URL = process.env.SHOT_URL ?? "http://localhost:3100/";
const OUT = process.env.SHOT_OUT ?? "/tmp/shots";
mkdirSync(OUT, { recursive: true });

const DESKTOP = { width: 1280, height: 880 };
const MOBILE = { width: 390, height: 844 };

async function open(browser, { theme = "light", viewport = DESKTOP } = {}) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  await ctx.addInitScript((t) => {
    try {
      localStorage.setItem("theme", t);
    } catch {}
  }, theme);
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.getByPlaceholder("Message Olune…").waitFor({ timeout: 15000 });
  await page.waitForTimeout(500);
  return { ctx, page };
}

const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png` });

const browser = await chromium.launch();

// ---- Thread (desktop) -------------------------------------------------------
{
  const { ctx, page } = await open(browser, { theme: "light" });
  await shot(page, "thread-01-light");
  try {
    await page.getByRole("button", { name: /Model:/ }).click();
    await page.waitForTimeout(350);
    await shot(page, "thread-02-tier-open");
    await page.keyboard.press("Escape");
  } catch (e) {
    console.log("tier-open skipped:", e.message);
  }
  try {
    const expanders = page.getByRole("button", { name: /detail/i });
    const n = await expanders.count();
    if (n > 0) {
      await expanders.nth(n - 1).click();
      await page.waitForTimeout(300);
      await shot(page, "thread-03-cost-expanded");
    }
  } catch (e) {
    console.log("cost-expanded skipped:", e.message);
  }
  await ctx.close();
}
{
  const { ctx, page } = await open(browser, { theme: "dark" });
  await shot(page, "thread-04-dark");
  await ctx.close();
}
{
  const { ctx, page } = await open(browser, { theme: "light" });
  const box = page.getByPlaceholder("Message Olune…");
  await box.click();
  await box.fill("How do I avoid the loading spinner flashing on fast responses?");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1500);
  await shot(page, "thread-05-streaming");
  await page.waitForTimeout(3500);
  await shot(page, "thread-06-after-stream");
  await ctx.close();
}

// ---- Chrome (desktop) -------------------------------------------------------
{
  const { ctx, page } = await open(browser, { theme: "light" });
  try {
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await page.waitForTimeout(350);
    await shot(page, "desktop-collapsed");
  } catch (e) {
    console.log("collapsed skipped:", e.message);
  }
  await ctx.close();
}
{
  // New chat → welcome hero, then a suggestion prefills the composer.
  const { ctx, page } = await open(browser, { theme: "light" });
  try {
    await page.getByRole("button", { name: "New chat" }).first().click();
    await page.waitForTimeout(300);
    await shot(page, "desktop-welcome");
    await page.getByRole("button", { name: /Debug a stack trace/ }).click();
    await page.waitForTimeout(350);
    await shot(page, "desktop-welcome-prefill");
  } catch (e) {
    console.log("welcome skipped:", e.message);
  }
  await ctx.close();
}
{
  // Selecting a history entry without loaded content → honest placeholder.
  const { ctx, page } = await open(browser, { theme: "light" });
  try {
    await page.getByRole("button", { name: /Postgres index strategy/ }).click();
    await page.waitForTimeout(350);
    await shot(page, "desktop-history-empty");
  } catch (e) {
    console.log("history-empty skipped:", e.message);
  }
  await ctx.close();
}
{
  // Temporary ON starts a fresh chat; banner uses the calm (non-amber) token.
  const { ctx, page } = await open(browser, { theme: "light" });
  try {
    await page.getByRole("button", { name: "Temporary chat" }).click();
    await page.waitForTimeout(350);
    await shot(page, "desktop-temporary");
  } catch (e) {
    console.log("temporary skipped:", e.message);
  }
  await ctx.close();
}
for (const theme of ["light", "dark"]) {
  const { ctx, page } = await open(browser, { theme });
  try {
    await page.getByRole("button", { name: "Open settings" }).first().click();
    await page.waitForTimeout(400);
    await shot(page, `desktop-settings-${theme}`);
  } catch (e) {
    console.log(`settings-${theme} skipped:`, e.message);
  }
  await ctx.close();
}

// ---- Mobile (390px) ---------------------------------------------------------
{
  const { ctx, page } = await open(browser, { theme: "light", viewport: MOBILE });
  await shot(page, "mobile-thread");
  try {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page.waitForTimeout(450);
    await shot(page, "mobile-drawer");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  } catch (e) {
    console.log("mobile-drawer skipped:", e.message);
  }
  // Temporary + Settings live in the overflow menu below md:.
  try {
    await page.getByRole("button", { name: "More options" }).click();
    await page.waitForTimeout(350);
    await shot(page, "mobile-overflow");
    await page.getByRole("menuitem", { name: "Settings" }).click();
    await page.waitForTimeout(400);
    await shot(page, "mobile-settings");
  } catch (e) {
    console.log("mobile-overflow/settings skipped:", e.message);
  }
  await ctx.close();
}

await browser.close();
console.log("done");
