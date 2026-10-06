# Playwright capture harness

A reusable, framework-agnostic capture script. Copy it and keep its
structure (mocks, content wait, error capture, verification) unchanged.
Change only the four clearly-marked repo-specific blocks: the **preview
port**, the **API base + mock fixtures and routing**, the **capture matrix
(media + steps per entry)**, and the **auth + theme seed**.

## Why it is shaped this way

- It intercepts every API call and fulfills JSON in-browser — the real
  backend is blocked from the sandbox. Each shot prints its unmatched
  calls on an `UNMOCKED:` line under its `api:` line, and the run ends by
  listing every shot that had one.
- It captures against a **production build served by a preview server**
  (see `SKILL.md` → Setup). Point `BASE_URL` at the preview port.
- It waits for **real content** before each shot, not a loading spinner.
  A shot whose wait missed, or that threw a page error, is saved as
  `<name>__UNRENDERED.png` and listed at the end.
- It records each shot's API hits and console errors from Node-side
  listeners, because `page.evaluate` cannot see either.
- It writes shots **outside the repo** (`/tmp/uxsweep/shots`) so nothing
  leaks into `git status`.

## Run

```bash
# 1. driver + browser, never through the repo's manifest or lockfile (run from the app dir)
mkdir -p /tmp/uxsweep/shots
if node -e 'const p = require("./package.json"); process.exit({ ...p.dependencies, ...p.devDependencies }.playwright ? 0 : 1)'; then
    # the repo already depends on playwright: reuse its install
    ln -sfn "$PWD/node_modules" /tmp/uxsweep/node_modules
    npx playwright install chromium
else
    # install it in the script directory, never the repo: `npm i` inside a
    # pnpm/yarn workspace fails on `workspace:` deps and rewrites node_modules
    (cd /tmp/uxsweep && npm init -y >/dev/null && npm i playwright && npx playwright install chromium)
fi

# 2. production build + preview on a stable port (use the repo's package manager)
npm run build
npx vite preview --port 4173 --strictPort --host 0.0.0.0 &   # or: npx serve -s dist -l 4173
# serve moves to a free port when 4173 is taken; BASE_URL must equal the port printed

# 3. capture, then prove each shot actually rendered
node /tmp/uxsweep/capture.mjs            # read each shot's UNMOCKED: line and the closing UNRENDERED/UNMOCKED lists
md5sum /tmp/uxsweep/shots/*.png | sort   # duplicate hash across routes == route never rendered
```

## Skeleton — `/tmp/uxsweep/capture.mjs`

```js
import { chromium } from "playwright";
import path from "node:path";
import fs from "node:fs";

const SHOTS_DIR = "/tmp/uxsweep/shots";
fs.mkdirSync(SHOTS_DIR, { recursive: true });
// ── REPO-SPECIFIC 1/4: preview port ──────────────────────────────────
const BASE_URL = "http://localhost:4173"; // the PREVIEW server, not dev; must equal the port it prints
// ─────────────────────────────────────────────────────────────────────

// ── REPO-SPECIFIC 2/4: API base + mock fixtures and routing ──────────
const API_GLOB = "**/api/v1/**";        // match your app's client base (path or absolute origin)
const API_PREFIX = /^\/api\/v1\//;
const IDENTITY_PATHS = ["users", "auth/me"]; // 401 when unauthed
const USER = { _id: "u-1", username: "Avery Chen", email: "a@x.dev" };
const fixtures = {
    // Return ARRAYS where the app maps over a collection (a scalar throws
    // `(x ?? []).map is not a function` and trips the error boundary).
    "users/members": [USER, { _id: "u-2", username: "Bao", email: "b@x.dev" }],
    projects: [{ _id: "p-1", projectName: "Demo project" }]
};
// Return undefined for an unmocked call: the harness records it for the shot
// and serves a placeholder (GET → [], else { ok: true }). Add a typed fixture.
const route = (p, method) => {
    if (IDENTITY_PATHS.includes(p)) return USER;       // identity → authed
    if (Object.hasOwn(fixtures, p)) return fixtures[p];
    return undefined;
};
// ─────────────────────────────────────────────────────────────────────

const installMocks = async (context, { authed, hits, unmocked }) => {
    // Playwright tries the most recently registered matching route first, so
    // register any broad stub before the API route, never after it.
    // Abort web fonts so an unreachable font host can't stall the page; text
    // then renders in fallback fonts, and each abort logs one "Failed to load
    // resource" console error. Delete this when the host is reachable.
    await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (r) => r.abort());
    await context.route(API_GLOB, async (r, req) => {
        const p = new URL(req.url()).pathname.replace(API_PREFIX, "");
        hits.push(`${req.method()} ${p}`);
        if (!authed && IDENTITY_PATHS.includes(p)) {
            return r.fulfill({ status: 401, contentType: "application/json", body: "{}" });
        }
        let body = route(p, req.method());
        if (body === undefined) {
            unmocked.push(`${req.method()} ${p}`);
            body = req.method() === "GET" ? [] : { ok: true };
        }
        await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
};

const VIEWPORTS = { iphone13: { width: 390, height: 844 }, desktop: { width: 1280, height: 800 } };
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));
// waitForFunction(fn, arg, options): options go third, or the timeout is ignored.
const waitFor = (page, text) => page.waitForFunction(
    (t) => document.body && document.body.innerText.includes(t), text, { timeout: 15000 }
).then(() => true, () => false);

// prefers-reduced-transparency is not an emulateMedia option, and emulateMedia
// silently ignores unknown keys. Chromium only: set it over CDP, then confirm.
const emulateReducedTransparency = async (page) => {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", {
        features: [{ name: "prefers-reduced-transparency", value: "reduce" }]
    });
    const on = await page.evaluate(() => matchMedia("(prefers-reduced-transparency: reduce)").matches);
    if (!on) throw new Error("prefers-reduced-transparency did not apply");
};

// ── REPO-SPECIFIC 3/4: capture matrix (media + steps per entry) ──────
// media:     page.emulateMedia keys: colorScheme, contrast, reducedMotion, forcedColors.
//            Shots disable animations, so a reducedMotion shot shows only
//            layout swaps; check motion itself with the motion probe below.
// steps:     runs after waitText appears. Click through to nested/guarded
//            routes and set interaction states (hover, focus, open menu) here.
// waitAfter: text that must appear after steps (defaults to waitText).
// state:     names the shot when steps change what is on screen.
const projects = { slug: "projects", path: "/projects", waitText: "Demo project", authed: true };
const captures = [
    { slug: "login", path: "/login", vp: "desktop", media: { colorScheme: "light" }, waitText: "Log in", authed: false },
    { ...projects, vp: "desktop", media: { colorScheme: "light" } },
    { ...projects, vp: "desktop", media: { colorScheme: "dark" } },
    { ...projects, vp: "iphone13", media: { colorScheme: "light" } },
    { ...projects, vp: "iphone13", media: { colorScheme: "dark" } },
    { ...projects, vp: "desktop", media: { colorScheme: "light", contrast: "more" } },
    { ...projects, vp: "desktop", media: { colorScheme: "light", forcedColors: "active" } },
    { ...projects, vp: "desktop", media: { colorScheme: "light", reducedMotion: "reduce" } },
    { ...projects, vp: "desktop", media: { colorScheme: "light" }, state: "reducedTransparency",
        steps: emulateReducedTransparency },
    { ...projects, vp: "desktop", media: { colorScheme: "light" }, state: "accountMenuOpen",
        steps: (page) => page.getByRole("button", { name: "Account" }).click(), waitAfter: "Log out" }
];
// ─────────────────────────────────────────────────────────────────────

// ── REPO-SPECIFIC 4/4: auth + theme seed ─────────────────────────────
const seed = async (context, c) => {
    // auth: the token/session the app checks, written before first paint
    if (c.authed) await context.addInitScript(() => {
        try { window.sessionStorage.setItem("ai_jwt", "fake.jwt.token"); } catch (e) {}
    });
    // theme: set the key your theme provider reads; delete if the app follows prefers-color-scheme
    await context.addInitScript((s) => {
        try { window.localStorage.setItem("ui:colorScheme", s); } catch (e) {}
    }, c.media.colorScheme ?? "light");
};
// ─────────────────────────────────────────────────────────────────────

const DEFAULT_MEDIA = { contrast: "no-preference", reducedMotion: "no-preference", forcedColors: "none" };
const shotName = (c) => [
    c.slug, c.vp, c.media.colorScheme ?? "light",
    ...Object.entries(c.media)
        .filter(([k, v]) => k !== "colorScheme" && v !== DEFAULT_MEDIA[k])
        .map(([k, v]) => `${k}-${v}`),
    ...(c.state ? [c.state] : [])
].join("__");

const run = async () => {
    const names = captures.map(shotName);
    const dup = names.find((n, i) => names.indexOf(n) !== i);
    if (dup) throw new Error(`two captures are both named ${dup}; give one a distinct media key or state`);
    const browser = await chromium.launch({ args: ["--no-sandbox"] });
    const bad = [];
    const gaps = [];  // shots with at least one unmocked call
    for (const [i, c] of captures.entries()) {
        const name = names[i];
        const vp = VIEWPORTS[c.vp];
        const isPhone = vp.width < 600;
        const context = await browser.newContext({
            viewport: vp, colorScheme: c.media.colorScheme ?? "light", deviceScaleFactor: 2,
            hasTouch: isPhone, isMobile: isPhone
        });
        await seed(context, c);
        const hits = [];
        const unmocked = [];
        await installMocks(context, { authed: c.authed, hits, unmocked });
        const page = await context.newPage();
        await page.emulateMedia(c.media);

        const errs = [];  // uncaught page errors: the shot is un-rendered
        const logs = [];  // console errors: evidence for the probe, not a verdict
        page.on("pageerror", (e) => errs.push(e.message.slice(0, 160)));
        page.on("console", (m) => { if (m.type() === "error") logs.push(m.text().slice(0, 160)); });
        try {
            // goto top-level + public paths only; reach nested/guarded routes in steps.
            await page.goto(`${BASE_URL}${c.path}`, { waitUntil: "domcontentloaded", timeout: 20000 });
            // WAIT FOR CONTENT, not for a spinner to clear.
            let rendered = await waitFor(page, c.waitText);
            if (rendered && c.steps) {
                await c.steps(page);
                rendered = await waitFor(page, c.waitAfter ?? c.waitText);
            }
            await sleep(800);
            const ok = rendered && errs.length === 0;
            if (!ok) bad.push(name);
            const file = ok ? `${name}.png` : `${name}__UNRENDERED.png`;
            await page.screenshot({ path: path.join(SHOTS_DIR, file), fullPage: true, animations: "disabled" });
            console.log(ok ? "  captured" : "  UNRENDERED", file, rendered ? "" : "(content wait missed)");
        } catch (e) {
            bad.push(name);
            console.error("  FAILED", name, e.message);
        } finally {
            // Print the evidence even when the shot threw, so a failed click-through keeps it.
            console.log("    api:", hits.join(", ") || "(none)");
            if (unmocked.length) { gaps.push(name); console.log("    UNMOCKED:", unmocked.join(", ")); }
            if (errs.length) console.log("    pageerror:", errs.join(" | "));
            if (logs.length) console.log("    console.error:", logs.join(" | "));
            await context.close();
        }
    }
    await browser.close();
    console.log(bad.length ? `UNRENDERED (probe before review): ${bad.join(", ")}` : "all shots rendered");
    console.log(gaps.length ? `UNMOCKED (add fixtures): ${gaps.join(", ")}` : "no unmocked calls");
    console.log("done.");
};
run().catch((e) => { console.error("fatal", e); process.exit(1); });
```

## Deep / nested / guarded routes

A direct `goto` works for top-level routes. For a nested/guarded route,
`goto` the parent and click in from the entry's `steps` — verified far more
reliable than a deep-link `goto`, which can leave the child stuck in
Suspense with only the app-shell queries fired:

```js
const boardEntry = {
    slug: "board", path: "/projects", vp: "desktop", media: { colorScheme: "light" },
    waitText: "Demo project", authed: true,                                   // the rendered parent
    steps: (page) => page.getByText("Demo project").first().click(),         // navigate like a user
    waitAfter: "Backlog"                                                      // a board column
};
```

This entry needs fixtures for every endpoint the child route fetches (here
the project detail, `projects/p-1`, and its board columns). Without them
the shot's `UNMOCKED:` line names the missing paths and the `Backlog` wait
misses.

## One-shot root-cause probe (step 6)

The harness already prints each shot's API hits, page errors and console
errors. When a shot is blank, stuck or odd, don't guess from code — filter
`captures` to that entry, re-run, and dump the page after the content wait:

```js
const info = await page.evaluate(() => ({
    url: location.href,
    loading: document.body.innerText.toLowerCase().includes("loading"),
    text: document.body.innerText.replace(/\s+/g, " ").slice(0, 300)
}));
console.log(info);
// "only identity endpoints in api:, the route's own queries never fired" ⇒
// the route is stuck in dev lazy-compile or a guard, not a code bug.
```

For a visual issue (contrast, overflow, clipping, motion), read the
element's computed style and box instead of guessing from the stylesheet.
For reduced motion, run it on the same element under
`reducedMotion: "no-preference"` and under `"reduce"`. The app honours the
preference if, under `reduce`, the animation is removed (`animationName:
none`) or its `animationDuration` or `transitionDuration` drops to near
zero (the common `.01ms` reset reads `1e-05s`). Values unchanged between
the two runs mean it ignores the preference.

```js
const style = await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const cs = getComputedStyle(el);
    return { color: cs.color, background: cs.backgroundColor, overflow: cs.overflow,
        animationName: cs.animationName, animationDuration: cs.animationDuration,
        transitionDuration: cs.transitionDuration,
        scrollWidth: el.scrollWidth, clientWidth: el.clientWidth };
}, ".the-element");
console.log(style);
```
