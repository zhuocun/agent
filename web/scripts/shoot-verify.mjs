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

// 20) History selection → honest empty placeholder (non-c1 conversation)
{
  const { ctx, page } = await newPage(browser, "light", DESKTOP);
  try {
    await page.getByRole("button", { name: /Postgres index strategy/ }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: `${OUT}/20-history-placeholder.png` });
  } catch (e) { console.log("history-placeholder skipped:", e.message); }
  await ctx.close();
}

// 21) Welcome suggestion → PREFILLS composer (not auto-send)
{
  const { ctx, page } = await newPage(browser, "light", DESKTOP);
  try {
    await page.getByRole("button", { name: "New chat" }).first().click();
    await page.waitForTimeout(300);
    await page.getByRole("button", { name: /Debug a stack trace/ }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: `${OUT}/21-welcome-prefill.png` });
  } catch (e) { console.log("welcome-prefill skipped:", e.message); }
  await ctx.close();
}

// 22) Mobile header overflow menu (temporary + settings collapsed under md:)
{
  const { ctx, page } = await newPage(browser, "light", MOBILE);
  try {
    await page.getByRole("button", { name: "More options" }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: `${OUT}/22-mobile-overflow.png` });
  } catch (e) { console.log("mobile-overflow skipped:", e.message); }
  await ctx.close();
}

// 23) Temporary ON = fresh temporary chat + new (cool, de-amber'd) banner color
{
  const { ctx, page } = await newPage(browser, "light", DESKTOP);
  try {
    await page.getByRole("button", { name: "Temporary chat" }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: `${OUT}/23-temporary-newcolor.png` });
  } catch (e) { console.log("temporary-newcolor skipped:", e.message); }
  await ctx.close();
}

// 24) Mobile code block — confirm horizontal scroll, no clip
{
  const { ctx, page } = await newPage(browser, "light", MOBILE);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/24-mobile-codeblock.png` });
  await ctx.close();
}

await browser.close();
console.log("done");
