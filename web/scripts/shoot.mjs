import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const URL = process.env.SHOT_URL ?? "http://localhost:3100/";
const OUT = "/tmp/shots";
mkdirSync(OUT, { recursive: true });

const VIEWPORT = { width: 1280, height: 880 };

async function newPage(browser, theme) {
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
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

// 1) Light — full thread
{
  const { ctx, page } = await newPage(browser, "light");
  await page.screenshot({ path: `${OUT}/01-light.png` });
  // 1b) tier picker open
  try {
    await page.getByRole("button", { name: /Model:/ }).click();
    await page.waitForTimeout(350);
    await page.screenshot({ path: `${OUT}/02-tier-open.png` });
    await page.keyboard.press("Escape");
  } catch (e) { console.log("tier-picker shot skipped:", e.message); }
  // 1c) expand a cost breakdown (the one with the substitution)
  try {
    const expanders = page.getByRole("button", { name: /detail/i });
    const n = await expanders.count();
    if (n > 0) {
      await expanders.nth(n - 1).click();
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/03-cost-expanded.png` });
    }
  } catch (e) { console.log("cost-expand shot skipped:", e.message); }
  await ctx.close();
}

// 2) Dark — full thread
{
  const { ctx, page } = await newPage(browser, "dark");
  await page.screenshot({ path: `${OUT}/04-dark.png` });
  await ctx.close();
}

// 3) Streaming mid-state — send a message, snapshot during stream
{
  const { ctx, page } = await newPage(browser, "light");
  const box = page.getByPlaceholder("Message Aperture…");
  await box.click();
  await box.fill("How do I avoid the loading spinner flashing on fast responses?");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1500); // pre-token + into reasoning/answer stream
  await page.screenshot({ path: `${OUT}/05-streaming.png` });
  await page.waitForTimeout(3500); // let it finish
  await page.screenshot({ path: `${OUT}/06-after-stream.png` });
  await ctx.close();
}

await browser.close();
console.log("done");
