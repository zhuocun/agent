// Audit global teardown: aggregate per-capture JSON into probes.json and a
// human-readable probes.md, and fail the run when two DISTINCT surfaces
// (different surface, viewport or theme) produced byte-identical PNGs — the
// signature of a surface that never rendered (visual-ux-sweep skill, "Verify
// the capture"). Same-surface duplicates across media variants are expected
// (reduced-motion of a static frame is pixel-identical) and only noted.

import fs from "node:fs";
import path from "node:path";

const AUDIT_DIR = path.resolve(__dirname, "..", "..", "test-results", "audit");

/* eslint-disable @typescript-eslint/no-explicit-any */
type Rec = any;

function mdEscape(s: string): string {
  return String(s ?? "").replace(/\|/g, "\\|").replace(/\n/g, " ");
}

export default async function globalTeardown(): Promise<void> {
  const capDir = path.join(AUDIT_DIR, "captures");
  if (!fs.existsSync(capDir)) return;
  const recs: Rec[] = fs
    .readdirSync(capDir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(fs.readFileSync(path.join(capDir, f), "utf8")))
    .sort((a, b) => a.name.localeCompare(b.name));
  fs.writeFileSync(path.join(AUDIT_DIR, "probes.json"), JSON.stringify(recs, null, 2));

  const L: string[] = [];
  const ok = recs.filter((r) => r.ok);
  const failed = recs.filter((r) => !r.ok);
  L.push("# UI audit — probe summary", "");
  L.push(`Generated ${new Date().toISOString()} by \`pnpm audit:ui\` (web/tests/audit). Raw data: \`probes.json\`; screenshots: \`shots/<viewport>/<theme>/<surface>[__<media>].png\`.`, "");
  L.push(`- Captures: **${recs.length}** (${ok.length} ok, ${failed.length} failed)`);
  const pngs = recs.filter((r) => r.file && r.file.endsWith(".png")).length;
  L.push(`- PNGs recorded in captures: ${pngs} (focus crops under \`focus/\` are extra)`, "");

  // ── Render verification ────────────────────────────────────────────────
  L.push("## Render verification (PNG hashes)", "");
  const byHash = new Map<string, Rec[]>();
  for (const r of ok) {
    if (!r.md5) continue;
    const list = byHash.get(r.md5) ?? [];
    list.push(r);
    byHash.set(r.md5, list);
  }
  const distinctDup: string[] = [];
  const benignDup: string[] = [];
  for (const [hash, list] of byHash) {
    if (list.length < 2) continue;
    const keys = new Set(list.map((r: Rec) => `${r.surface}|${r.viewport}|${r.theme}`));
    const line = `\`${hash.slice(0, 8)}\`: ${list.map((r: Rec) => r.name).join(", ")}`;
    if (keys.size > 1) {
      // Allowed: the "-focus-end"/"-pdf-meta" bookkeeping shots duplicate the
      // frame they follow, and "stopped" can equal nothing else.
      const real = list.filter((r: Rec) => !/(focus-end|pdf-meta)$/.test(r.surface));
      const realKeys = new Set(real.map((r: Rec) => `${r.surface}|${r.viewport}|${r.theme}`));
      if (realKeys.size > 1) distinctDup.push(line);
      else benignDup.push(line);
    } else benignDup.push(line);
  }
  L.push(distinctDup.length ? `**FAIL — distinct surfaces with identical PNGs (${distinctDup.length}):**` : "No two distinct surfaces share a PNG hash.", "");
  distinctDup.forEach((d) => L.push(`- ${d}`));
  if (benignDup.length) {
    L.push("", `Same-surface duplicates across media variants / bookkeeping shots (expected, ${benignDup.length}):`, "");
    benignDup.forEach((d) => L.push(`- ${d}`));
  }
  L.push("");

  // ── Capture failures ───────────────────────────────────────────────────
  L.push("## Capture failures", "");
  if (!failed.length) L.push("None.");
  for (const r of failed) L.push(`- \`${r.name}\` — ${mdEscape(r.error)} (diagnostic: \`${r.file}\`)`);
  L.push("");

  // ── Overflow ───────────────────────────────────────────────────────────
  L.push("## Horizontal overflow (UI-LAYOUT-1)", "");
  L.push("`pageOverflows` = `scrollingElement.scrollWidth > clientWidth + 1`. Offenders = visible elements whose box crosses the viewport edge and are not inside a horizontally clipping/scrolling ancestor. **Noise:** off-canvas chrome that is partly on-screen during a transition, and decorative glows with negative insets, can appear as offenders without causing page scroll — confirm in the PNG.", "");
  const ovf = ok.filter((r) => r.probe && (r.probe.overflow.pageOverflows || r.probe.overflow.offenders.length));
  if (!ovf.length) L.push("None.");
  for (const r of ovf) {
    const o = r.probe.overflow;
    L.push(`- \`${r.name}\` — page ${o.pageOverflows ? `**OVERFLOWS** (${o.scrollWidth} > ${o.clientWidth})` : "ok"}; ${o.offenders.length} offender(s): ${o.offenders.slice(0, 4).map((x: Rec) => `\`${mdEscape(x.sel)}\` [${x.left}→${x.right}] "${mdEscape(x.text)}"`).join("; ")}`);
  }
  L.push("");

  // ── Targets ────────────────────────────────────────────────────────────
  L.push("## Undersized targets (UI-TOUCH-1 44 px touch / UI-TOUCH-2 24 px pointer)", "");
  L.push("Measured on `getBoundingClientRect()` expanded by any absolutely positioned `::before/::after` hit-slop. Pointer viewports apply the WCAG 2.5.8 spacing exception (`spacingOk`) and the inline-link exception. **Noise:** controls inside a scroll container that are partly scrolled out still count; composite widgets whose hit region is a parent label are measured on the inner element.", "");
  const tgt = new Map<string, { sel: string; text: string; sizes: Set<string>; where: Set<string>; vps: Set<string> }>();
  for (const r of ok) {
    if (!r.probe) continue;
    for (const t of r.probe.targets.small) {
      if (t.inline) continue;
      if (!r.probe.facts.hoverNone && t.spacingOk) continue;
      const key = `${r.probe.targets.floor}|${t.sel}|${t.text}`;
      const e = tgt.get(key) ?? { sel: t.sel, text: t.text, sizes: new Set(), where: new Set(), vps: new Set() };
      e.sizes.add(`${t.w}×${t.h}`);
      e.where.add(r.surface);
      e.vps.add(r.viewport);
      tgt.set(key, e);
    }
  }
  const tgtRows = Array.from(tgt.entries()).sort((a, b) => b[1].where.size - a[1].where.size);
  L.push(`${tgtRows.length} distinct undersized target(s) after exceptions.`, "");
  L.push("| floor | selector | label | sizes | viewports | surfaces |", "| --- | --- | --- | --- | --- | --- |");
  for (const [key, e] of tgtRows.slice(0, 80)) {
    L.push(`| ${key.split("|")[0]} | \`${mdEscape(e.sel)}\` | ${mdEscape(e.text)} | ${Array.from(e.sizes).slice(0, 3).join(", ")} | ${Array.from(e.vps).join(" ")} | ${Array.from(e.where).slice(0, 6).join(", ")}${e.where.size > 6 ? ` +${e.where.size - 6}` : ""} |`);
  }
  if (tgtRows.length > 80) L.push("", `…${tgtRows.length - 80} more in probes.json.`);
  L.push("");

  // ── Axe ────────────────────────────────────────────────────────────────
  L.push("## axe-core (WCAG 2.0/2.1/2.2 A+AA tags)", "");
  L.push("Base media only. **Noise:** `color-contrast` over translucent glass and gradient backgrounds is often reported as `incomplete` rather than a violation (not listed); violations on `aria-hidden` focusables inside animating overlays can be transient.", "");
  const axe = new Map<string, { impact: string; help: string; nodes: number; where: Set<string>; targets: Set<string> }>();
  for (const r of ok) {
    for (const v of r.axe ?? []) {
      const e = axe.get(v.id) ?? { impact: v.impact, help: v.help, nodes: 0, where: new Set(), targets: new Set() };
      e.nodes += v.nodes;
      e.where.add(`${r.viewport}/${r.theme}/${r.surface}`);
      for (const t of v.targets) if (e.targets.size < 8) e.targets.add(`${t.target} — ${t.summary}`);
      axe.set(v.id, e);
    }
  }
  if (!axe.size) L.push("No violations.");
  for (const [id, e] of Array.from(axe.entries()).sort((a, b) => b[1].where.size - a[1].where.size)) {
    L.push(`### \`${id}\` (${e.impact}) — ${mdEscape(e.help)}`, "");
    L.push(`${e.nodes} node(s) across ${e.where.size} capture(s): ${Array.from(e.where).slice(0, 12).join(", ")}${e.where.size > 12 ? " …" : ""}`, "");
    for (const t of e.targets) L.push(`- \`${mdEscape(t)}\``);
    L.push("");
  }

  // ── Small text ─────────────────────────────────────────────────────────
  L.push("## Text below 12 px", "");
  L.push("Visible text nodes whose parent's computed `font-size` < 12 px. UI-TYPE-4 sets stricter per-role floors on mobile (13 px captions); this probe is the flat floor from the brief.", "");
  const st = new Map<string, { fs: number; sample: string; where: Set<string> }>();
  for (const r of ok) {
    for (const s of r.probe?.smallText ?? []) {
      const key = `${s.sel}|${s.fontSize}`;
      const e = st.get(key) ?? { fs: s.fontSize, sample: s.sample, where: new Set() };
      e.where.add(`${r.viewport}/${r.surface}`);
      st.set(key, e);
    }
  }
  if (!st.size) L.push("None.");
  else L.push("| px | element | sample | where |", "| --- | --- | --- | --- |");
  for (const [key, e] of Array.from(st.entries()).sort((a, b) => a[1].fs - b[1].fs)) {
    L.push(`| ${e.fs} | \`${mdEscape(key.split("|")[0])}\` | ${mdEscape(e.sample)} | ${Array.from(e.where).slice(0, 5).join(", ")}${e.where.size > 5 ? ` +${e.where.size - 5}` : ""} |`);
  }
  L.push("");

  // ── Focus ──────────────────────────────────────────────────────────────
  L.push("## Focus visibility walk (UI-FOCUS-2 / UI-FOCUS-3)", "");
  L.push("25 Tab presses from the top of the document. Each focused element's outline / box-shadow / border / background / text-decoration (self + 3 ancestors, to catch `:focus-within` rings) is compared to its resting style after blur. `NONE` = no computed change anywhere in the chain; `weak` = background-only. **Noise:** an element whose indicator is drawn by a sibling or a portal is reported NONE — confirm with the crop in `focus/`.", "");
  for (const r of recs.filter((x) => x.focus)) {
    const steps = (r.focus as Rec[]).filter(Boolean);
    const none = steps.filter((s) => s.indicator === "NONE");
    const weak = steps.filter((s) => s.indicator.startsWith("weak"));
    const off = steps.filter((s) => !s.inViewport);
    L.push(`### \`${r.name.replace(/-focus-end$/, "")}\` — ${steps.length} stops, ${none.length} with no indicator, ${weak.length} weak, ${off.length} off-screen`, "");
    for (const s of [...none, ...weak, ...off.filter((x) => x.indicator === "visible")]) {
      L.push(`- step ${s.step}: \`${mdEscape(s.desc)}\` "${mdEscape(s.text)}" — ${s.indicator}${s.inViewport ? "" : " (OFF-SCREEN)"}${s.focusVisible ? "" : " (:focus-visible false)"} [${s.rect.w}×${s.rect.h} @ ${s.rect.x},${s.rect.y}]`);
    }
    L.push("");
  }

  // ── Console / network ──────────────────────────────────────────────────
  L.push("## Console errors and failed requests", "");
  L.push("Attributed to the capture that followed them. **Expected:** the `example.invalid` image from the fake provider's `RICH_MARKDOWN:` turn, the forced bootstrap 503 / connection-refused in `bootstrap-*`, and the `FORCE_ERROR:` turn.", "");
  const ce = new Map<string, Set<string>>();
  for (const r of recs) {
    for (const m of [...(r.consoleErrors ?? []), ...(r.failedRequests ?? [])]) {
      const key = m.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g, "<uuid>").replace(/share\/[\w-]+/g, "share/<token>");
      const e = ce.get(key) ?? new Set();
      e.add(`${r.viewport}/${r.theme}/${r.surface}`);
      ce.set(key, e);
    }
  }
  if (!ce.size) L.push("None.");
  for (const [m, where] of Array.from(ce.entries()).sort((a, b) => b[1].size - a[1].size)) {
    L.push(`- (${where.size}×) \`${mdEscape(m.slice(0, 220))}\` — e.g. ${Array.from(where).slice(0, 3).join(", ")}`);
  }
  L.push("");

  // ── CLS ────────────────────────────────────────────────────────────────
  L.push("## Layout shift (UI-PERF-3 lab approximation)", "");
  L.push("Sum of `layout-shift` entries without recent input. `load` = first 1.2 s after the shell is ready on `/`; `stream` = one fake-provider reply (first turn, includes welcome→thread swap); `slow-stream` = the `SLOW:` turn through Stop. **Noise:** the first-turn value includes the welcome hero unmounting, which is a user-initiated transition but lands >500 ms after the click, so it is not excluded by `hadRecentInput`.", "");
  L.push("| viewport/theme | load | first stream | slow-stream+stop | top sources |", "| --- | --- | --- | --- | --- |");
  const fmt = (c: Rec) => (c && typeof c.value === "number" ? c.value.toFixed(4) : "–");
  const byCombo = new Map<string, Rec>();
  for (const r of recs) {
    const k = `${r.viewport}/${r.theme}`;
    const e = byCombo.get(k) ?? {};
    if (r.surface === "welcome" && r.media === "base") e.load = r.extra?.loadCls;
    if (r.surface === "thread" && r.media === "base") e.stream = r.extra?.streamCls;
    if (r.surface === "stopped") e.slow = r.extra?.streamCls;
    byCombo.set(k, e);
  }
  for (const [k, e] of byCombo) {
    const srcs = [e.load, e.stream, e.slow]
      .flatMap((c: Rec) => (c?.entries ?? []).filter((x: Rec) => !x.recent && x.v > 0.005))
      .flatMap((x: Rec) => x.src)
      .slice(0, 4)
      .join(", ");
    L.push(`| ${k} | ${fmt(e.load)} | ${fmt(e.stream)} | ${fmt(e.slow)} | ${mdEscape(srcs)} |`);
  }
  L.push("");

  // ── Animations ─────────────────────────────────────────────────────────
  L.push("## Running animations (UI-MOTION-1 / UI-MOTION-2)", "");
  L.push("Idle = the settled thread capture; mid-stream = sampled once while the `SLOW:` reply streams. Infinite animations outside `.chat-scroll` during a stream fail UI-MOTION-1; any running animation on an idle surface fails UI-MOTION-2. **Noise:** captures are taken after a 350 ms settle, so a finite entrance transition still running is possible.", "");
  for (const r of ok) {
    const idle = (r.probe?.animations ?? []) as Rec[];
    const mid = (r.extra?.runningAnimations ?? []) as Rec[];
    const list = r.surface === "mid-stream" ? mid : idle.filter((x) => x.infinite || r.surface === "thread");
    if (!list.length) continue;
    if (!["thread", "welcome", "mid-stream", "tool-approval", "deep-research-plan"].includes(r.surface)) continue;
    L.push(`- \`${r.name}\`: ${list.map((x) => `${x.name}${x.infinite ? "∞" : ""}@${x.target ?? (x.inThread ? "thread" : "periphery")}`).slice(0, 8).join(", ")}`);
  }
  L.push("");

  // ── Spacing ────────────────────────────────────────────────────────────
  L.push("## Off-scale spacing (craft)", "");
  L.push("Computed margin / padding / gap values that fail UI-CRAFT-1's predicate: `0`, `1`, a multiple of 4, or — inside a control (`button`, menuitem, option, tab, `code`, badge) — a multiple of 2 up to 14 px. `ml-auto` resolved margins also appear. **Noisy by design:** `em`-based prose margins inside `.chat-md` (column `inProse`), browser defaults and vendored Streamdown chrome show up here; treat as a pointer for review, not a defect list.", "");
  const sp = new Map<string, { value: number; prop: string; count: number; inProse: number; examples: Set<string> }>();
  for (const r of ok) {
    for (const s of r.probe?.spacing ?? []) {
      const key = `${s.value}|${s.prop}`;
      const e = sp.get(key) ?? { value: s.value, prop: s.prop, count: 0, inProse: 0, examples: new Set() };
      e.count += s.count;
      e.inProse += s.inProse;
      for (const x of s.examples) if (e.examples.size < 3) e.examples.add(x);
      sp.set(key, e);
    }
  }
  L.push("| value px | property | occurrences | inProse | examples |", "| --- | --- | --- | --- | --- |");
  for (const e of Array.from(sp.values()).sort((a, b) => b.count - a.count).slice(0, 25)) {
    L.push(`| ${e.value} | ${e.prop} | ${e.count} | ${e.inProse} | ${Array.from(e.examples).map((x) => `\`${mdEscape(x.slice(0, 70))}\``).join("<br>")} |`);
  }
  L.push("");

  // ── Facts ──────────────────────────────────────────────────────────────
  L.push("## Environment facts", "");
  const factRows = new Map<string, string>();
  for (const r of ok) {
    if (r.probe && r.surface === "welcome" && r.media === "base") {
      factRows.set(`${r.viewport}/${r.theme}`, `hover:none=${r.probe.facts.hoverNone} pointer:coarse=${r.probe.facts.pointerCoarse} html.class="${r.probe.facts.theme}"`);
    }
  }
  for (const [k, v] of factRows) L.push(`- ${k}: ${v}`);
  L.push("");

  fs.writeFileSync(path.join(AUDIT_DIR, "probes.md"), L.join("\n"));
  if (distinctDup.length) {
    throw new Error(`UI audit: ${distinctDup.length} distinct surfaces produced identical PNGs — see test-results/audit/probes.md`);
  }
}
