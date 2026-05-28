import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const URL = process.env.SHOT_URL ?? "http://localhost:3100/";
const OUT = "/tmp/shots";
mkdirSync(OUT, { recursive: true });

const DESKTOP = { width: 1280, height: 880 };
const MOBILE = { width: 390, height: 844 };

async function newPage(browser, theme, viewport) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2 });
  if (theme) {
    await ctx.addInitScript((t) => {
      try { localStorage.setItem("theme", t); } catch {}
    }, theme);
  }
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.getByPlaceholder("Message Aperture…").waitFor({ timeout: 15000 });
  await page.waitForTimeout(500);
  return { ctx, page };
}

const browser = await chromium.launch();

// 10) Desktop light — full app with sidebar
{
  const { ctx, page } = await newPage(browser, "light", DESKTOP);
  await page.screenshot({ path: `${OUT}/10-desktop-sidebar-light.png` });

  // 11) collapse the sidebar
  try {
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: `${OUT}/11-desktop-collapsed.png` });
  } catch (e) { console.log("collapse shot skipped:", e.message); }
  await ctx.close();
}

// 12) Desktop dark — with sidebar
{
  const { ctx, page } = await newPage(browser, "dark", DESKTOP);
  await page.screenshot({ path: `${OUT}/12-desktop-sidebar-dark.png` });
  await ctx.close();
}

// 13) Empty / welcome state (New chat)
{
  const { ctx, page } = await newPage(browser, "light", DESKTOP);
  try {
    await page.getByRole("button", { name: "New chat" }).first().click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/13-welcome.png` });
  } catch (e) { console.log("welcome shot skipped:", e.message); }
  await ctx.close();
}

// 14) Settings dialog open
{
  const { ctx, page } = await newPage(browser, "light", DESKTOP);
  try {
    await page.getByRole("button", { name: "Open settings" }).first().click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/14-settings.png` });
  } catch (e) { console.log("settings shot skipped:", e.message); }
  await ctx.close();
}

// 15) Settings dialog open — dark
{
  const { ctx, page } = await newPage(browser, "dark", DESKTOP);
  try {
    await page.getByRole("button", { name: "Open settings" }).first().click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/15-settings-dark.png` });
  } catch (e) { console.log("settings-dark shot skipped:", e.message); }
  await ctx.close();
}

// 16) Temporary-chat banner active
{
  const { ctx, page } = await newPage(browser, "light", DESKTOP);
  try {
    await page.getByRole("button", { name: "Temporary chat" }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: `${OUT}/16-temporary.png` });
  } catch (e) { console.log("temporary shot skipped:", e.message); }
  await ctx.close();
}

// 17) Mobile — full thread (sidebar collapsed into drawer)
{
  const { ctx, page } = await newPage(browser, "light", MOBILE);
  await page.screenshot({ path: `${OUT}/17-mobile-thread.png` });

  // 18) open the mobile nav drawer
  try {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page.waitForTimeout(450);
    await page.screenshot({ path: `${OUT}/18-mobile-drawer.png` });
  } catch (e) { console.log("mobile-drawer shot skipped:", e.message); }
  await ctx.close();
}

// 19) Mobile — settings dialog
{
  const { ctx, page } = await newPage(browser, "light", MOBILE);
  try {
    await page.getByRole("button", { name: "Open settings" }).first().click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${OUT}/19-mobile-settings.png` });
  } catch (e) { console.log("mobile-settings shot skipped:", e.message); }
  await ctx.close();
}

await browser.close();
console.log("done");
