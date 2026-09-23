// UI audit harness — capture + measurement, no assertions about the product.
//
// Run: `pnpm audit:ui` (builds the FE for production, boots BE + `next start`,
// runs this file, aggregates). `pnpm audit:ui:nobuild` reuses an existing
// audit build. Filter with `AUDIT_ONLY=m390,d1440` (viewport ids) and
// `AUDIT_THEMES=light`.
//
// One test per viewport × theme walks the app like a user through every
// surface in the brief: welcome, model picker, command palette, sidebar /
// drawer, account menu, auth dialog, every settings tab, a multi-turn thread
// (rich markdown incl. a long unbroken URL, code, table, lists; the fake
// provider's code+image and substitution turns), message overflow, share
// dialog, media emulations, mid-stream + stopped, a failed turn, tool /
// web-search / deep-research surfaces, temporary chat, /status, the public
// /share/<token> view, the 404 page and a failed-bootstrap error state.
//
// Every capture writes a PNG under test-results/audit/shots/<vp>/<theme>/ and
// a JSON record under test-results/audit/captures/ holding the probe results
// (probes.ts) plus axe, console errors, failed requests and the PNG's hash.
// global-teardown.ts turns those into probes.json / probes.md.
//
// A surface that cannot be reached is recorded as a capture failure (with a
// diagnostic screenshot) and the walk continues — the report lists them.

import AxeBuilder from "@axe-core/playwright";
import { test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { BE_URL } from "../e2e/shared-config";
import {
  focusBaselines,
  focusSnapshot,
  installClsObserver,
  pageProbe,
} from "./probes";

const AUDIT_DIR = path.resolve(__dirname, "..", "..", "test-results", "audit");

interface Viewport {
  id: string;
  width: number;
  height: number;
  touch: boolean;
  dsf: number;
  /** Media-emulation variants + focus walks run on these only. */
  primary: boolean;
}

const VIEWPORTS: Viewport[] = [
  { id: "d1440", width: 1440, height: 900, touch: false, dsf: 1, primary: true },
  { id: "d1024", width: 1024, height: 768, touch: false, dsf: 1, primary: false },
  { id: "t820", width: 820, height: 1180, touch: true, dsf: 1, primary: false },
  { id: "m390", width: 390, height: 844, touch: true, dsf: 2, primary: true },
  { id: "m320", width: 320, height: 640, touch: true, dsf: 2, primary: false },
];
const THEMES = ["light", "dark"] as const;
type Theme = (typeof THEMES)[number];

const ONLY = (process.env.AUDIT_ONLY ?? "").split(",").filter(Boolean);
const ONLY_THEMES = (process.env.AUDIT_THEMES ?? "").split(",").filter(Boolean);

const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

// ── Rich-markdown fixture ────────────────────────────────────────────────
// The fake provider's templates carry no table, list or long URL, so the
// harness rewrites the answer of one turn in flight: the real BE stream is
// fetched (so the turn is persisted and the conversation stays valid) and its
// answer_delta frames are replaced with this body before the terminal frame.
const LONG_URL =
  "https://example.com/really/long/path/" + "segment".repeat(18) + "?token=" + "x".repeat(60);
const RICH_ANSWER = [
  "## Rich markdown fixture",
  "",
  "A paragraph with `inline code`, **bold**, _emphasis_ and a [short link](https://example.com).",
  "",
  `An unbroken URL: ${LONG_URL}`,
  "",
  "- First bullet with a fairly long sentence that should wrap cleanly on a phone",
  "- Second bullet",
  "  - Nested bullet",
  "1. Ordered one",
  "2. Ordered two",
  "",
  "| Region | Latency p50 | Latency p95 | Error rate | Notes | Owner |",
  "| --- | --- | --- | --- | --- | --- |",
  "| ap-southeast-1 | 120 ms | 480 ms | 0.02% | Primary database region, warm | platform |",
  "| us-east-1 | 210 ms | 900 ms | 0.10% | Cross-region reads only | infra |",
  "| eu-west-1 | 260 ms | 1100 ms | 0.31% | Degraded during deploy windows | infra |",
  "",
  "```typescript",
  "export function formatLatency(ms: number): string { return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`; } // deliberately long single line to force horizontal scroll",
  "```",
  "",
  "> A blockquote that closes the fixture.",
].join("\n");
const RICH_PROMPT = `AUDIT_RICH: Summarise the latency table and include this link without shortening it ${LONG_URL} — plus a list and a code sample.`;

// ── Capture machinery ────────────────────────────────────────────────────

interface CaptureRecord {
  name: string;
  viewport: string;
  theme: Theme;
  media: string;
  surface: string;
  file: string | null;
  md5: string | null;
  ok: boolean;
  error?: string;
  probe?: unknown;
  axe?: unknown;
  consoleErrors: string[];
  failedRequests: string[];
  cls?: unknown;
  focus?: unknown;
  extra?: Record<string, unknown>;
}

class Auditor {
  consoleErrors: string[] = [];
  failedRequests: string[] = [];
  media = "base";

  constructor(
    readonly page: Page,
    readonly vp: Viewport,
    readonly theme: Theme,
  ) {
    page.on("console", (m) => {
      if (m.type() === "error") this.consoleErrors.push(m.text().slice(0, 300));
    });
    page.on("pageerror", (e) => this.consoleErrors.push(`pageerror: ${e.message.slice(0, 300)}`));
    page.on("requestfailed", (r) => {
      const why = r.failure()?.errorText ?? "failed";
      // Aborted-by-client (stop, navigation) is noise, not a defect.
      if (/ERR_ABORTED/.test(why)) return;
      this.failedRequests.push(`${r.method()} ${r.url()} — ${why}`);
    });
    page.on("response", (r) => {
      if (r.status() >= 400) this.failedRequests.push(`${r.request().method()} ${r.url()} — HTTP ${r.status()}`);
    });
  }

  get floor(): number {
    return this.vp.touch ? 44 : 24;
  }

  shotPath(surface: string): string {
    const media = this.media === "base" ? "" : `__${this.media}`;
    return path.join(AUDIT_DIR, "shots", this.vp.id, this.theme, `${surface}${media}.png`);
  }

  async settle(): Promise<void> {
    await this.page.evaluate(() => document.fonts.ready.then(() => undefined)).catch(() => {});
    await this.page.waitForTimeout(350);
    await this.page
      .evaluate(
        () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))),
      )
      .catch(() => {});
  }

  /**
   * Screenshot + probes for one surface. `ready` must resolve once the
   * intended surface is visibly rendered — a shot of a spinner is a failure.
   */
  async capture(
    surface: string,
    opts: {
      ready?: () => Promise<unknown>;
      axe?: boolean;
      probes?: boolean;
      fullPage?: boolean;
      extra?: Record<string, unknown>;
    } = {},
  ): Promise<CaptureRecord> {
    const name = `${this.vp.id}__${this.theme}__${surface}${this.media === "base" ? "" : `__${this.media}`}`;
    const file = this.shotPath(surface);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const rec: CaptureRecord = {
      name,
      viewport: this.vp.id,
      theme: this.theme,
      media: this.media,
      surface,
      file: path.relative(AUDIT_DIR, file),
      md5: null,
      ok: true,
      consoleErrors: [],
      failedRequests: [],
      extra: opts.extra,
    };
    try {
      if (opts.ready) await opts.ready();
      await this.settle();
    } catch (e) {
      rec.ok = false;
      rec.error = `not ready: ${(e as Error).message.split("\n")[0]}`;
    }
    try {
      const buf = await this.page.screenshot({
        path: rec.ok ? file : file.replace(/\.png$/, "__FAILED.png"),
        fullPage: opts.fullPage ?? false,
        animations: "disabled",
        caret: "hide",
      });
      rec.md5 = crypto.createHash("md5").update(buf).digest("hex");
      if (!rec.ok) rec.file = path.relative(AUDIT_DIR, file.replace(/\.png$/, "__FAILED.png"));
    } catch (e) {
      rec.ok = false;
      rec.file = null;
      rec.error = `${rec.error ?? ""} screenshot: ${(e as Error).message.split("\n")[0]}`;
    }
    if (rec.ok && opts.probes !== false) {
      try {
        rec.probe = await this.page.evaluate(pageProbe, {
          touch: this.vp.touch,
          targetFloor: this.floor,
        });
      } catch (e) {
        rec.extra = { ...rec.extra, probeError: (e as Error).message.split("\n")[0] };
      }
      if (opts.axe !== false && this.media === "base") {
        try {
          const res = await new AxeBuilder({ page: this.page }).withTags(AXE_TAGS).analyze();
          rec.axe = res.violations.map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            tags: v.tags.filter((t) => t.startsWith("wcag")),
            nodes: v.nodes.length,
            targets: v.nodes.slice(0, 6).map((n) => ({
              target: n.target.join(" "),
              summary: (n.failureSummary ?? "").replace(/\s+/g, " ").slice(0, 220),
            })),
          }));
        } catch (e) {
          rec.extra = { ...rec.extra, axeError: (e as Error).message.split("\n")[0] };
        }
      }
    }
    rec.consoleErrors = this.consoleErrors.splice(0);
    rec.failedRequests = this.failedRequests.splice(0);
    this.write(rec);
    return rec;
  }

  /** Record a surface that could not be reached at all. */
  async fail(surface: string, err: unknown): Promise<void> {
    await this.capture(surface, {
      ready: async () => {
        throw err instanceof Error ? err : new Error(String(err));
      },
      probes: false,
    });
  }

  write(rec: CaptureRecord): void {
    const out = path.join(AUDIT_DIR, "captures", `${rec.name}.json`);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, JSON.stringify(rec, null, 2));
  }

  /** Run `fn`; on throw, record the surface as unreachable and continue. */
  async attempt(surface: string, fn: () => Promise<void>): Promise<void> {
    try {
      await fn();
    } catch (e) {
      await this.fail(surface, e);
    } finally {
      await dismissAll(this.page);
    }
  }
}

// Touch viewports must activate controls with touch events. A synthesized
// mouse click inside a bottom sheet is swallowed by the sheet's swipe-dismiss
// pointer capture (see FINDINGS-RAW.md), so on touch contexts the walk taps,
// as a phone user would. Set per test; tests in one worker run sequentially.
let currentTouch = false;
async function press(loc: Locator): Promise<void> {
  if (currentTouch) await loc.tap();
  else await loc.click();
}

async function dismissAll(page: Page): Promise<void> {
  for (let i = 0; i < 3; i++) {
    const open = await page
      .locator('[role="dialog"]:visible, [role="menu"]:visible, [role="listbox"]:visible')
      .count()
      .catch(() => 0);
    if (!open) return;
    await page.keyboard.press("Escape").catch(() => {});
    await page.waitForTimeout(250);
  }
}

async function waitForShell(page: Page): Promise<void> {
  await page.getByTestId("composer-textarea").waitFor({ state: "visible", timeout: 20_000 });
}

async function visibleFirst(...locs: Locator[]): Promise<Locator> {
  for (const l of locs) {
    const v = l.locator("visible=true").first();
    if (await v.count()) return v;
  }
  throw new Error("none of the candidate controls is visible");
}

async function openDrawerIfMobile(page: Page): Promise<boolean> {
  // The desktop sidebar exposes its controls directly; below md the header's
  // "Open sidebar" opens the Navigation drawer.
  const accountVisible = await page.getByRole("button", { name: "Account menu" }).isVisible();
  if (accountVisible) return false;
  const opener = await visibleFirst(page.getByRole("button", { name: "Open sidebar" }));
  await press(opener);
  await page.getByRole("dialog", { name: "Navigation" }).waitFor({ state: "visible" });
  return true;
}

async function sendAndSettle(page: Page, prompt: string, status = "done"): Promise<Locator> {
  const before = await page.getByTestId("assistant-message").count();
  await page.getByTestId("composer-textarea").fill(prompt);
  await press(page.getByTestId("composer-send"));
  const msg = page.getByTestId("assistant-message").nth(before);
  await msg.waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForFunction(
    ([idx, st]) => {
      const el = document.querySelectorAll('[data-testid="assistant-message"]')[idx as number];
      return !!el && el.getAttribute("data-status") === st;
    },
    [before, status] as const,
    { timeout: 25_000 },
  );
  return msg;
}

async function resetCls(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __auditCls?: { value: number; entries: unknown[] } };
    if (w.__auditCls) {
      w.__auditCls.value = 0;
      w.__auditCls.entries = [];
    }
  });
}

async function readCls(page: Page): Promise<unknown> {
  return page.evaluate(() => (window as unknown as { __auditCls?: unknown }).__auditCls ?? null);
}

async function focusWalk(a: Auditor, surface: string, steps = 25, crops = false): Promise<unknown> {
  const page = a.page;
  await page.evaluate(() => {
    (window as unknown as { __auditFocused: Element[] }).__auditFocused = [];
    (document.activeElement as HTMLElement | null)?.blur?.();
  });
  // Start from the top of the document so the order is the real tab order.
  await page.mouse.click(1, Math.max(1, a.vp.height - 2)).catch(() => {});
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.());
  const snaps: unknown[] = [];
  for (let i = 0; i < steps; i++) {
    await page.keyboard.press("Tab");
    await page.waitForTimeout(60);
    const s = (await page.evaluate(focusSnapshot)) as
      | { rect: { x: number; y: number; w: number; h: number } }
      | null;
    snaps.push(s);
    if (crops && s && s.rect.w > 0 && s.rect.h > 0) {
      const pad = 10;
      const clip = {
        x: Math.max(0, s.rect.x - pad),
        y: Math.max(0, s.rect.y - pad),
        width: Math.min(a.vp.width, s.rect.w + pad * 2),
        height: Math.min(a.vp.height, s.rect.h + pad * 2),
      };
      if (clip.x + clip.width > a.vp.width) clip.width = a.vp.width - clip.x;
      if (clip.y + clip.height > a.vp.height) clip.height = a.vp.height - clip.y;
      if (clip.width > 2 && clip.height > 2) {
        const f = path.join(AUDIT_DIR, "focus", `${a.vp.id}__${a.theme}`, `${surface}-${String(i).padStart(2, "0")}.png`);
        fs.mkdirSync(path.dirname(f), { recursive: true });
        await page.screenshot({ path: f, clip, animations: "disabled" }).catch(() => {});
      }
    }
    // A Tab that opened something (it should not) — close it and move on.
  }
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.());
  await page.waitForTimeout(150);
  const base = (await page.evaluate(focusBaselines)) as Array<Array<Record<string, string>>>;
  return snaps.map((s, i) => {
    if (!s) return null;
    const snap = s as { index: number; focused: Array<Record<string, string>> };
    const rest = base[snap.index] ?? [];
    const changed: string[] = [];
    snap.focused.forEach((f, depth) => {
      const r = rest[depth];
      if (!r) return;
      for (const k of Object.keys(f)) {
        if (f[k] !== r[k]) changed.push(`${depth === 0 ? "self" : `ancestor${depth}`}.${k}`);
      }
    });
    const strong = changed.some((c) => /outline|boxShadow|borderColor|textDecoration/.test(c));
    return {
      step: i + 1,
      ...(s as object),
      focused: undefined,
      changed,
      indicator: strong ? "visible" : changed.length ? "weak(background-only)" : "NONE",
    };
  });
}

// ── The walk ─────────────────────────────────────────────────────────────

async function newAuditContext(
  browser: import("@playwright/test").Browser,
  vp: Viewport,
  theme: Theme,
  extra: Partial<import("@playwright/test").BrowserContextOptions> = {},
): Promise<BrowserContext> {
  const ctx = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: vp.dsf,
    hasTouch: vp.touch,
    isMobile: vp.touch && vp.width < 768,
    colorScheme: theme,
    serviceWorkers: "block",
    ...extra,
  });
  await ctx.addInitScript((t) => {
    try {
      window.localStorage.setItem("theme", t);
    } catch {
      /* storage blocked */
    }
  }, theme);
  await ctx.addInitScript(installClsObserver);
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});
  return ctx;
}

for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    if (ONLY.length && !ONLY.includes(vp.id)) continue;
    if (ONLY_THEMES.length && !ONLY_THEMES.includes(theme)) continue;

    test(`audit ${vp.id} ${theme}`, async ({ browser }) => {
      const ctx = await newAuditContext(browser, vp, theme);
      const page = await ctx.newPage();
      const a = new Auditor(page, vp, theme);
      const primary = vp.primary;
      currentTouch = vp.touch;

      // 1. Welcome ------------------------------------------------------------
      await page.goto("/");
      await waitForShell(page);
      const loadCls = await (async () => {
        await page.waitForTimeout(1200);
        return readCls(page);
      })();
      await a.capture("welcome", {
        ready: () => page.getByTestId("ai-interaction-disclosure").waitFor({ state: "visible" }),
        extra: { loadCls },
      });
      if (primary) {
        await a.attempt("welcome-focus", async () => {
          const walk = await focusWalk(a, "welcome", 25, theme === "light");
          const rec = await a.capture("welcome-focus-end", { probes: false });
          rec.focus = walk;
          a.write(rec);
        });
        await page.goto("/");
        await waitForShell(page);
        for (const m of mediaVariants(vp)) {
          await a.attempt(`welcome__${m.id}`, async () => {
            await m.apply(page, vp);
            a.media = m.id;
            await a.capture("welcome", {
              ready: () => waitForShell(page),
              probes: m.id !== "print",
              axe: false,
            });
          });
          a.media = "base";
          await m.reset(page, vp);
        }
      }

      // 2. Model picker -------------------------------------------------------
      await a.attempt("model-picker", async () => {
        await press(page.locator('[data-testid="model-mode-trigger"]:visible').first());
        await a.capture("model-picker", {
          ready: () =>
            page.locator('[role="menu"]:visible, [role="dialog"]:visible').first().waitFor({ state: "visible" }),
        });
        const adv = page.locator('[data-testid="picker-advanced"]:visible').first();
        if (await adv.count()) {
          await press(adv);
          await a.capture("model-picker-advanced", {
            ready: () => page.locator('[data-testid="web-search-toggle"]:visible').first().waitFor(),
          });
        }
      });

      // 3. Command palette ----------------------------------------------------
      await a.attempt("command-palette", async () => {
        await page.locator("body").click({ position: { x: 5, y: 5 } }).catch(() => {});
        await page.keyboard.press("ControlOrMeta+k");
        await a.capture("command-palette", {
          ready: () => page.getByRole("dialog").locator("input").first().waitFor({ state: "visible" }),
        });
      });

      // 4. Sidebar / drawer ---------------------------------------------------
      await a.attempt("sidebar", async () => {
        const drawer = await openDrawerIfMobile(page);
        await a.capture(drawer ? "drawer" : "sidebar", {
          ready: () =>
            (drawer
              ? page.getByRole("dialog", { name: "Navigation" })
              : page.getByRole("button", { name: "Account menu" })
            ).waitFor({ state: "visible" }),
        });
      });

      // 5. Account menu + auth dialog ----------------------------------------
      await a.attempt("account-menu", async () => {
        await openDrawerIfMobile(page);
        await press(page.getByRole("button", { name: "Account menu" }));
        await a.capture("account-menu", {
          ready: () => page.getByRole("menuitem", { name: "Settings" }).waitFor(),
        });
        await press(page.getByRole("menuitem", { name: "Sign in" }));
        await a.capture("auth-signin", {
          ready: () => page.getByRole("heading", { name: "Sign in" }).waitFor(),
        });
        const toSignup = page.getByRole("button", { name: "Create an account" });
        if (await toSignup.count()) {
          await press(toSignup);
          await a.capture("auth-signup", {
            ready: () => page.getByRole("heading", { name: "Create account" }).waitFor(),
          });
        }
      });

      // 6. Settings, every tab -----------------------------------------------
      await a.attempt("settings", async () => {
        await openDrawerIfMobile(page);
        await press(page.getByRole("button", { name: "Account menu" }));
        await press(page.getByRole("menuitem", { name: "Settings" }));
        const dialog = page.getByRole("dialog", { name: "Settings" });
        await dialog.waitFor({ state: "visible" });
        const tabs = ["General", "Activity", "Memory", "Templates", "Models", "Shortcuts"];
        const isList = (await dialog.getByRole("tab").count()) === 0;
        if (isList) {
          await a.capture("settings-list", { ready: () => dialog.getByText("General").first().waitFor() });
        }
        for (const label of tabs) {
          const slug = `settings-${label.toLowerCase()}`;
          try {
            if (isList) {
              const back = dialog.getByTestId("settings-back-button");
              if (await back.isVisible().catch(() => false)) await press(back);
              await press(dialog.getByRole("button", { name: label, exact: true }));
            } else {
              await press(dialog.getByRole("tab", { name: label }));
            }
            await a.capture(slug, {
              ready: async () => {
                await page.waitForTimeout(300);
                await dialog.locator('[role="tabpanel"], [data-testid$="-panel"]').first().waitFor({ state: "visible" }).catch(async () => {
                  // Panels without a tabpanel role — require non-trivial text.
                  const t = await dialog.innerText();
                  if (t.trim().length < 40) throw new Error(`settings tab ${label} rendered empty`);
                });
              },
            });
          } catch (e) {
            await a.fail(slug, e);
          }
        }
        if (primary) {
          // Forced colors on the dialog (UI-PREF-1 names dialog boundaries).
          await page.emulateMedia({ forcedColors: "active" });
          a.media = "forced-colors";
          await a.capture("settings-shortcuts", { probes: false });
          a.media = "base";
          await page.emulateMedia({ forcedColors: "none" });
        }
      });

      // 7. Build the thread ---------------------------------------------------
      let conversationId: string | null = null;
      page.on("request", (req) => {
        const m = req.url().match(/\/api\/conversations\/([0-9a-fA-F-]{36})\/messages/);
        if (m && !conversationId) conversationId = m[1]!;
      });
      let streamCls: unknown = null;
      await a.attempt("thread-build", async () => {
        await page.goto("/");
        await waitForShell(page);
        await resetCls(page);
        await sendAndSettle(page, "Give me a short overview of how the service handles a request.");
        streamCls = await readCls(page);

        await page.route(`${BE_URL}/api/conversations/*/messages`, async (route) => {
          const req = route.request();
          if (req.method() !== "POST" || !(req.postData() ?? "").includes("AUDIT_RICH")) {
            await route.fallback();
            return;
          }
          const resp = await route.fetch();
          // sse-starlette terminates lines with CRLF; normalise before
          // splitting into frames.
          const body = (await resp.text()).replace(/\r\n/g, "\n");
          const frames = body.split(/\n\n/);
          const kept = frames.filter((f) => !/^event: answer_delta/m.test(f));
          const idx = kept.findIndex((f) => /^event: terminal/m.test(f));
          const rich = `event: answer_delta\ndata: ${JSON.stringify({ text: RICH_ANSWER })}`;
          if (idx >= 0) kept.splice(idx, 0, rich);
          else kept.push(rich);
          await route.fulfill({ response: resp, body: kept.join("\n\n") });
        });
        await sendAndSettle(page, RICH_PROMPT);
        await page.unroute(`${BE_URL}/api/conversations/*/messages`);
        await sendAndSettle(page, "RICH_MARKDOWN: show a snippet and an image");
        await sendAndSettle(page, "FORCE_FALLBACK: answer from whichever route is up");
      });

      // 8. Thread surfaces ----------------------------------------------------
      await a.attempt("thread", async () => {
        await a.capture("thread", {
          ready: () => page.getByTestId("message-attribution").last().waitFor({ state: "visible" }),
          extra: { streamCls },
        });
        const idleAnims = await page.evaluate(() =>
          document.getAnimations().filter((x) => x.playState === "running").length,
        );
        // Scroll-positioned shots of the rich turn. A position already
        // captured (short thread / tall viewport) is skipped rather than
        // written as a duplicate frame.
        const scroller = page.locator(".chat-scroll");
        const seen = new Set<number>([Math.round(await scroller.evaluate((el) => el.scrollTop))]);
        const richMsg = page.getByTestId("assistant-message").nth(1);
        const spots: Array<[string, Locator]> = [
          ["thread-user-long-url", page.getByTestId("user-message-text").nth(1)],
          ["thread-rich-table", richMsg.locator("table").first()],
          ["thread-rich-code", richMsg.locator("pre").first()],
        ];
        const skipped: string[] = [];
        for (const [name, loc] of spots) {
          await loc.evaluate((el) => el.scrollIntoView({ block: "start" }));
          await page.waitForTimeout(150);
          const top = Math.round(await scroller.evaluate((el) => el.scrollTop));
          if (seen.has(top)) {
            skipped.push(name);
            continue;
          }
          seen.add(top);
          await a.capture(name, {
            ready: () => loc.waitFor({ state: "visible" }),
            extra: { idleRunningAnimations: idleAnims, skippedAsDuplicatePosition: skipped.slice() },
          });
        }
        await page.locator(".chat-scroll").evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
      });
      if (primary) {
        await a.attempt("thread-focus", async () => {
          const walk = await focusWalk(a, "thread", 25, theme === "light");
          const rec = await a.capture("thread-focus-end", { probes: false });
          rec.focus = walk;
          a.write(rec);
        });
      }

      await a.attempt("message-overflow", async () => {
        await page.locator(".chat-scroll").evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
        const last = page.getByTestId("assistant-message").last();
        await last.hover().catch(() => {});
        await press(last.getByTestId("message-actions-overflow"));
        await a.capture("message-overflow", {
          ready: () => page.getByRole("menu").first().waitFor({ state: "visible" }),
        });
      });

      await a.attempt("share-dialog", async () => {
        await press(await visibleFirst(page.getByRole("button", { name: "Chat menu" })));
        await a.capture("chat-menu", { ready: () => page.getByRole("menuitem", { name: "Share chat" }).waitFor() });
        await press(page.getByRole("menuitem", { name: "Share chat" }));
        await a.capture("share-dialog", {
          ready: () => page.getByRole("heading", { name: "Share chat" }).waitFor(),
        });
        await press(page.getByRole("button", { name: "Create share link" }));
        await a.capture("share-dialog-link", {
          ready: () => page.getByRole("textbox", { name: "Public share link" }).waitFor(),
        });
      });

      if (vp.touch && vp.width < 768) {
        await a.attempt("drawer-thread", async () => {
          await openDrawerIfMobile(page);
          await a.capture("drawer-thread", {
            ready: () => page.locator("[data-conversation-id]:visible").first().waitFor({ state: "visible" }),
          });
        });
      }

      // 9. Media emulation on the thread -------------------------------------
      if (primary) {
        for (const m of mediaVariants(vp)) {
          await a.attempt(`thread__${m.id}`, async () => {
            await m.apply(page, vp);
            a.media = m.id;
            await page.locator(".chat-scroll").evaluate((el) => el.scrollTo({ top: el.scrollHeight })).catch(() => {});
            await a.capture("thread", {
              ready: () => page.getByTestId("assistant-message").last().waitFor({ state: "visible" }),
              probes: m.id !== "print",
              fullPage: m.id === "print",
            });
            if (m.id === "print") {
              const pdf = path.join(AUDIT_DIR, "pdf", `${vp.id}__${theme}__thread.pdf`);
              fs.mkdirSync(path.dirname(pdf), { recursive: true });
              const buf = await page.pdf({ path: pdf, printBackground: true });
              const pages = (buf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) ?? []).length;
              const rec = await a.capture("thread-print-pdf-meta", { probes: false });
              rec.extra = { pdf: path.relative(AUDIT_DIR, pdf), pdfPages: pages, pdfBytes: buf.length };
              a.write(rec);
            }
          });
          a.media = "base";
          await m.reset(page, vp);
        }
      }

      // 10. Streaming states --------------------------------------------------
      await a.attempt("turn-error", async () => {
        await sendAndSettle(page, "FORCE_ERROR: fail this turn", "error");
        await a.capture("turn-error", {
          ready: () => page.getByTestId("assistant-message").last().getByRole("button", { name: /retry/i }).first().waitFor(),
        });
      });

      await a.attempt("mid-stream", async () => {
        await page.locator(".chat-scroll").evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
        await resetCls(page);
        await page.getByTestId("composer-textarea").fill("SLOW: stream a long answer slowly");
        await press(page.getByTestId("composer-send"));
        const stop = page.getByRole("button", { name: "Stop generating" });
        await stop.waitFor({ state: "visible", timeout: 10_000 });
        await page.waitForFunction(
          () => {
            const msgs = document.querySelectorAll('[data-testid="assistant-message"]');
            const last = msgs[msgs.length - 1];
            return !!last && /part \d+ part \d+ part \d+/.test(last.textContent ?? "");
          },
          undefined,
          { timeout: 10_000 },
        );
        const midAnims = await page.evaluate(() =>
          document
            .getAnimations()
            .filter((x) => x.playState === "running")
            .map((x) => ({
              name: (x as CSSAnimation).animationName || (x as CSSTransition).transitionProperty || "anim",
              infinite: x.effect?.getComputedTiming().iterations === Infinity,
              inThread: !!((x.effect as KeyframeEffect | null)?.target as Element | null)?.closest?.(".chat-scroll"),
            })),
        );
        // No settle wait here: the stream is ~2 s end to end.
        const buf = await page.screenshot({ path: a.shotPath("mid-stream"), animations: "disabled" });
        const rec: CaptureRecord = {
          name: `${vp.id}__${theme}__mid-stream`,
          viewport: vp.id,
          theme,
          media: "base",
          surface: "mid-stream",
          file: path.relative(AUDIT_DIR, a.shotPath("mid-stream")),
          md5: crypto.createHash("md5").update(buf).digest("hex"),
          ok: true,
          consoleErrors: [],
          failedRequests: [],
          extra: { runningAnimations: midAnims },
        };
        rec.probe = await page.evaluate(pageProbe, { touch: vp.touch, targetFloor: a.floor });
        a.write(rec);
        await press(stop);
        const last = page.getByTestId("assistant-message").last();
        await a.capture("stopped", {
          ready: () =>
            page.waitForFunction(() => {
              const msgs = document.querySelectorAll('[data-testid="assistant-message"]');
              return msgs[msgs.length - 1]?.getAttribute("data-status") === "stopped";
            }),
          extra: { streamCls: await readCls(page), lastStatus: await last.getAttribute("data-status") },
        });
      });

      // A send shortly after Stop. Recorded because the BE answered 409
      // STREAM_IN_PROGRESS here during harness development (FINDINGS-RAW.md);
      // the capture shows whatever the product does with the draft.
      await a.attempt("send-after-stop", async () => {
        await page.waitForTimeout(3000);
        await page.getByTestId("composer-textarea").fill("A follow-up sent after stopping");
        const resp = page.waitForResponse(
          (r) => /\/api\/conversations\/[^/]+\/messages$/.test(r.url()) && r.request().method() === "POST",
          { timeout: 10_000 },
        );
        await press(page.getByTestId("composer-send"));
        const status = (await resp).status();
        await page.waitForTimeout(800);
        await a.capture("send-after-stop", {
          extra: {
            messagesPostStatus: status,
            draftAfter: await page.getByTestId("composer-textarea").inputValue(),
            followUpBubbleShown: (await page.getByTestId("user-message-text").allTextContents()).some((t) =>
              t.includes("A follow-up sent after stopping"),
            ),
          },
        });
      });

      // 11. Tool / agentic surfaces ------------------------------------------
      await a.attempt("tool-approval", async () => {
        await page.goto("/");
        await waitForShell(page);
        await sendAndSettle(page, "TOOL_APPROVE: book a meeting for tomorrow", "awaiting_approval");
        await a.capture("tool-approval", {
          ready: () => page.getByTestId("tool-approve").last().waitFor({ state: "visible" }),
        });
        await press(page.getByTestId("tool-approve").last());
        await page.waitForFunction(() => {
          const msgs = document.querySelectorAll('[data-testid="assistant-message"]');
          return msgs[msgs.length - 1]?.getAttribute("data-status") === "done";
        }, undefined, { timeout: 20_000 });
        await a.capture("tool-approved", {
          ready: () => page.getByTestId("tool-call-part").last().waitFor({ state: "visible" }),
        });
      });

      await a.attempt("web-search", async () => {
        await page.goto("/");
        await waitForShell(page);
        await press(page.locator('[data-testid="model-mode-trigger"]:visible').first());
        await press(page.locator('[data-testid="picker-advanced"]:visible').first());
        await press(page.locator('[data-testid="web-search-toggle"]:visible').first());
        await dismissAll(page);
        await sendAndSettle(page, "What is the latest on Playwright releases?");
        await a.capture("web-search", {
          ready: () => page.getByTestId("web-search-panel").last().waitFor({ state: "visible" }),
        });
        const trig = page.getByTestId("web-search-trigger").last();
        if (await trig.count()) {
          await press(trig);
          await a.capture("web-search-expanded", { ready: () => page.waitForTimeout(300) });
        }
      });

      await a.attempt("deep-research-plan", async () => {
        await page.goto("/");
        await waitForShell(page);
        await press(page.locator('[data-testid="model-mode-trigger"]:visible').first());
        await press(page.locator('[data-testid="deep-research-toggle"]:visible').first());
        await dismissAll(page);
        await sendAndSettle(page, "DEEP_RESEARCH: alpha topic | beta topic", "awaiting_approval");
        await a.capture("deep-research-plan", {
          ready: () => page.getByTestId("plan-approval-detail").last().waitFor({ state: "visible" }),
        });
        await press(page.getByTestId("tool-approve").last());
        await page.waitForFunction(() => {
          const msgs = document.querySelectorAll('[data-testid="assistant-message"]');
          const s = msgs[msgs.length - 1]?.getAttribute("data-status");
          return s === "done" || s === "error";
        }, undefined, { timeout: 45_000 });
        await a.capture("deep-research-done", {
          ready: () => page.getByTestId("assistant-message").last().getByTestId("assistant-answer").waitFor({ state: "visible" }),
        });
      });

      await a.attempt("temporary-chat", async () => {
        await page.goto("/");
        await waitForShell(page);
        await press(await visibleFirst(page.getByRole("button", { name: "Chat menu" })));
        await press(page.getByRole("menuitemcheckbox", { name: "Temporary chat" }));
        await a.capture("temporary-chat", {
          ready: () => page.getByTestId("temporary-chat-banner").waitFor({ state: "visible" }),
        });
      });

      // 12. Standalone routes -------------------------------------------------
      await a.attempt("status-page", async () => {
        await page.goto("/status");
        await a.capture("status-page", {
          ready: () => page.getByRole("heading").first().waitFor({ state: "visible" }),
        });
      });

      await a.attempt("share-view", async () => {
        if (!conversationId) throw new Error("no conversation id captured from the thread build");
        const res = await page.request.post(`${BE_URL}/api/conversations/${conversationId}/share`);
        if (!res.ok()) throw new Error(`share mint HTTP ${res.status()}`);
        const { sharePath } = (await res.json()) as { sharePath: string };
        // Public view is viewed by a stranger: fresh context, no cookie.
        const pub = await newAuditContext(browser, vp, theme);
        const pp = await pub.newPage();
        const pa = new Auditor(pp, vp, theme);
        await pp.goto(sharePath);
        await pa.capture("share-view", {
          ready: () => pp.getByTestId("public-conversation-title").waitFor({ state: "visible", timeout: 20_000 }),
          extra: { sharePath },
        });
        // Full-page capture of the public transcript (the rich turn, the
        // code/image turn and the substitution callout).
        await pa.capture("share-view-full", {
          ready: () => pp.getByTestId("public-assistant-message").nth(2).waitFor({ state: "attached" }),
          fullPage: true,
        });
        await pub.close();
      });

      await a.attempt("not-found", async () => {
        await page.goto("/this-route-does-not-exist");
        await a.capture("not-found", {
          ready: () => page.getByText(/not found|404|doesn.t exist/i).first().waitFor({ state: "visible" }),
        });
      });

      await a.attempt("bootstrap-error", async () => {
        await page.route(`${BE_URL}/api/bootstrap`, (r) =>
          r.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({
              error: { code: "UPSTREAM_UNAVAILABLE", severity: "error", title: "Service unavailable", body: "The service is temporarily unavailable." },
            }),
          }),
        );
        await page.goto("/");
        await a.capture("bootstrap-error", {
          ready: () => page.getByRole("button", { name: /try again/i }).waitFor({ state: "visible", timeout: 20_000 }),
        });
        await page.unroute(`${BE_URL}/api/bootstrap`);
      });

      await a.attempt("bootstrap-offline", async () => {
        await page.route(`${BE_URL}/api/bootstrap`, (r) => r.abort("connectionrefused"));
        await page.goto("/");
        await a.capture("bootstrap-offline", {
          ready: () => page.getByRole("button", { name: /try again/i }).waitFor({ state: "visible", timeout: 20_000 }),
        });
        await page.unroute(`${BE_URL}/api/bootstrap`);
      });

      await ctx.close();
    });
  }
}

// ── Pointer click inside a bottom sheet ──────────────────────────────────
// Below `md` the dialogs render as swipe-dismissable bottom sheets. During
// harness development a synthesized MOUSE click on a row inside the Settings
// sheet did nothing while a TAP worked (FINDINGS-RAW.md). This probe re-checks
// it on a narrow pointer (no touch) window, the case a desktop user hits by
// resizing the browser, and records the outcome instead of asserting it.
if (!ONLY.length || ONLY.includes("p600")) {
  test("audit p600 sheet mouse click", async ({ browser }) => {
    const vp: Viewport = { id: "p600", width: 600, height: 800, touch: false, dsf: 1, primary: false };
    const ctx = await newAuditContext(browser, vp, "light");
    const page = await ctx.newPage();
    const a = new Auditor(page, vp, "light");
    currentTouch = false;
    await page.goto("/");
    await waitForShell(page);
    await a.attempt("sheet-mouse-click", async () => {
      await openDrawerIfMobile(page);
      await page.getByRole("button", { name: "Account menu" }).click();
      await page.getByRole("menuitem", { name: "Settings" }).click();
      const dialog = page.getByRole("dialog", { name: "Settings" });
      await dialog.waitFor({ state: "visible" });
      await page.waitForTimeout(600);
      await dialog.getByRole("button", { name: "General", exact: true }).click();
      await page.waitForTimeout(800);
      const navigated = await dialog.getByTestId("settings-back-button").isVisible().catch(() => false);
      // Keyboard activation of the same row, for comparison.
      let keyboardWorks: boolean | null = null;
      if (!navigated) {
        await dialog.getByRole("button", { name: "General", exact: true }).focus();
        await page.keyboard.press("Enter");
        await page.waitForTimeout(600);
        keyboardWorks = await dialog.getByTestId("settings-back-button").isVisible().catch(() => false);
      }
      await a.capture("sheet-mouse-click", { extra: { mouseClickNavigated: navigated, keyboardWorks } });
    });
    await ctx.close();
  });
}

// ── Media variants ───────────────────────────────────────────────────────

interface MediaVariant {
  id: string;
  apply: (page: Page, vp: Viewport) => Promise<void>;
  reset: (page: Page, vp: Viewport) => Promise<void>;
}

function mediaVariants(vp: Viewport): MediaVariant[] {
  const clear = async (page: Page) => {
    await page.emulateMedia({ reducedMotion: null, forcedColors: null, contrast: null, media: null });
  };
  const variants: MediaVariant[] = [
    { id: "reduced-motion", apply: (p) => p.emulateMedia({ reducedMotion: "reduce" }), reset: clear },
    { id: "forced-colors", apply: (p) => p.emulateMedia({ forcedColors: "active" }), reset: clear },
    { id: "contrast-more", apply: (p) => p.emulateMedia({ contrast: "more" }), reset: clear },
    {
      // 200% zoom equivalent: half the CSS viewport. On a phone the reflow
      // equivalent is already the 320 px viewport, so the phone variant scales
      // the root font instead (WCAG 1.4.4 resize text, UI-TYPE-3).
      id: vp.touch ? "text200" : "zoom200",
      apply: async (p) => {
        if (vp.touch) {
          await p.evaluate(() => {
            document.documentElement.style.fontSize = "200%";
          });
        } else {
          await p.setViewportSize({ width: Math.round(vp.width / 2), height: Math.round(vp.height / 2) });
        }
        await p.waitForTimeout(400);
      },
      reset: async (p) => {
        if (vp.touch) {
          await p.evaluate(() => {
            document.documentElement.style.fontSize = "";
          });
        } else {
          await p.setViewportSize({ width: vp.width, height: vp.height });
        }
        await p.waitForTimeout(300);
      },
    },
    { id: "print", apply: (p) => p.emulateMedia({ media: "print" }), reset: clear },
  ];
  return variants;
}
