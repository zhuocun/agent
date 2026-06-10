# Playwright capture harness

A reusable, framework-agnostic capture script. Copy it, then change only
the four clearly-marked repo-specific blocks: **API base**, **mock
fixtures + routing**, **auth seed**, and the **capture matrix**.

## Why it is shaped this way

- It intercepts every API call and fulfills JSON in-browser — the real
  backend is blocked from the sandbox.
- It captures against a **production build served by a preview server**
  (see `SKILL.md` → Setup). Point `BASE_URL` at the preview port.
- It waits for **real content** before each shot, not a loading spinner.
- It writes shots **outside the repo** (`/tmp/uxsweep/shots`) so nothing
  leaks into `git status`.

## Run

```bash
# 1. driver + browser (does not touch package.json)
npm i playwright --no-save
npx playwright install chromium

# 2. production build + preview on a stable port
npm run build
npx vite preview --port 4173 --host 0.0.0.0 &   # or: npx serve -s dist

# 3. ESM must resolve "playwright" from the script dir
mkdir -p /tmp/uxsweep/shots
ln -sfn "$PWD/node_modules" /tmp/uxsweep/node_modules

# 4. capture, then prove each shot actually rendered
node /tmp/uxsweep/capture.mjs
md5sum /tmp/uxsweep/shots/*.png | sort   # duplicate hash == route never rendered
```

## Skeleton — `/tmp/uxsweep/capture.mjs`

```js
import { chromium } from "playwright";
import path from "node:path";
import fs from "node:fs";

const SHOTS_DIR = "/tmp/uxsweep/shots";
fs.mkdirSync(SHOTS_DIR, { recursive: true });
const BASE_URL = "http://localhost:4173"; // the PREVIEW server, not dev

// ── REPO-SPECIFIC 1/4: API base + mock fixtures ──────────────────────
const API_GLOB = "**/api/v1/**";        // match your app's client base
const API_PREFIX = /^\/api\/v1\//;
const USER = { _id: "u-1", username: "Avery Chen", email: "a@x.dev" };
const fixtures = {
    // Return ARRAYS where the app maps over a collection (a scalar throws
    // `(x ?? []).map is not a function` and trips the error boundary).
    "users/members": [USER, { _id: "u-2", username: "Bao", email: "b@x.dev" }],
    projects: [{ _id: "p-1", projectName: "Demo project" }]
};
const route = (pathname, method) => {
    const p = pathname.replace(API_PREFIX, "");
    if (p === "users" || p === "auth/me") return USER; // identity → authed
    if (p in fixtures) return fixtures[p];
    return method === "GET" ? [] : { ok: true };       // safe defaults
};
// ─────────────────────────────────────────────────────────────────────

const installMocks = async (context, { authed = true } = {}) => {
    await context.route(API_GLOB, async (r, req) => {
        const p = new URL(req.url()).pathname.replace(API_PREFIX, "");
        if (!authed && (p === "users" || p === "auth/me")) {
            return r.fulfill({ status: 401, contentType: "application/json", body: "{}" });
        }
        await r.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(route(new URL(req.url()).pathname, req.method()))
        });
    });
    // stub external fonts/CDNs so cert/latency doesn't stall the page
    await context.route(/https:\/\/(fonts\.|cdn\.|api\.)/, (r) =>
        r.fulfill({ status: 200, contentType: "text/plain", body: "" }));
};

const VIEWPORTS = { iphone13: { width: 390, height: 844 }, desktop: { width: 1280, height: 800 } };
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

// ── REPO-SPECIFIC 2/4: capture matrix ────────────────────────────────
// [slug, urlPath, viewport, scheme, contrast, waitText, authed]
const captures = [
    ["login", "/login", "desktop", "light", "no-preference", "Log in", false],
    ["projects", "/projects", "desktop", "light", "no-preference", "Demo project", true],
    ["projects", "/projects", "desktop", "dark", "no-preference", "Demo project", true],
    ["projects", "/projects", "desktop", "light", "more", "Demo project", true] // prefers-contrast
];
// ─────────────────────────────────────────────────────────────────────

const run = async () => {
    const browser = await chromium.launch({ args: ["--no-sandbox"] });
    for (const [slug, urlPath, vpKey, scheme, contrast, waitText, authed] of captures) {
        const vp = VIEWPORTS[vpKey];
        const isPhone = vp.width < 600;
        const context = await browser.newContext({
            viewport: vp, colorScheme: scheme, deviceScaleFactor: 2,
            hasTouch: isPhone, isMobile: isPhone
        });
        // ── REPO-SPECIFIC 3/4: auth seed (token/session the app checks) ──
        if (authed) await context.addInitScript(() => {
            try { window.sessionStorage.setItem("ai_jwt", "fake.jwt.token"); } catch (e) {}
        });
        // ─────────────────────────────────────────────────────────────────
        await context.addInitScript((s) => {
            try { window.localStorage.setItem("ui:colorScheme", s); } catch (e) {}
        }, scheme);
        await installMocks(context, { authed });
        const page = await context.newPage();
        await page.emulateMedia({ colorScheme: scheme, contrast });

        const errs = [];
        page.on("pageerror", (e) => errs.push(e.message.slice(0, 160)));
        const suffix = contrast === "more" ? "__contrastMore" : "";
        const name = `${slug}__${vpKey}__${scheme}${suffix}`;
        try {
            // Prefer click-through nav for deep/guarded routes; a direct
            // goto is fine for top-level + public pages.
            await page.goto(`${BASE_URL}${urlPath}`, { waitUntil: "domcontentloaded", timeout: 20000 });
            // WAIT FOR CONTENT, not for a spinner to clear.
            await page.waitForFunction(
                (t) => document.body && document.body.innerText.includes(t),
                waitText, { timeout: 15000 }
            ).catch(() => console.log("  waitText MISSED (likely stuck loading):", name));
            await sleep(800);
            await page.screenshot({ path: path.join(SHOTS_DIR, `${name}.png`), fullPage: true, animations: "disabled" });
            console.log("  captured", name, errs.length ? `(pageerror: ${errs[0]})` : "");
        } catch (e) {
            console.error("  FAILED", name, e.message);
        } finally {
            await context.close();
        }
    }
    await browser.close();
    console.log("done.");
};
run().catch((e) => { console.error("fatal", e); process.exit(1); });
```

## Deep / nested / guarded routes

A direct `goto` works for top-level routes. For a nested/guarded route,
render the parent and click in — verified far more reliable than a
deep-link `goto`, which can leave the child stuck in Suspense with only
the app-shell queries fired:

```js
await page.goto(`${BASE_URL}/projects`, { waitUntil: "domcontentloaded" });
await page.waitForFunction(
    (t) => document.body.innerText.includes(t), "Demo project", { timeout: 15000 }
);
await page.getByText("Demo project").first().click();      // navigate like a user
await page.waitForFunction(
    () => document.body.innerText.includes("Backlog"), { timeout: 15000 } // a board column
);
// now screenshot the board
```

## One-shot root-cause probe (step 6)

When a shot is blank/stuck, don't guess from code — ask the page:

```js
const info = await page.evaluate(() => ({
    url: location.href,
    loading: document.body.innerText.toLowerCase().includes("loading"),
    text: document.body.innerText.replace(/\s+/g, " ").slice(0, 300)
}));
// plus: log the set of intercepted API paths and any pageerror/console errors.
// "only identity endpoints fired, the route's queries never did" ⇒ the
// route is stuck in dev lazy-compile or a guard, not a code bug.
```
