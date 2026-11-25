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

| Name | Size | Expected layout in a two-layout figure |
| --- | --- | --- |
| desktop | 1440 × 900 | wide in each figure whose breakpoint is at most 1440 |
| breakpoint-*width* | each breakpoint width × 800, 1104 with the starting-point values | wide in each figure with that breakpoint |
| breakpoint-*width*-below | one pixel less than each breakpoint width × 800 | narrow in each figure with that breakpoint |
| tablet | 768 × 1024 | narrow in each figure whose breakpoint is above 768 |
| above-phone | 391 × 844 | narrow in each figure whose breakpoint is above 391 |
| phone | 390 × 844 | narrow in each figure whose breakpoint is above 390 |
| small-phone | 360 × 800 | narrow in every two-layout figure |

- These viewports sample the supported width range, every width from 360px
  up, in which **Maximum readability** in `SKILL.md` requires the font floors,
  the lead-size limit and one rendered size for each kind of text. At each
  viewport up to 390px wide, a single-layout SVG has the narrow floor; at each
  wider viewport, it has the wide floor.
- At each viewport, a two-layout figure shows its wide layout when the
  viewport is at least as wide as the figure's breakpoint, and its narrow
  layout otherwise. A figure's breakpoint is its `data-breakpoint` value, or
  the page breakpoint when it has none. A breakpoint is a whole number of CSS
  pixels of at least 361, so that the viewport one pixel below it is still in
  the supported range; `verify.mjs` and `export.mjs` reject any other value.
- Pass the page breakpoint to `verify.mjs` and `export.mjs` when it differs
  from 1104. `verify.mjs` reads each figure's `data-breakpoint` from the page
  and renders both sides of every breakpoint.
- `verify.mjs`, `export.mjs` and the structural checker classify each diagram
  SVG associated with its nearest enclosing `<figure>` the same way (class
  tokens matched case-insensitively). They consider only outer SVGs, not an
  SVG nested inside another SVG. Only a definitions-only SVG — one with
  `aria-hidden="true"`, a `<defs>` element and no renderable graphics outside
  `<defs>` — is skipped. Every other SVG, including a legend sample glyph
  outside a `<figure>`, needs `role="img"`, an `aria-label` and a `viewBox`.
  - **Narrow:** `data-layout="narrow"`, or class `narrow` or `n`.
  - **Wide:** `data-layout="wide"`, or class `wide` or `w`.
  - **Single:** `data-layout="single"`, or an unmarked SVG that is the only
    diagram SVG in its figure.
  - An unmarked SVG beside other diagram SVGs counts as wide.
- Each figure with a diagram SVG holds exactly one single-layout SVG, or
  exactly one wide SVG and one narrow SVG. `verify.mjs` and `export.mjs`
  report a figure with any other set of layouts before they check its
  visibility or export it. At each
  viewport, exactly one SVG of each figure must be visible, and in a
  two-layout figure it must be the expected layout.

## DOM geometry probe

`verify.mjs` renders the page at each viewport and in each render variant,
scrolls through it, runs the probe, writes one full-page screenshot per run,
and exits with 1 when any check fails:

```js
// verify.mjs: [VH_EMBED_LEAD_PX=<px>] node verify.mjs <page.html> <out-dir> [page-breakpoint-width]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const USAGE = "usage: [VH_EMBED_LEAD_PX=<px>] node verify.mjs <page.html> <out-dir> [page-breakpoint-width]";
const WHOLE = /^\s*[1-9]\d*\s*$/;
const MIN_BREAKPOINT = 361; // one pixel below it is still a supported width
const usableBreakpoint = (v) => WHOLE.test(v) && Number(v) >= MIN_BREAKPOINT;
const [pageArg, outArg, bpArg] = process.argv.slice(2);
if (!pageArg || !outArg) {
  console.error(USAGE);
  process.exit(2);
}
if (bpArg !== undefined && !usableBreakpoint(bpArg)) {
  console.error(`the page breakpoint must be a whole CSS pixel width of at least ${MIN_BREAKPOINT}; got "${bpArg}"\n${USAGE}`);
  process.exit(2);
}
const PAGE_BREAKPOINT = Number(bpArg || 1104);
const EMBED_LEAD_PX = process.env.VH_EMBED_LEAD_PX === undefined ? null : Number(process.env.VH_EMBED_LEAD_PX);
if (EMBED_LEAD_PX !== null && !(EMBED_LEAD_PX > 0)) {
  console.error(`VH_EMBED_LEAD_PX must be the embed limit in CSS px; got "${process.env.VH_EMBED_LEAD_PX}"\n${USAGE}`);
  process.exit(2);
}
const url = pathToFileURL(path.resolve(pageArg)).href;
const outDir = path.resolve(outArg);
mkdirSync(outDir, { recursive: true });
const FLOORS = { wide: 14, narrow: 12.5 };
const SINGLE_NARROW_MAX = 390; // widest viewport at which a single-layout SVG has the narrow floor
const KIND_SPREAD = 1.05; // largest over smallest rendered size allowed for one kind of text
const ALLOWED = []; // URL prefixes of outside assets the user required
const allowed = (u) => u === url || u.startsWith("data:") || ALLOWED.some((p) => u.startsWith(p));

function probe({ floors, singleNarrowMax, kindSpread, pageBreakpoint, minBreakpoint, embedLeadPx }) {
  const problems = [];
  const sizesByKind = new Map(); // data-text-kind -> [[rendered px, where]]
  const root = document.documentElement;
  if (root.scrollWidth > innerWidth + 1) {
    problems.push(`page overflow: scrollWidth ${root.scrollWidth} > ${innerWidth}`);
  }
  const whole = /^\s*[1-9]\d*\s*$/;
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
    const svgs = [...fig.querySelectorAll("svg")].filter(
      (s) => s.closest("figure") === fig && !s.parentElement.closest("svg") && !isDefsOnly(s),
    );
    if (!svgs.length) continue;
    const kinds = svgs.map((s) => marked(s) || (svgs.length === 1 ? "single" : "wide"));
    const set = [...kinds].sort().join("+");
    if (set !== "single" && set !== "narrow+wide") {
      problems.push(`${name}: layouts ${kinds.join(", ")}; expected one single-layout SVG, or one wide and one narrow SVG`);
      continue;
    }
    const dual = set === "narrow+wide";
    const rawBreakpoint = fig.getAttribute("data-breakpoint");
    if (rawBreakpoint !== null && !(whole.test(rawBreakpoint) && Number(rawBreakpoint) >= minBreakpoint)) {
      problems.push(`${name}: data-breakpoint "${rawBreakpoint}" is not a whole CSS pixel width of at least ${minBreakpoint}`);
      continue;
    }
    const section = fig.closest("section");
    const leadEl = section && section.querySelector(".vh-lead");
    const lead = embedLeadPx ?? (leadEl ? parseFloat(getComputedStyle(leadEl).fontSize) : null);
    if (!lead) {
      problems.push(section
        ? `${name}: no .vh-lead lead sentence in its section to compare label sizes with`
        : `${name}: outside any <section>; put each figure of a page in a section with a .vh-lead lead sentence`);
    }
    const breakpoint = rawBreakpoint === null ? pageBreakpoint : Number(rawBreakpoint);
    const expected = dual ? (innerWidth < breakpoint ? "narrow" : "wide") : null;
    const visible = svgs.filter(shown);
    if (visible.length !== 1) {
      problems.push(`${name}: ${visible.length} SVGs visible, expected 1`);
      continue;
    }
    const svg = visible[0];
    const kind = kinds[svgs.indexOf(svg)];
    if (expected && kind !== expected) problems.push(`${name}: ${kind} layout visible, expected ${expected}`);
    const floor = kind === "narrow" || (kind === "single" && innerWidth <= singleNarrowMax) ? floors.narrow : floors.wide;
    for (let el = svg; el; el = el.parentElement) {
      const o = getComputedStyle(el).opacity;
      if (o !== "1") problems.push(`${name}/${kind}: <${el.tagName.toLowerCase()}> has opacity ${o}`);
    }
    const svgBox = svg.getBoundingClientRect();
    const runs = [];
    for (const el of svg.querySelectorAll("text, tspan, textPath")) {
      if (el.closest("defs, symbol")) continue; // rendered only through <use>
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
      const scales = [Math.hypot(m.a, m.b), Math.hypot(m.c, m.d)];
      const px = parseFloat(cs.fontSize) * Math.min(...scales);
      const pxMax = parseFloat(cs.fontSize) * Math.max(...scales);
      const textEl = el.closest("text");
      const display = textEl.hasAttribute("data-display");
      if (px < floor - 0.01) problems.push(`${where}: renders at ${px.toFixed(2)}px, floor ${floor}px`);
      if (lead && pxMax >= lead && !display) {
        problems.push(`${where}: renders at up to ${pxMax.toFixed(2)}px, not below the ${lead}px lead sentence`);
      }
      const textKind = textEl.getAttribute("data-text-kind");
      if (textKind && !display) {
        if (!sizesByKind.has(textKind)) sizesByKind.set(textKind, []);
        sizesByKind.get(textKind).push([px, where]);
      }
      if (!inside(box, svgBox)) problems.push(`${where}: outside its SVG`);
      const shape = el.closest("[data-node]")?.querySelector(":scope > rect");
      if (shape && !inside(box, shape.getBoundingClientRect())) problems.push(`${where}: overflows its node`);
      runs.push([where, box, textEl]);
    }
    for (let i = 0; i < runs.length; i++) {
      for (let j = i + 1; j < runs.length; j++) {
        if (runs[i][2] !== runs[j][2] && overlap(runs[i][1], runs[j][1])) {
          problems.push(`${runs[i][0]} overlaps ${runs[j][0]}`);
        }
      }
    }
  }
  for (const [textKind, sizes] of sizesByKind) {
    const lo = sizes.reduce((a, b) => (b[0] < a[0] ? b : a));
    const hi = sizes.reduce((a, b) => (b[0] > a[0] ? b : a));
    if (hi[0] > lo[0] * kindSpread + 1e-6) {
      problems.push(`text kind "${textKind}": ${lo[0].toFixed(2)}px at ${lo[1]} and ${hi[0].toFixed(2)}px at ${hi[1]}, ` +
        `more than ${Math.round((kindSpread - 1) * 100)}% apart`);
    }
  }
  return problems;
}

async function check(browser, vp, options, suffix, grayscale = false) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, ...options });
  const page = await context.newPage();
  const problems = [];
  page.on("console", (msg) => { if (msg.type() === "error") problems.push(`console: ${msg.text()}`); });
  page.on("pageerror", (err) => problems.push(`page error: ${err.message}`));
  page.on("request", (req) => { if (!allowed(req.url())) problems.push(`request outside the page: ${req.url()}`); });
  await context.route(/^https?:/, (route) => (allowed(route.request().url()) ? route.continue() : route.abort()));
  await page.goto(url, { waitUntil: "load" });
  if (grayscale) await page.addStyleTag({ content: "html { filter: grayscale(100%) !important; }" });
  try {
    // Timers and animation frames never fire with JavaScript disabled.
    if (options.javaScriptEnabled !== false) await page.evaluate(async () => {
      await document.fonts.ready;
      for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight / 2) {
        scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 150));
      }
      scrollTo(0, 0);
      await new Promise((r) => setTimeout(r, 1000));
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    });
    problems.push(...(await page.evaluate(probe, {
      floors: FLOORS, singleNarrowMax: SINGLE_NARROW_MAX, kindSpread: KIND_SPREAD,
      pageBreakpoint: PAGE_BREAKPOINT, minBreakpoint: MIN_BREAKPOINT, embedLeadPx: EMBED_LEAD_PX,
    })));
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
// Read each figure's own breakpoint, so that both sides of every breakpoint are rendered.
const declared = await (async () => {
  const context = await browser.newContext();
  await context.route(/^https?:/, (route) => (allowed(route.request().url()) ? route.continue() : route.abort()));
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "load" });
  const values = await page.evaluate(() =>
    [...document.querySelectorAll("figure[data-breakpoint]")].map((f) => f.getAttribute("data-breakpoint")));
  await context.close();
  return values;
})();
const widths = [...new Set([PAGE_BREAKPOINT, ...declared.filter(usableBreakpoint).map(Number)])];
const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  ...widths.sort((a, b) => b - a).flatMap((w) => [
    { name: `breakpoint-${w}`, width: w, height: 800 },
    { name: `breakpoint-${w}-below`, width: w - 1, height: 800 },
  ]),
  { name: "tablet", width: 768, height: 1024 },
  { name: "above-phone", width: SINGLE_NARROW_MAX + 1, height: 844 },
  { name: "phone", width: 390, height: 844 },
  { name: "small-phone", width: 360, height: 800 },
];
const DESKTOP = VIEWPORTS[0];
const PHONE = VIEWPORTS.find((vp) => vp.name === "phone");
for (const vp of VIEWPORTS) ok = (await check(browser, vp, {}, "")) && ok;
ok = (await check(browser, PHONE, { reducedMotion: "reduce" }, "-reduced-motion")) && ok;
ok = (await check(browser, DESKTOP, { javaScriptEnabled: false }, "-no-js")) && ok;
ok = (await check(browser, DESKTOP, {}, "-grayscale", true)) && ok;
await browser.close();
console.log(ok ? "verify: all checks passed" : "verify: failures listed above");
process.exit(ok ? 0 : 1);
```

- Set `FLOORS` to the structural checker thresholds in use, and add each
  user-required outside asset to `ALLOWED`.
- The probe measures each text run (`<text>`, `<tspan>` or `<textPath>`) that
  holds its own text. It multiplies the computed font size by the smaller of
  the horizontal and vertical screen scales for the font floor and by the
  larger for the lead-size limit, so it stays correct under `viewBox` scaling,
  group transforms and non-uniform scaling.
- The probe skips text inside `<defs>` and `<symbol>`, and does not measure
  text drawn through `<use>` from a symbol or a shared def. Check such text in
  the screenshots, or draw it as `<text>` in the figure.
- The probe reports a label that is hidden, transparent, unpainted (`fill: none`
  and `stroke: none`) or of zero size, and it compares overlaps only between
  different `<text>` elements.
- The probe compares each figure's text with the computed font size of the
  `.vh-lead` element in the figure's `<section>`, and reports a figure outside
  any `<section>` or in a section without one. It exempts only a `<text>`
  element that carries `data-display`, with its `<tspan>` children. With
  `VH_EMBED_LEAD_PX` set, it compares the text of every figure with that one
  value instead; set it only for an embed block, as
  [Standalone embed blocks](#standalone-embed-blocks) directs.
- The probe groups the text runs of the visible SVGs by the `data-text-kind`
  of their `<text>` element, display text apart, and reports each kind whose
  largest rendered size is more than 5% above its smallest. It does not
  compare text without the hook. It groups by the hook because one authored
  size can belong to different kinds in different layouts: 14 units is a wide
  node detail and a narrow node title.
- The probe needs the markup, the `vh-lead` class and the `data-node` and
  `data-text-kind` hooks the generator emits. For a page under review that lacks them, adapt the
  selectors and report the adaptation in the coverage field.
- `verify.mjs` overwrites the screenshots in its output directory. Give each
  run in the design review of pass 4 in `SKILL.md` a new output directory, so
  that the screenshots kept for comparison stay unchanged.
- Treat a reported overlap between an edge label and the line under it as a
  false alarm only after the screenshot shows the label on its plate.
- A line that says the probe was unavailable is a failure to resolve by
  reviewing that screenshot, not a pass.

## Visual review checklist

Open every screenshot and check each item:

- **Text:** no clipped, overlapping or missing glyphs; no empty boxes in
  place of characters; no line starting with closing CJK punctuation; every
  label readable at 100% zoom; text in each figure, apart from display text,
  smaller than its section's lead sentence at every viewport, the tablet one
  included; each kind of text the same size in every figure.
- **Layout:** one layout per figure; no horizontal scroll; consistent column
  margins; balanced space around and inside figures; nothing crowded against
  a container edge.
- **Lines:** every arrowhead present, in its line's color and meeting its
  target; no line through a node it does not connect to; each label on a line
  set on its plate; no two parallel lines merged into one double line; the
  lines that carry the diagram in the palette's second ink, apart from the
  focal, semantic and receding lines.
- **Hierarchy:** one focal group in each figure, the strongest visual mass of
  that figure; planned, inferred, estimated and placeholder marks visible;
  every encoding the page uses explained once.
- **Color:** the fixed colors and the hues chosen for the page only; no
  gradient, glow or heavy shadow; no two categories told apart by red against
  green alone; statuses and categories still distinct in the grayscale
  screenshot.
- **Text budget:** each section shows only its number, heading, lead sentence,
  optional badge and source links outside the figure.
- **Truth:** every number and status on screen appears in the fact table with
  its source.

## Reduced motion, no-JavaScript and grayscale renders

`verify.mjs` adds three render variants to the viewport runs:

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
- `--max-section-words` and `--max-section-chars` enforce the word and
  character limits of **Illustration over text** in `SKILL.md`. The checker
  does not check that the text is one lead sentence.
- The checker applies the SVG font floors to every CSS rule that sets a font
  size on SVG text, inside any media query. It accepts a rule below a layout's
  floor only when all of these hold: the rule sits outside any `@layer`
  block, whose cascade layer the checker does not model; the rule's selector
  uses no pseudo-class other than `:root` and `:first-child`; no font size in the page's CSS
  uses `var()`, whose value the checker does not resolve; and every element
  of that layout that the rule matches also gets a size at or above the floor
  from a rule that wins the cascade over it by importance, specificity and
  order. The winning rule sits outside any at-rule, any `<style media>`
  element and any `<noscript>` element, and meets the same pseudo-class limit. Scope a narrow-only size to the narrow SVG,
  as in `svg.narrow text`, or meet that condition.
- Pass `--forbid` for each placeholder string, such as `TODO` or `lorem`, and
  for each retired or internal name the page must not show.

## PNG export protocol

`export.mjs` exports each two-layout figure twice, the wide layout at the
desktop width and the narrow layout at the phone width, and each single-layout
figure once, at the desktop width. For a figure whose breakpoint is above the
desktop width, it exports the wide layout at the breakpoint width instead, and
for one whose breakpoint is at or below the phone width, it exports the narrow
layout one pixel below the breakpoint, so that each capture shows the
requested layout. Before it plans the captures, it reports and skips each
figure whose set of layouts or whose breakpoint
[Viewports and layout classes](#viewports-and-layout-classes) does not allow.
For each capture it requires exactly one visible SVG of the
expected layout, disables transitions and animations, waits two animation
frames, and confirms opacity `'1'` on the SVG and every ancestor. It then
captures a whole-CSS-pixel clip at 2× device scale and checks the PNG header
against that clip. It exits with 1 on any failure, and when it writes no PNG
at all:

```js
// export.mjs: node export.mjs <page.html> <out-dir> [page-breakpoint-width]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const USAGE = "usage: node export.mjs <page.html> <out-dir> [page-breakpoint-width]";
const WHOLE = /^\s*[1-9]\d*\s*$/;
const MIN_BREAKPOINT = 361; // one pixel below it is still a supported width
const usableBreakpoint = (v) => WHOLE.test(v) && Number(v) >= MIN_BREAKPOINT;
const [pageArg, outArg, bpArg] = process.argv.slice(2);
if (!pageArg || !outArg) {
  console.error(USAGE);
  process.exit(2);
}
if (bpArg !== undefined && !usableBreakpoint(bpArg)) {
  console.error(`the page breakpoint must be a whole CSS pixel width of at least ${MIN_BREAKPOINT}; got "${bpArg}"\n${USAGE}`);
  process.exit(2);
}
const PAGE_BREAKPOINT = Number(bpArg || 1104);
const url = pathToFileURL(path.resolve(pageArg)).href;
const outDir = path.resolve(outArg);
mkdirSync(outDir, { recursive: true });
const SCALE = 2;
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const NO_MOTION = "*, *::before, *::after { transition: none !important; animation: none !important; }";

function classify(fig) {
  const draw = "rect, circle, ellipse, line, polyline, polygon, path, text, image, use, foreignObject";
  const isDefsOnly = (svg) => {
    if ((svg.getAttribute("aria-hidden") || "").trim().toLowerCase() !== "true") return false;
    if (!svg.querySelector("defs")) return false;
    return ![...svg.querySelectorAll(draw)].some((el) => !el.closest("defs, symbol, marker, pattern, clipPath, mask"));
  };
  const svgs = [...fig.querySelectorAll("svg")].filter((s) => s.closest("figure") === fig && !s.parentElement.closest("svg") && !isDefsOnly(s));
  const marked = (svg) => {
    const d = (svg.getAttribute("data-layout") || "").trim().toLowerCase();
    const c = new Set([...svg.classList].map((x) => x.toLowerCase()));
    if (d === "narrow" || c.has("narrow") || c.has("n")) return "narrow";
    if (d === "wide" || c.has("wide") || c.has("w")) return "wide";
    if (d === "single") return "single";
    return null;
  };
  const kinds = svgs.map((s) => marked(s) || (svgs.length === 1 ? "single" : "wide"));
  const set = [...kinds].sort().join("+");
  const visible = svgs.map((s, i) => [s, i]).filter(([s]) => {
    const cs = getComputedStyle(s);
    const r = s.getBoundingClientRect();
    return cs.display !== "none" && cs.visibility === "visible" && r.width > 0 && r.height > 0;
  }).map(([, i]) => i);
  return { id: fig.dataset.figure, kinds, visible, valid: set === "single" || set === "narrow+wide", dual: set === "narrow+wide" };
}

const browser = await chromium.launch();
let ok = true;
let written = 0;
// Choose, for each figure, the widths at which its wide and its narrow layout show.
const plan = await (async () => {
  const context = await browser.newContext({ viewport: DESKTOP });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "load" });
  const figs = [];
  for (const fig of await page.$$("figure[data-figure]")) {
    figs.push([await fig.evaluate(classify), await fig.getAttribute("data-breakpoint")]);
  }
  await context.close();
  return figs;
})();
if (!plan.length) { console.log("export: no figure[data-figure] in the page"); ok = false; }
const WIDTHS = new Map(); // figure id -> { wide, narrow }
for (const [{ id, kinds, valid }, raw] of plan) {
  if (!valid) {
    console.log(`${id}: layouts ${kinds.join(", ") || "none"}; expected one single-layout SVG, or one wide and one narrow SVG`);
    ok = false;
    continue;
  }
  if (raw !== null && !usableBreakpoint(raw)) {
    console.log(`${id}: data-breakpoint "${raw}" is not a whole CSS pixel width of at least ${MIN_BREAKPOINT}`);
    ok = false;
    continue;
  }
  const bp = raw === null ? PAGE_BREAKPOINT : Number(raw);
  if (!WIDTHS.has(id)) WIDTHS.set(id, { wide: Math.max(DESKTOP.width, bp), narrow: Math.min(PHONE.width, bp - 1) });
}
const TARGETS = [];
for (const widths of WIDTHS.values()) {
  for (const expect of ["wide", "narrow"]) {
    const height = (expect === "wide" ? DESKTOP : PHONE).height;
    if (!TARGETS.some((t) => t.expect === expect && t.viewport.width === widths[expect])) {
      TARGETS.push({ expect, viewport: { width: widths[expect], height } });
    }
  }
}
for (const t of TARGETS) {
  const context = await browser.newContext({ viewport: t.viewport, deviceScaleFactor: SCALE, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: NO_MOTION });
  const figures = await page.$$("figure[data-figure]");
  const seenIds = new Set();
  for (const fig of figures) {
    const info = await fig.evaluate(classify);
    if (!info.id || seenIds.has(info.id)) {
      console.log(`export: missing or duplicate data-figure="${info.id || ""}"`);
      ok = false;
      continue;
    }
    seenIds.add(info.id);
    if (WIDTHS.get(info.id)?.[t.expect] !== t.viewport.width) continue; // exported at another width
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
      return [...f.querySelectorAll("svg")].filter((s) => s.closest("figure") === f && !s.parentElement.closest("svg") && !isDefs(s))[idx].getBoundingClientRect().height;
    }, info.visible[0]);
    if (height + 2 > page.viewportSize().height) {
      await page.setViewportSize({ width: t.viewport.width, height: Math.ceil(height) + 2 });
    }
    await fig.evaluate((f, idx) => {
      const draw = "rect, circle, ellipse, line, polyline, polygon, path, text, image, use, foreignObject";
      const isDefs = (s) => (s.getAttribute("aria-hidden") || "").trim().toLowerCase() === "true" && !!s.querySelector("defs") && ![...s.querySelectorAll(draw)].some((e) => !e.closest("defs, symbol, marker, pattern, clipPath, mask"));
      [...f.querySelectorAll("svg")].filter((s) => s.closest("figure") === f && !s.parentElement.closest("svg") && !isDefs(s))[idx].scrollIntoView({ block: "start" });
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
      const el = [...f.querySelectorAll("svg")].filter((s) => s.closest("figure") === f && !s.parentElement.closest("svg") && !isDefs(s))[idx];
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
  figure { margin-inline: 0; }
</style>
</head>
<body>
<svg class="defs" aria-hidden="true" focusable="false" width="0" height="0" style="position:absolute">
  <defs><!-- the markers this figure uses --></defs>
</svg>
<figure class="vh-figure" data-figure="request-path">
  <svg class="wide" data-layout="wide" viewBox="0 0 960 420" style="max-width:1008px" role="img" aria-label="...">...</svg>
  <svg class="narrow" data-layout="narrow" viewBox="0 0 300 780" style="max-width:360px" role="img" aria-label="...">...</svg>
</figure>
</body>
</html>
```

- Give each block its own shared defs with the markers its figure uses, and
  keep IDs unique within the block.
- Keep both layouts of a two-layout figure, or the one SVG of a single-layout
  figure, each with its scale cap. Media queries inside an iframe test the
  iframe's width, not the host page's width, so set the block's breakpoint
  where the figure content box equals the wide SVG's cap, as on the page: the
  cap plus the horizontal padding, borders and margins of `body` and the
  figure. With the 16px `body` padding above, the starting-point 16px figure
  padding at the wide layout and no figure margin or border, that is
  1008 + 2 × 16 + 2 × 16 = 1072px. Below it, with the 12px narrow figure
  padding, the content box at 360px is 360 − 2 × 16 − 2 × 12 = 304px, as on
  the page.
- Do not use `vh` units or `height: 100%` on `html` or `body`. A host that
  sizes the iframe to its content can otherwise grow it without limit.
- When the host's HTML block offers an iframe mode and an automatic height
  setting, such as `use-iframe` and `html-box-height-mode: auto`, enable both,
  so that the block renders isolated and its height follows its content.
- Run the structural checker on every block. Run `verify.mjs` on each block
  with its breakpoint as the third argument and `VH_EMBED_LEAD_PX` set to the
  embed limit: the smallest computed size of the page's lead sentences across
  the verification viewports, 17 with the starting-point type scale. The probe
  then holds the block's figure text, display text apart, below that one
  limit at every width, because the block holds no lead sentence and its host
  decides which text appears beside it. Check the block's screenshots at the
  desktop and phone widths.
