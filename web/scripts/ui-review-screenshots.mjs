/**
 * One-off UI review screenshot harness. Captures desktop + mobile views of
 * major app surfaces for UX audit. Run with dev servers on :3000/:8000.
 */
import { chromium, devices } from "playwright";
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve("test-results/ui-review");
const FE_URL = "http://localhost:3000";

async function waitForBootstrap(page) {
  await page.getByTestId("composer-textarea").waitFor({ state: "visible", timeout: 30_000 });
  // Let welcome entrance animations settle before capturing.
  await page.waitForTimeout(500);
}

async function capture(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`saved ${file}`);
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch();

  // Desktop
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await desktop.goto(FE_URL);
  await waitForBootstrap(desktop);
  await capture(desktop, "desktop-welcome-light");

  // Theme lives in command palette (Cmd+K) or sidebar settings — skip for harness
  const openSidebar = desktop.getByRole("button", { name: /open sidebar/i });
  if (await openSidebar.count()) {
    await openSidebar.first().click();
    await desktop.waitForTimeout(400);
    await capture(desktop, "desktop-sidebar-open");
  }

  await desktop.getByTestId("composer-textarea").fill("Hello, review the UI please");
  await desktop.getByTestId("composer-send").click();
  await desktop.waitForTimeout(2000);
  await capture(desktop, "desktop-chat-streaming");

  await desktop.waitForTimeout(3000);
  await capture(desktop, "desktop-chat-complete");

  await desktop.keyboard.press("Control+k");
  await desktop.waitForTimeout(400);
  await desktop.getByPlaceholder(/search/i).fill("settings");
  await desktop.keyboard.press("Enter");
  await desktop.waitForTimeout(500);
  await capture(desktop, "desktop-settings-dialog");
  await desktop.keyboard.press("Escape");

  await desktop.keyboard.press("Control+Slash");
  await desktop.waitForTimeout(400);
  await desktop.waitForTimeout(400);
  await capture(desktop, "desktop-shortcuts-dialog");
  await desktop.keyboard.press("Escape");

  // Mobile (iPhone 13)
  const iphone = devices["iPhone 13"];
  const mobile = await browser.newPage({
    ...iphone,
    viewport: iphone.viewport,
  });
  await mobile.goto(FE_URL);
  await waitForBootstrap(mobile);
  await capture(mobile, "mobile-welcome");

  await mobile.getByRole("button", { name: /open sidebar/i }).click();
  await mobile.waitForTimeout(400);
  await capture(mobile, "mobile-sidebar-open");
  await mobile.keyboard.press("Escape");

  await mobile.getByTestId("composer-textarea").fill("Mobile UI test message");
  await mobile.getByTestId("composer-send").click();
  await mobile.waitForTimeout(5000);
  await capture(mobile, "mobile-chat");

  await mobile.keyboard.press("Meta+k");
  await mobile.waitForTimeout(400);
  await mobile.getByPlaceholder(/search/i).fill("settings");
  await mobile.keyboard.press("Enter");
  await mobile.waitForTimeout(500);
  await capture(mobile, "mobile-settings-dialog");

  await browser.close();
  console.log(`\nScreenshots in ${OUT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
