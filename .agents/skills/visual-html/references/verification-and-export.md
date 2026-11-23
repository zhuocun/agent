# Verification and export

- [Browser setup](#browser-setup)
- [Viewports and layout classes](#viewports-and-layout-classes)
- [DOM geometry probe](#dom-geometry-probe)
- [Visual review checklist](#visual-review-checklist)
- [Reduced motion, no-JavaScript and grayscale renders](#reduced-motion-no-javascript-and-grayscale-renders)
- [Running the structural checker](#running-the-structural-checker)
- [PNG export protocol](#png-export-protocol)
- [Standalone embed blocks](#standalone-embed-blocks)

## Browser setup

Install the browser driver in a scratch directory outside the project, so that
the project's manifest and lockfile stay unchanged:

```bash
mkdir -p "${TMPDIR:-/tmp}/visual-html-verify"
cd "${TMPDIR:-/tmp}/visual-html-verify"
npm init -y
npm install playwright
npx playwright install chromium
```

- Save `verify.mjs` and `export.mjs` from this file in that directory. An ES
  module resolves `import "playwright"` from its own directory.
- Confirm that `chromium.launch()` succeeds before the first run. If the
  browser download is blocked, pass an installed Chrome or Chromium binary as
  `chromium.launch({ executablePath })`. If neither works, report browser
  verification as not done.
- For a CJK page, confirm that a CJK font is installed, for example with
  `fc-list :lang=zh family` (or `ja`, `ko`). If none is listed, install one,
  such as the `fonts-noto-cjk` package, or report CJK rendering as unverified.
  A screenshot that shows empty boxes in place of characters is invalid
  evidence.
- Write screenshots and exports to the paths that the **Modes** rule in
  `SKILL.md` sets for the mode.

## Viewports and layout classes

| Name | Size | Expected layout in a two-layout figure | Font floor for a single-layout SVG |
| --- | --- | --- | --- |
| desktop | 1440 × 900 | wide | 14px |
| breakpoint | the page's breakpoint width × 800, 1056 with the default values | wide | 14px |
| phone | 390 × 844 | narrow | 12.5px |

- Pass the page's breakpoint to `verify.mjs` when it differs from 1056.
- `verify.mjs`, `export.mjs` and the structural checker classify each diagram
  SVG associated with its nearest enclosing `<figure>` the same way (class
  tokens matched case-insensitively). Only a definitions-only SVG — one with
  `aria-hidden="true"`, a `<defs>` element and no renderable graphics outside
  `<defs>` — is skipped.
  - **Narrow:** `data-layout="narrow"`, or class `narrow` or `n`.
  - **Wide:** `data-layout="wide"`, or class `wide` or `w`.
  - **Single:** `data-layout="single"`, or an unmarked SVG that is the only
    diagram SVG in its figure.
  - An unmarked SVG beside other diagram SVGs counts as wide.
- A two-layout figure holds a wide SVG and a narrow SVG. At each viewport,
  exactly one SVG of each figure must be visible, and in a two-layout figure it
  must be the expected layout.
- Apply the font floors in **Maximum readability** in `SKILL.md` at every
  viewport that shows each layout.

## DOM geometry probe

`verify.mjs` renders the page at each viewport and in each render variant,
scrolls through it, runs the probe, writes one full-page screenshot per run,
and exits with 1 when any check fails:

```js
// verify.mjs: node verify.mjs <page.html> <out-dir> [breakpoint-width]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [pageArg, outArg, bpArg] = process.argv.slice(2);
if (!pageArg || !outArg) {
  console.error("usage: node verify.mjs <page.html> <out-dir> [breakpoint-width]");
  process.exit(2);
}
const url = pathToFileURL(path.resolve(pageArg)).href;
const outDir = path.resolve(outArg);
mkdirSync(outDir, { recursive: true });
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, phone: false },
  { name: "breakpoint", width: Number(bpArg || 1056), height: 800, phone: false },
  { name: "phone", width: 390, height: 844, phone: true },
];
const FLOORS = { wide: 14, narrow: 12.5 };
const ALLOWED = []; // URL prefixes of outside assets the user required

function probe({ floors, phone }) {
  const problems = [];
  const root = document.documentElement;
  if (root.scrollWidth > innerWidth + 1) {
    problems.push(`page overflow: scrollWidth ${root.scrollWidth} > ${innerWidth}`);
  }
  const shown = (el) => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return cs.display !== "none" && cs.visibility === "visible" && r.width > 0 && r.height > 0;
  };
  const isDefsOnly = (svg) => {
    if ((svg.getAttribute("aria-hidden") || "").trim().toLowerCase() !== "true") return false;
    if (!svg.querySelector("defs")) return false;
    const draw = "rect, circle, ellipse, line, polyline, polygon, path, text, image, use, foreignObject";
    return ![...svg.querySelectorAll(draw)].some((el) => !el.closest("defs, symbol, marker, pattern, clipPath, mask"));
  };
  const marked = (svg) => {
    const d = (svg.getAttribute("data-layout") || "").trim().toLowerCase();
    const c = new Set([...svg.classList].map((x) => x.toLowerCase()));
    if (d === "narrow" || c.has("narrow") || c.has("n")) return "narrow";
    if (d === "wide" || c.has("wide") || c.has("w")) return "wide";
    if (d === "single") return "single";
    return null;
  };
  const inside = (a, b) =>
    a.left >= b.left - 0.5 && a.right <= b.right + 0.5 &&
    a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5;
  const overlap = (a, b) =>
    Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
    Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
  for (const fig of document.querySelectorAll("figure")) {
    const name = fig.dataset.figure || "(unnamed figure)";
    const svgs = [...fig.querySelectorAll("svg")].filter((s) => s.closest("figure") === fig && !isDefsOnly(s));
    if (!svgs.length) continue;
    const kinds = svgs.map((s) => marked(s) || (svgs.length === 1 ? "single" : "wide"));
    const dual = kinds.includes("wide") && kinds.includes("narrow");
    const expected = dual ? (phone ? "narrow" : "wide") : null;
    const visible = svgs.filter(shown);
    if (visible.length !== 1) {
      problems.push(`${name}: ${visible.length} SVGs visible, expected 1`);
      continue;
    }
    const svg = visible[0];
    const kind = kinds[svgs.indexOf(svg)];
    if (expected && kind !== expected) problems.push(`${name}: ${kind} layout visible, expected ${expected}`);
    const floor = kind === "narrow" || (kind === "single" && phone) ? floors.narrow : floors.wide;
    for (let el = svg; el; el = el.parentElement) {
      const o = getComputedStyle(el).opacity;
      if (o !== "1") problems.push(`${name}/${kind}: <${el.tagName.toLowerCase()}> has opacity ${o}`);
    }
    const svgBox = svg.getBoundingClientRect();
    const runs = [];
    for (const el of svg.querySelectorAll("text, tspan, textPath")) {
      const own = [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
      if (!own) continue;
      const where = `${name}/${kind} "${el.textContent.trim().slice(0, 40)}"`;
      const cs = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      const unpainted = cs.fill === "none" && cs.stroke === "none";
      let hidden = cs.display === "none" || cs.visibility !== "visible" || unpainted || box.width === 0 || box.height === 0;
      for (let e = el; e && e !== svg; e = e.parentElement) {
        if (getComputedStyle(e).opacity !== "1") hidden = true;
      }
      if (hidden) {
        problems.push(`${where}: hidden, transparent, unpainted or zero-size label`);
        continue;
      }
      const m = (el.getScreenCTM ? el : el.closest("text")).getScreenCTM();
      const scale = Math.min(Math.hypot(m.a, m.b), Math.hypot(m.c, m.d));
      const px = parseFloat(cs.fontSize) * scale;
      if (px < floor - 0.01) problems.push(`${where}: renders at ${px.toFixed(2)}px, floor ${floor}px`);
      if (!inside(box, svgBox)) problems.push(`${where}: outside its SVG`);
      const shape = el.closest("[data-node]")?.querySelector(":scope > rect");
      if (shape && !inside(box, shape.getBoundingClientRect())) problems.push(`${where}: overflows its node`);
      runs.push([where, box, el.closest("text")]);
    }
    for (let i = 0; i < runs.length; i++) {
      for (let j = i + 1; j < runs.length; j++) {
        if (runs[i][2] !== runs[j][2] && overlap(runs[i][1], runs[j][1])) {
          problems.push(`${runs[i][0]} overlaps ${runs[j][0]}`);
        }
      }
    }
  }
  return problems;
}

async function check(browser, vp, options, suffix, grayscale = false) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, ...options });
  const page = await context.newPage();
  const problems = [];
  const allowed = (u) => u === url || u.startsWith("data:") || ALLOWED.some((p) => u.startsWith(p));
  page.on("console", (msg) => { if (msg.type() === "error") problems.push(`console: ${msg.text()}`); });
  page.on("pageerror", (err) => problems.push(`page error: ${err.message}`));
  page.on("request", (req) => { if (!allowed(req.url())) problems.push(`request outside the page: ${req.url()}`); });
  await context.route(/^https?:/, (route) => (allowed(route.request().url()) ? route.continue() : route.abort()));
  await page.goto(url, { waitUntil: "load" });
  if (grayscale) await page.addStyleTag({ content: "html { filter: grayscale(100%) !important; }" });
  try {
    await page.evaluate(async () => {
      await document.fonts.ready;
      for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight / 2) {
        scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 150));
      }
      scrollTo(0, 0);
      await new Promise((r) => setTimeout(r, 1000));
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    });
    problems.push(...(await page.evaluate(probe, { floors: FLOORS, phone: vp.phone })));
    if (options.reducedMotion === "reduce") {
      const state = await page.evaluate(() => ({
        matches: matchMedia("(prefers-reduced-motion: reduce)").matches,
        running: document.getAnimations().filter((a) => a.playState === "running").length,
      }));
      if (!state.matches) problems.push("reduced motion: emulation not in effect");
      if (state.running) problems.push(`reduced motion: ${state.running} animations still running`);
    }
  } catch (err) {
    problems.push(`probe unavailable (${err.message}); judge this render from its screenshot`);
  }
  await page.screenshot({ path: path.join(outDir, `${vp.name}${suffix}.png`), fullPage: true });
  for (const p of problems) console.log(`${vp.name}${suffix}: ${p}`);
  await context.close();
  return problems.length === 0;
}

const browser = await chromium.launch();
let ok = true;
for (const vp of VIEWPORTS) ok = (await check(browser, vp, {}, "")) && ok;
ok = (await check(browser, VIEWPORTS[2], { reducedMotion: "reduce" }, "-reduced-motion")) && ok;
ok = (await check(browser, VIEWPORTS[0], { javaScriptEnabled: false }, "-no-js")) && ok;
ok = (await check(browser, VIEWPORTS[0], {}, "-grayscale", true)) && ok;
await browser.close();
console.log(ok ? "verify: all checks passed" : "verify: failures listed above");
process.exit(ok ? 0 : 1);
```

- Set `FLOORS` to the structural checker thresholds in use, and add each
  user-required outside asset to `ALLOWED`.
- The probe measures each text run (`<text>`, `<tspan>` or `<textPath>`) that
  holds its own text. It takes the rendered size from the computed font size
  times the smaller of the horizontal and vertical screen scales, so it stays
  correct under `viewBox` scaling, group transforms and non-uniform scaling.
- The probe reports a label that is hidden, transparent, unpainted (`fill: none`
  and `stroke: none`) or of zero size, and it compares overlaps only between
  different `<text>` elements.
- The probe needs the markup and `data-node` hooks the generator emits. For a
  page under review that lacks them, adapt the selectors and report the
  adaptation in the coverage field.
- Treat a reported overlap between an edge label and the line under it as a
  false alarm only after the screenshot shows the label on its background
  rectangle.
- A line that says the probe was unavailable is a failure to resolve by
  reviewing that screenshot, not a pass.

## Visual review checklist

Open every screenshot and check each item:

- **Text:** no clipped, overlapping or missing glyphs; no empty boxes in
  place of characters; no line starting with closing CJK punctuation; every
  label readable at 100% zoom.
- **Layout:** one layout per figure; no horizontal scroll; consistent column
  margins; balanced space around and inside figures; nothing crowded against
  a container edge.
- **Arrows:** every arrowhead present and meeting its target with the 3-unit
  gap from [Arrow routing](visual-system.md#arrow-routing); no edge through
  a node or label; flow in the reading direction of the layout.
- **Hierarchy:** one focal group visible at a glance in each figure; planned,
  inferred, estimated and placeholder marks visible; every encoding present in
  the legend.
- **Color:** the page palette only; no gradient, glow or heavy shadow;
  statuses and categories still distinct in the grayscale screenshot.
- **Text budget:** each section shows only its number, heading, lead sentence,
  optional badge and source links outside the figure.
- **Truth:** every number and status on screen appears in the fact table with
  its source.

## Reduced motion, no-JavaScript and grayscale renders

`verify.mjs` adds three render variants to the three viewports:

| Variant | Viewport | Setting | What must hold |
| --- | --- | --- | --- |
| `-reduced-motion` | phone | `reducedMotion: "reduce"` | the media query matches, no animation runs, and every figure shows at full opacity |
| `-no-js` | desktop | `javaScriptEnabled: false` | every figure shows at full opacity |
| `-grayscale` | desktop | `html { filter: grayscale(100%) }` | every status and category stays distinct by shape, line style or label |

## Running the structural checker

Run the structural checker from this skill's directory, where `<skill-dir>` is
the directory that holds this skill's `SKILL.md`:

```bash
python3 <skill-dir>/scripts/check_visual_html.py [options] <html-file> [...]
```

It needs Python 3 with the standard library only and takes no interactive
input. It classifies SVG layouts as
[Viewports and layout classes](#viewports-and-layout-classes) describes.

| Option | Default | Effect |
| --- | --- | --- |
| `--min-wide-font FLOAT` | `14.0` | minimum authored SVG font size, in px, in wide and single-layout SVGs |
| `--min-narrow-font FLOAT` | `12.5` | minimum authored SVG font size, in px, in narrow SVGs |
| `--max-section-chars INT` | `220` | maximum non-whitespace characters outside `<figure>` in a `<section>` that contains a `<figure>`, when CJK characters (Han, kana, Hangul, Bopomofo) make up at least 25% of that text's letters; `0` disables |
| `--max-section-words INT` | `65` | maximum whitespace-separated words outside `<figure>` in such a section for all other text, Latin or otherwise; `0` disables |
| `--forbid TEXT` | none | fails when the text appears in static HTML text (outside `[hidden]`, `<template>`, `<style>` and `<script>`), SVG `<text>` or non-hidden/non-template `aria-label`; repeatable (audit CSS-hidden HTML text with computed visibility in the browser probe) |
| `--allow-external-assets` | off | allows resources loaded from the network or from another file |
| `--allow-foreign-object` | off | allows `<foreignObject>` inside SVG |
| `--format text\|json` | `text` | output format |

- Exit code `0` means every file passed, `1` means at least one check failed,
  and `2` means a usage error or a file that could not be read or decoded.
- Without `--allow-external-assets`, every resource reference outside the page
  fails, whether it is a network URL or a relative path to another file. That
  covers `src`, `srcset`, a `<link href>` that loads a resource rather than
  naming a navigation target, CSS `url(...)` and `@import`, and SVG paint
  `url(...)`.
- `<a href>` links, `data:` URIs, `#fragment` references such as `url(#id)`,
  and SVG XML namespace URIs always pass.
- Text output starts with `OK:` or `FAIL:` and gives each failure as a block
  with the check name, file and location, then `Problem:`, `Expected:` and
  `Try:` lines. JSON output holds `ok`, `files` and `failures`, and each
  failure holds `file`, `location`, `check`, `problem`, `expected` and `fix`.
- The section budgets are a guardrail. The **Illustration over text** rule in
  `SKILL.md` is stricter: one lead sentence, not 65 words.
- Pass `--forbid` for each placeholder string, such as `TODO` or `lorem`, and
  for each retired or internal name the page must not show.

## PNG export protocol

`export.mjs` exports each two-layout figure twice, the wide layout at the
desktop viewport and the narrow layout at the phone viewport, and each
single-layout figure once, at the desktop viewport. For each capture it
requires exactly one visible SVG of the expected layout, disables transitions
and animations, waits two animation frames, and confirms opacity `'1'` on the
SVG and every ancestor. It then captures a whole-CSS-pixel clip at 2× device
scale and checks the PNG header against that clip. It exits with 1 on any
failure, and when it writes no PNG at all:

```js
// export.mjs: node export.mjs <page.html> <out-dir>
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [pageArg, outArg] = process.argv.slice(2);
if (!pageArg || !outArg) {
  console.error("usage: node export.mjs <page.html> <out-dir>");
  process.exit(2);
}
const url = pathToFileURL(path.resolve(pageArg)).href;
const outDir = path.resolve(outArg);
mkdirSync(outDir, { recursive: true });
const SCALE = 2;
const TARGETS = [
  { expect: "wide", viewport: { width: 1440, height: 900 } },
  { expect: "narrow", viewport: { width: 390, height: 844 } },
];
const NO_MOTION = "*, *::before, *::after { transition: none !important; animation: none !important; }";

function classify(fig) {
  const draw = "rect, circle, ellipse, line, polyline, polygon, path, text, image, use, foreignObject";
  const isDefsOnly = (svg) => {
    if ((svg.getAttribute("aria-hidden") || "").trim().toLowerCase() !== "true") return false;
    if (!svg.querySelector("defs")) return false;
    return ![...svg.querySelectorAll(draw)].some((el) => !el.closest("defs, symbol, marker, pattern, clipPath, mask"));
  };
  const svgs = [...fig.querySelectorAll("svg")].filter((s) => s.closest("figure") === fig && !isDefsOnly(s));
  const marked = (svg) => {
    const d = (svg.getAttribute("data-layout") || "").trim().toLowerCase();
    const c = new Set([...svg.classList].map((x) => x.toLowerCase()));
    if (d === "narrow" || c.has("narrow") || c.has("n")) return "narrow";
    if (d === "wide" || c.has("wide") || c.has("w")) return "wide";
    if (d === "single") return "single";
    return null;
  };
  const kinds = svgs.map((s) => marked(s) || (svgs.length === 1 ? "single" : "wide"));
  const visible = svgs.map((s, i) => [s, i]).filter(([s]) => {
    const cs = getComputedStyle(s);
    const r = s.getBoundingClientRect();
    return cs.display !== "none" && cs.visibility === "visible" && r.width > 0 && r.height > 0;
  }).map(([, i]) => i);
  return { id: fig.dataset.figure, kinds, visible, dual: kinds.includes("wide") && kinds.includes("narrow") };
}

const browser = await chromium.launch();
let ok = true;
let written = 0;
for (const t of TARGETS) {
  const context = await browser.newContext({ viewport: t.viewport, deviceScaleFactor: SCALE, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: NO_MOTION });
  const figures = await page.$$("figure[data-figure]");
  if (!figures.length) { console.log("export: no figure[data-figure] in the page"); ok = false; }
  const seenIds = new Set();
  for (const fig of figures) {
    const info = await fig.evaluate(classify);
    if (!info.id || seenIds.has(info.id)) {
      console.log(`export: missing or duplicate data-figure="${info.id || ""}"`);
      ok = false;
      continue;
    }
    seenIds.add(info.id);
    if (!info.dual && t.expect === "narrow") continue;   // single-layout figures export once
    if (info.visible.length !== 1) {
      console.log(`${info.id}: ${info.visible.length} SVGs visible at the ${t.expect} target, expected 1`);
      ok = false;
      continue;
    }
    const kind = info.kinds[info.visible[0]];
    if (info.dual && kind !== t.expect) {
      console.log(`${info.id}: ${kind} layout visible at the ${t.expect} target`);
      ok = false;
      continue;
    }
    const height = await fig.evaluate((f, idx) => {
      const draw = "rect, circle, ellipse, line, polyline, polygon, path, text, image, use, foreignObject";
      const isDefs = (s) => (s.getAttribute("aria-hidden") || "").trim().toLowerCase() === "true" && !!s.querySelector("defs") && ![...s.querySelectorAll(draw)].some((e) => !e.closest("defs, symbol, marker, pattern, clipPath, mask"));
      return [...f.querySelectorAll("svg")].filter((s) => s.closest("figure") === f && !isDefs(s))[idx].getBoundingClientRect().height;
    }, info.visible[0]);
    if (height + 2 > page.viewportSize().height) {
      await page.setViewportSize({ width: t.viewport.width, height: Math.ceil(height) + 2 });
    }
    await fig.evaluate((f, idx) => {
      const draw = "rect, circle, ellipse, line, polyline, polygon, path, text, image, use, foreignObject";
      const isDefs = (s) => (s.getAttribute("aria-hidden") || "").trim().toLowerCase() === "true" && !!s.querySelector("defs") && ![...s.querySelectorAll(draw)].some((e) => !e.closest("defs, symbol, marker, pattern, clipPath, mask"));
      [...f.querySelectorAll("svg")].filter((s) => s.closest("figure") === f && !isDefs(s))[idx].scrollIntoView({ block: "start" });
    }, info.visible[0]);
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const after = await fig.evaluate(classify);
    if (after.visible.length !== 1 || after.kinds[after.visible[0]] !== kind) {
      console.log(`${info.id}/${kind}: layout changed after resize/scroll (${after.visible.length} visible)`);
      ok = false;
      continue;
    }
    const checkTarget = await fig.evaluate((f, idx) => {
      const draw = "rect, circle, ellipse, line, polyline, polygon, path, text, image, use, foreignObject";
      const isDefs = (s) => (s.getAttribute("aria-hidden") || "").trim().toLowerCase() === "true" && !!s.querySelector("defs") && ![...s.querySelectorAll(draw)].some((e) => !e.closest("defs, symbol, marker, pattern, clipPath, mask"));
      const el = [...f.querySelectorAll("svg")].filter((s) => s.closest("figure") === f && !isDefs(s))[idx];
      for (let e = el; e; e = e.parentElement) {
        const o = getComputedStyle(e).opacity;
        if (o !== "1") return { hidden: `<${e.tagName.toLowerCase()}> has opacity ${o}` };
      }
      return { hidden: null, rect: el.getBoundingClientRect().toJSON() };
    }, after.visible[0]);
    if (checkTarget.hidden) { console.log(`${info.id}/${kind}: not exported, ${checkTarget.hidden}`); ok = false; continue; }
    const r = checkTarget.rect;
    const vp = page.viewportSize();
    if (r.left < -0.5 || r.top < -0.5 || r.right > vp.width + 0.5 || r.bottom > vp.height + 0.5) {
      console.log(`${info.id}/${kind}: SVG bounds (${r.left.toFixed(1)},${r.top.toFixed(1)}..${r.right.toFixed(1)},${r.bottom.toFixed(1)}) extend outside viewport ${vp.width}x${vp.height}`);
      ok = false;
      continue;
    }
    const x0 = Math.max(0, Math.floor(r.left));
    const y0 = Math.max(0, Math.floor(r.top));
    const clip = { x: x0, y: y0, width: Math.ceil(r.right) - x0, height: Math.ceil(r.bottom) - y0 };
    const file = path.join(outDir, `${info.id}-${kind}@2x.png`);
    const png = await page.screenshot({ path: file, clip, animations: "disabled" });
    const w = png.readUInt32BE(16);
    const h = png.readUInt32BE(20);
    if (w !== clip.width * SCALE || h !== clip.height * SCALE) {
      console.log(`${file}: PNG is ${w}x${h}, expected ${clip.width * SCALE}x${clip.height * SCALE}`);
      ok = false;
      continue;
    }
    console.log(`${file} ${w}x${h}`);
    written += 1;
  }
  await context.close();
}
await browser.close();
if (!written) { console.log("export: no PNG written"); ok = false; }
process.exit(ok ? 0 : 1);
```

- Do not force `opacity: 1` in the injected CSS. The opacity check must find a
  figure that a reveal script left hidden, so that the cause gets fixed in the
  generator.
- The script grows the viewport height, never its width, when a figure is
  taller than the viewport, so that the layout stays the same and the clip
  stays inside the viewport.
- Open every PNG and check it against the
  [Visual review checklist](#visual-review-checklist). A figure that exports
  blank, faded or cut off fails the export.

## Standalone embed blocks

Generate each embed block from the same figure builders as the page, for
example with a `--embed-dir` argument; never copy markup out of the generated
page by hand. Each block is a complete HTML document for an iframe:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  /* theme tokens, figure CSS, the reduced-motion block,
     and the breakpoint rule rewritten for the iframe width */
  html, body { margin: 0; background: var(--paper); }
  body { padding: 16px; }
</style>
</head>
<body>
<svg class="defs" aria-hidden="true" focusable="false" width="0" height="0" style="position:absolute">
  <defs><!-- the markers this figure uses --></defs>
</svg>
<figure class="vh-figure" data-figure="request-path">
  <svg class="wide" data-layout="wide" viewBox="0 0 960 420" role="img" aria-label="...">...</svg>
  <svg class="narrow" data-layout="narrow" viewBox="0 0 330 780" role="img" aria-label="...">...</svg>
</figure>
</body>
</html>
```

- Give each block its own shared defs with the markers its figure uses, and
  keep IDs unique within the block.
- Keep both layouts of a two-layout figure, or the one SVG of a single-layout
  figure. Media queries inside an iframe test the iframe's width, not the host
  page's width, so set the block's breakpoint to the wide `viewBox` width plus
  the block padding: 960 + 2 × 16 = 992px with the default values.
- Do not use `vh` units or `height: 100%` on `html` or `body`. A host that
  sizes the iframe to its content can otherwise grow it without limit.
- When the host's HTML block offers an iframe mode and an automatic height
  setting, such as `use-iframe` and `html-box-height-mode: auto`, enable both,
  so that the block renders isolated and its height follows its content.
- Run the structural checker on every block, and run `verify.mjs` on each
  block with its breakpoint as the third argument. Check the block's
  screenshots at the desktop and phone widths.
