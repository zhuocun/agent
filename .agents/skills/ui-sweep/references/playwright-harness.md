# Playwright capture harness

A reusable, framework-agnostic capture script. Copy it and keep its
structure (mocks, content wait, error capture, verification) unchanged.
Change only the four clearly-marked repo-specific blocks: the **preview
port**, the **API base + observed request surface, mock fixtures and
routing**, the **capture matrix (media + steps and final route/state checks
per entry, each entry choosing one of the existing `VIEWPORTS`)**, and the
**auth + theme seed**. The one edit outside them
is the font-abort route in `installMocks`: delete it when the font host is
reachable.

- [Why it is shaped this way](#why-it-is-shaped-this-way)
- [Run](#run)
- [Skeleton — `/tmp/uxsweep/capture.mjs`](#skeleton--tmpuxsweepcapturemjs)
- [Deep / nested / guarded routes](#deep--nested--guarded-routes)
- [One-shot root-cause probe (step 6)](#one-shot-root-cause-probe-step-6)

## Why it is shaped this way

- It intercepts the declared browser API match and awaits complete fixture
  responses. Select fixtures by actual method, full URL and relevant
  query/body/header distinctions, using discovered status, headers/content
  type and body shape for every response needed by the selected state,
  including errors, non-JSON and bodyless responses. `route(req, c)` may
  resolve asynchronously to `{ status, headers, body }` (serialized string
  or Buffer body; `""` for no body), or `undefined` for an unknown request.
  Unknowns and fixture failures are diagnosed and aborted, not forwarded
  or filled with invented data. JSON serialization is an explicit helper,
  not an assumption imposed by the adapter.
- It blocks service workers and compares matched hits with an independent
  relevant-request observer. The broad guard aborts relevant requests
  outside `API_GLOB`; only ordinary non-API resources continue. Derive
  `isRelevantRequest` from the app, including its API URLs and browser
  fetch/XHR traffic. These observations do not cover WebSockets,
  server-side calls or every other channel/origin. For channels used by
  selected states, establish the required mocks separately or report the
  affected evidence as unverified; no matched unknowns is not proof of
  complete backend/API coverage. The real backend is usually blocked from
  the sandbox. Each shot prints `UNMOCKED`, fixture and coverage diagnostics.
- It captures against a **production build served by a preview server**
  (see `SKILL.md` → Setup). Point `BASE_URL` at the preview port.
- It waits for **real content** before each shot, not a loading spinner.
  Classification follows successful acquisition and final route/content/
  state/media and error observations, including errors during capture.
  Acquired invalid PNGs are saved as `<name>__UNRENDERED.png`; failed
  acquisition is a stage failure. Earlier setup failures retain diagnostics
  and attempt owned cleanup without replacing the original failure.
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
node /tmp/uxsweep/capture.mjs            # read stage failures, UNRENDERED, UNMOCKED and coverage/media diagnostics
md5sum /tmp/uxsweep/shots/*.png | sort   # investigate duplicates with route/state/content/API/DOM evidence
```

## Skeleton — `/tmp/uxsweep/capture.mjs`

```js
import { chromium } from "playwright";
import path from "node:path";
import fs from "node:fs";
import { createRequire } from "node:module";

const SHOTS_DIR = "/tmp/uxsweep/shots";
// ── REPO-SPECIFIC 1/4: preview port ──────────────────────────────────
const BASE_URL = "http://localhost:4173"; // the PREVIEW server, not dev; must equal the port it prints
// ─────────────────────────────────────────────────────────────────────

// ── REPO-SPECIFIC 2/4: API base + mock fixtures and routing ──────────
const API_GLOB = "**/api/v1/**";        // match your app's client base (path or absolute origin)
const API_BASE = new URL("/api/v1/", BASE_URL); // use the actual origin, including a separate API origin
const isRelevantRequest = (req) => ["xhr", "fetch"].includes(req.resourceType()) ||
    (new URL(req.url()).origin === API_BASE.origin && new URL(req.url()).pathname.startsWith(API_BASE.pathname));
const key = (method, url, body = null) => JSON.stringify([
    method, new URL(url, API_BASE).href, body === null ? null : Buffer.from(body).toString("base64")
]);
const requestKey = (req) => key(req.method(), req.url(), req.postDataBuffer());
const identityKeys = ["users", "auth/me"].map((p) => key("GET", p)); // 401 only for these session probes
const jsonResponse = (status, value) => ({
    status, headers: { "content-type": "application/json" }, body: JSON.stringify(value)
});
const USER = { _id: "u-1", username: "Avery Chen", email: "a@x.dev" };
const fixtures = new Map([
    // Return ARRAYS where the app maps over a collection (a scalar throws
    // `(x ?? []).map is not a function` and trips the error boundary).
    [key("GET", "users/members"), jsonResponse(200, [USER, { _id: "u-2", username: "Bao", email: "b@x.dev" }])],
    [key("GET", "projects"), jsonResponse(200, [{ _id: "p-1", projectName: "Demo project" }])]
]);
// Replace illustrative shapes with discovered types/fixtures. Match query/body
// variants explicitly; use req headers when relevant. Select state-specific
// success/error responses with c as needed, awaiting asynchronous selection.
const route = async (req, c) => {
    const k = requestKey(req);
    if (identityKeys.includes(k)) return jsonResponse(c.authed ? 200 : 401, c.authed ? USER : {});
    return fixtures.get(k); // undefined stays explicitly UNMOCKED
};
// ─────────────────────────────────────────────────────────────────────

const installMocks = async (context, c, { hits, unmocked, mockErrors, observed, matched, pending }) => {
    context.on("request", (req) => { if (isRelevantRequest(req)) observed.add(req); });
    // Playwright tries the most recently registered matching route first, so
    // register any broad stub before the API route, never after it.
    await context.route("**/*", async (r, req) => {
        try {
            if (isRelevantRequest(req)) await r.abort(); // outside API_GLOB; never forward unknown API traffic
            else await r.continue(); // ordinary documents/scripts/images, not an API fallback
        } catch (e) { mockErrors.push(`coverage guard: ${e.message}`); }
    });
    // Abort web fonts so an unreachable font host can't stall the page; text
    // then renders in fallback fonts, and each abort logs one "Failed to load
    // resource" console error. Delete this when the host is reachable.
    await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//,
        (r) => r.abort().catch((e) => { mockErrors.push(`font abort: ${e.message}`); }));
    await context.route(API_GLOB, async (r, req) => {
        matched.add(req);
        pending.add(req);
        let k = `${req.method()} ${req.url()}`;
        try {
            k = requestKey(req);
            hits.push({ request: k });
            const response = await route(req, c);
            if (response === undefined) {
                unmocked.push(k);
                await r.abort();
                return;
            }
            if (!Number.isInteger(response.status) || response.status < 200 || response.status > 599 ||
                !response.headers || typeof response.headers !== "object" ||
                Object.values(response.headers).some((v) => typeof v !== "string") ||
                !(typeof response.body === "string" || Buffer.isBuffer(response.body))) {
                throw new Error(`invalid fixture response for ${k}`);
            }
            hits.push({ request: k, response: { status: response.status, headers: response.headers, body: response.body } });
            await r.fulfill({ status: response.status, headers: response.headers, body: response.body });
        } catch (e) {
            mockErrors.push(`${k}: ${e.message}`);
            try { await r.abort(); } catch (abortError) { mockErrors.push(`abort: ${abortError.message}`); }
        } finally { pending.delete(req); }
    });
};

const VIEWPORTS = { iphone13: { width: 390, height: 844 }, desktop: { width: 1280, height: 800 } };
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));
// waitForFunction(fn, arg, options): options go third, or the timeout is ignored.
const waitFor = (page, text) => page.waitForFunction(
    (t) => document.body && document.body.innerText.includes(t), text, { timeout: 15000 }
).then(() => true, () => false);

const MEDIA = {
    colorScheme: { feature: "prefers-color-scheme", values: ["light", "dark"], since: 9 },
    contrast: { feature: "prefers-contrast", values: ["no-preference", "more"], since: 51 },
    reducedMotion: { feature: "prefers-reduced-motion", values: ["no-preference", "reduce"], since: 12 },
    forcedColors: { feature: "forced-colors", values: ["none", "active"], since: 15 }
};
const verifyMedia = async (page, c) => {
    const queries = Object.entries(c.media).map(([k, v]) => `(${MEDIA[k].feature}: ${v})`);
    if (c.reducedTransparency) queries.push("(prefers-reduced-transparency: reduce)");
    const effective = await page.evaluate((qs) => qs.map((q) => [q, matchMedia(q).matches]), queries);
    if (effective.some(([, on]) => !on)) throw new Error(`UNVERIFIED_MEDIA ${JSON.stringify(effective)}`);
    return effective;
};
// Chromium only; retain requested features when setting transparency over CDP.
const emulateReducedTransparency = async (page, c) => {
    // Keep the override's session attached through capture; per-case context cleanup closes its target.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", { features: [
        ...Object.entries(c.media).map(([k, value]) => ({ name: MEDIA[k].feature, value })),
        { name: "prefers-reduced-transparency", value: "reduce" }
    ] });
    await verifyMedia(page, c);
};

// ── REPO-SPECIFIC 3/4: capture matrix (media + steps per entry) ──────
// media:     page.emulateMedia keys: colorScheme, contrast, reducedMotion, forcedColors.
//            Shots disable animations, so a reducedMotion shot shows only
//            layout swaps; check actual motion by mechanism/intent, as in step 6.
// steps:     runs after waitText appears. Click through to nested/guarded
//            routes and set interaction states (hover, focus, open menu) here.
// waitAfter: text that must appear after steps (defaults to waitText).
// state:     names the shot when steps change what is on screen.
// finalPath: expected final URL path/query/hash after steps (defaults to path).
// checkState: optional async (page) => boolean for state not identified by text/URL;
//             checked before and after capture. Use when the selected state needs it.
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
        reducedTransparency: true, steps: emulateReducedTransparency },
    { ...projects, vp: "desktop", media: { colorScheme: "light" }, state: "accountMenuOpen",
        steps: (page) => page.getByRole("button", { name: "Account" }).click(), waitAfter: "Log out" }
];
// ─────────────────────────────────────────────────────────────────────

// ── REPO-SPECIFIC 4/4: auth + theme seed ─────────────────────────────
const seed = async (context, c) => {
    // auth: the token/session the app checks, written before first paint
    if (c.authed) await context.addInitScript(() => {
        try { window.sessionStorage.setItem("auth_token", "fake.jwt.token"); } catch (e) {}
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
    const bad = [];
    const gaps = [];  // shots with at least one unmocked call
    let browser;
    let runStage = "driver metadata/output setup";
    try {
        const driverVersion = createRequire(import.meta.url)("playwright/package.json").version;
        const [major, minor] = driverVersion.split(".").map(Number);
        fs.mkdirSync(SHOTS_DIR, { recursive: true });
        runStage = "browser launch";
        browser = await chromium.launch({ args: ["--no-sandbox"] });
        console.log("driver:", driverVersion, "browser:", browser.version());
        const names = new Set();
        for (const [i, c] of captures.entries()) {
            runStage = `case ${i}`;
            let name = `case-${i}`;
            let stage = "configuration";
            let context, page, png, info, failure;
            let rendered = false, finalOK = false, pendingAtCapture = 0;
            const hits = [], unmocked = [], mockErrors = [], errs = [], logs = [], cleanupErrors = [];
            const observed = new Set(), matched = new Set(), pending = new Set();
            let mediaEvidence;
            try {
                name = shotName(c);
                if (names.has(name)) throw new Error(`two captures are named ${name}; give one a distinct media key or state`);
                names.add(name);
                const vp = VIEWPORTS[c.vp];
                if (!vp) throw new Error(`unknown viewport ${c.vp}`);
                stage = "media API capability";
                for (const [k, v] of Object.entries(c.media)) {
                    const spec = MEDIA[k];
                    if (!spec || !spec.values.includes(v) || !Number.isInteger(major) || !Number.isInteger(minor) ||
                        !(major > 1 || (major === 1 && minor >= spec.since))) {
                        throw new Error(`UNVERIFIED_MEDIA ${k}=${v} with driver ${driverVersion}`);
                    }
                }
                stage = "context setup";
                const isPhone = vp.width < 600;
                context = await browser.newContext({
                    viewport: vp, colorScheme: c.media.colorScheme ?? "light", deviceScaleFactor: 2,
                    hasTouch: isPhone, isMobile: isPhone, serviceWorkers: "block"
                });
                stage = "auth/theme seed";
                await seed(context, c);
                stage = "mock setup";
                await installMocks(context, c, { hits, unmocked, mockErrors, observed, matched, pending });
                stage = "page setup";
                page = await context.newPage();
                page.on("pageerror", (e) => errs.push(e.message.slice(0, 160)));
                page.on("console", (m) => { if (m.type() === "error") logs.push(m.text().slice(0, 160)); });
                stage = "media emulation";
                await page.emulateMedia(c.media);
                stage = "navigation";
                // goto top-level + public paths only; reach nested/guarded routes in steps.
                await page.goto(new URL(c.path, BASE_URL).href, { waitUntil: "domcontentloaded", timeout: 20000 });
                stage = "content readiness";
                rendered = await waitFor(page, c.waitText);
                if (rendered && c.steps) {
                    stage = "interaction state";
                    await c.steps(page, c);
                    stage = "state readiness";
                    rendered = await waitFor(page, c.waitAfter ?? c.waitText);
                }
                stage = "settle/state verification";
                await sleep(800);
                if (c.checkState) rendered = (await c.checkState(page)) && rendered;
                stage = "effective media";
                mediaEvidence = await verifyMedia(page, c);
                stage = "screenshot acquisition";
                png = await page.screenshot({ fullPage: true, animations: "disabled" });
                stage = "final evidence";
                info = await page.evaluate(() => ({ url: location.href, text: document.body?.innerText ?? "" }));
                finalOK = info.url === new URL(c.finalPath ?? c.path, BASE_URL).href &&
                    info.text.includes(c.waitAfter ?? c.waitText) && (!c.checkState || await c.checkState(page));
                mediaEvidence = await verifyMedia(page, c);
                pendingAtCapture = pending.size;
            } catch (e) {
                failure = { stage, message: e.message };
                console.error("  FAILED", name, JSON.stringify(failure));
            } finally {
                // Diagnostic acquisition and owned cleanup have separate failure paths.
                if (page && !info) {
                    try { info = await page.evaluate(() => ({ url: location.href, text: document.body?.innerText ?? "" })); }
                    catch (e) { console.log("    page: unavailable", e.message); }
                }
                if (context) {
                    try { await context.close(); } catch (e) { cleanupErrors.push(e.message); }
                }
            }
            try {
                const outside = [...observed].filter((req) => !matched.has(req)).map(requestKey);
                console.log("    api:", JSON.stringify(hits));
                if (unmocked.length) console.log("    UNMOCKED:", JSON.stringify(unmocked));
                if (outside.length) console.log("    OUTSIDE_API_MATCH (unverified):", JSON.stringify(outside));
                if (mockErrors.length) console.log("    FIXTURE_FAILURE:", JSON.stringify(mockErrors));
                if (pendingAtCapture || pending.size) console.log("    PENDING_FIXTURES:", pendingAtCapture || pending.size);
                if (errs.length) console.log("    pageerror:", errs.join(" | "));
                if (logs.length) console.log("    console.error:", logs.join(" | "));
                if (cleanupErrors.length) console.log("    context cleanup:", cleanupErrors.join(" | "));
                console.log("    media:", JSON.stringify(mediaEvidence ?? "unverified"));
                console.log("    page:", info ? JSON.stringify({ url: info.url,
                    loading: info.text.toLowerCase().includes("loading"), text: info.text.replace(/\s+/g, " ").slice(0, 300) }) : "unavailable");
                const ok = !!png && !failure && rendered && finalOK && errs.length === 0 &&
                    !unmocked.length && !outside.length && !mockErrors.length && !pendingAtCapture && !pending.size;
                if (!ok) bad.push(name);
                if (unmocked.length || outside.length || mockErrors.length || pendingAtCapture || pending.size) gaps.push(name);
                if (png) {
                    const file = ok ? `${name}.png` : `${name}__UNRENDERED.png`;
                    try {
                        fs.writeFileSync(path.join(SHOTS_DIR, file), png);
                        console.log(ok ? "  captured" : "  UNRENDERED", file,
                            rendered && finalOK ? "" : "(readiness/final route or state not confirmed)");
                    } catch (e) {
                        if (!bad.includes(name)) bad.push(name);
                        console.error("  FAILED", name, "PNG write:", e.message);
                    }
                } else {
                    console.log("  NO_CAPTURE", name);
                }
            } catch (e) {
                if (!bad.includes(name)) bad.push(name);
                console.error("  FAILED", name, "evidence reporting:", e.message);
            }
        }
    } catch (e) {
        console.error("RUN FAILED", runStage, e.message, "— no complete capture run; inspect per-case output");
        throw e;
    } finally {
        if (browser) {
            try { await browser.close(); } catch (e) { console.error("browser cleanup:", e.message); }
        }
    }
    console.log(bad.length ? `UNRENDERED / FAILED (probe before review): ${bad.join(", ")}` : "all acquired shots passed observed render checks");
    console.log(gaps.length ? `UNMOCKED / COVERAGE GAPS (resolve fixtures/surface): ${gaps.join(", ")}` : "no observed gaps on the declared browser request surface; other channels not established here");
    console.log("done.");
};
run().catch((e) => { console.error("fatal", e); process.exit(1); });
```

## Deep / nested / guarded routes

A direct `goto` works for top-level routes. For a nested/guarded route,
`goto` the parent and click in from the entry's `steps` — a deep-link
`goto` can leave the child stuck in Suspense with only the app-shell
queries fired:

```js
const boardEntry = {
    slug: "board", path: "/projects", vp: "desktop", media: { colorScheme: "light" },
    waitText: "Demo project", authed: true,                                   // the rendered parent
    steps: (page) => page.getByText("Demo project").first().click(),         // navigate like a user
    finalPath: "/projects/p-1/board", waitAfter: "Backlog"                     // discovered final route + a board column
};
```

This entry needs complete responses for every request the child awaits
(here the project detail, `projects/p-1`, and its board columns). Match the
actual method/full URL/query/body, status and shape using `route(req, c)`;
the starter does not supply those child fixtures. Missing ones are aborted
and named by request identity in `UNMOCKED`; the `Backlog` wait may miss.
Set `finalPath` to the discovered final URL path/query/hash, and use
`checkState` when URL/text alone cannot distinguish the selected state.

## One-shot root-cause probe (step 6)

The harness prints each shot's matched requests and fixture responses,
coverage gaps, stage failures, page errors and console errors. It acquires
final page evidence after capture, or attempts a diagnostic dump before
cleanup if a stage failed. For a blank, stuck or odd shot,
filter `captures` to that entry, re-run, and read those lines together.
The dump evaluates:

```js
const info = await page.evaluate(() => ({
    url: location.href,
    loading: document.body?.innerText.toLowerCase().includes("loading") ?? false,
    text: (document.body?.innerText ?? "").replace(/\s+/g, " ").slice(0, 300)
}));
console.log(info);
// Only identity calls observed suggests a guard, mount or readiness hypothesis.
// Trace requests/responses/fixtures/state/guards/mount/CSS before assigning fault.
```

For a visual issue (contrast, overflow, clipping, motion), read the
element's computed style and box instead of guessing from the stylesheet.
For reduced motion, establish effective `"no-preference"` and `"reduce"`
queries on the same element and identify its actual mechanism and intended
response. Computed styles can support CSS transition/keyframe analysis,
but also inspect applicable rules/keyframes, JavaScript preference handling,
SVG or WAAPI as relevant, with appropriate live observations before
animation-disabled capture. Reduced motion may remove, reduce or replace
motion. Equal durations or pixels alone neither prove nor disprove support;
animation-disabled screenshots are not a reduced-motion test.

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
