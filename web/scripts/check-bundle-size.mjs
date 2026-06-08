// CI bundle-size gate. Run AFTER `next build` (the script reads `.next/`):
//
//   pnpm build && pnpm check:bundle
//
// Fails the build when the JavaScript the browser must download for the FIRST
// paint of a route ("initial route JS") exceeds a budget. Bundle creep is silent
// — every dependency bump or stray client import nudges it up — so we gate it in
// CI rather than catching it after a regression ships to Vercel.
//
// What "initial route JS" means here: the union of the entry chunks the app
// loads up-front. We support both bundlers Next can emit:
//
//   * Turbopack (current default) — there is no per-route client manifest, so we
//     measure the shared app-shell entry: `rootMainFiles` + `polyfillFiles` from
//     `.next/build-manifest.json`. These load on first paint for every app-router
//     route, so they are the floor every route pays.
//   * Webpack — `.next/app-build-manifest.json` lists the JS per route; we budget
//     each route's full initial set independently and report the worst offender.
//
// Budget: gzipped bytes (what users actually download over the wire). The default
// is 200 KB gzip; override with BUNDLE_BUDGET_GZIP_KB. An uncompressed ceiling is
// also enforced (BUNDLE_BUDGET_RAW_KB, default 700 KB) as a documented secondary
// guard — gzip ratios vary, and a huge raw bundle still costs parse/exec time.

import { readFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { gzipSync } from "node:zlib";

const NEXT_DIR = resolve(process.cwd(), ".next");
const BUDGET_GZIP_KB = Number(process.env.BUNDLE_BUDGET_GZIP_KB ?? 200);
const BUDGET_RAW_KB = Number(process.env.BUNDLE_BUDGET_RAW_KB ?? 700);

const KB = 1024;

function fail(message) {
  console.error(`\n\u001b[31m✖ bundle-size gate: ${message}\u001b[0m\n`);
  process.exit(1);
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

// Sum the on-disk (raw) and gzipped sizes of a set of chunk paths, which are
// stored in the manifest relative to `.next/`. Missing files are a hard error:
// a manifest that points at a chunk the build didn't emit means the build is
// inconsistent, and silently skipping it would under-count the budget.
function measure(files) {
  let raw = 0;
  let gzip = 0;
  const perFile = [];
  for (const file of files) {
    const abs = join(NEXT_DIR, file);
    if (!existsSync(abs)) {
      fail(`manifest references missing chunk: ${file}`);
    }
    const buf = readFileSync(abs);
    const g = gzipSync(buf).length;
    raw += buf.length;
    gzip += g;
    perFile.push({ file, raw: buf.length, gzip: g });
  }
  return { raw, gzip, perFile };
}

// Build a { label -> [chunk, ...] } map of every initial-JS set to budget.
// Prefer the webpack per-route manifest (richer); fall back to the Turbopack
// shared app-shell entry.
function collectEntries() {
  const appBuildManifest = join(NEXT_DIR, "app-build-manifest.json");
  if (existsSync(appBuildManifest)) {
    const manifest = readJson(appBuildManifest);
    const pages = manifest.pages ?? {};
    const entries = Object.entries(pages)
      .map(([route, files]) => [route, (files ?? []).filter((f) => f.endsWith(".js"))])
      .filter(([, files]) => files.length > 0);
    if (entries.length > 0) {
      return { mode: "per-route (webpack app-build-manifest)", entries };
    }
  }

  const buildManifest = join(NEXT_DIR, "build-manifest.json");
  if (!existsSync(buildManifest)) {
    fail(`no build manifest found in ${NEXT_DIR}. Did you run \`next build\` first?`);
  }
  const manifest = readJson(buildManifest);
  const shell = [...(manifest.rootMainFiles ?? []), ...(manifest.polyfillFiles ?? [])].filter(
    (f) => f.endsWith(".js"),
  );
  if (shell.length === 0) {
    fail("build manifest had no rootMainFiles/polyfillFiles to measure.");
  }
  return { mode: "shared app shell (turbopack build-manifest)", entries: [["app shell", shell]] };
}

const { mode, entries } = collectEntries();

console.log(`Bundle-size gate — measuring: ${mode}`);
console.log(`Budget: ${BUDGET_GZIP_KB} KB gzip / ${BUDGET_RAW_KB} KB raw (initial route JS)\n`);

let worstGzip = 0;
const violations = [];

for (const [label, files] of entries) {
  const { raw, gzip } = measure(files);
  worstGzip = Math.max(worstGzip, gzip);
  const gzipKb = gzip / KB;
  const rawKb = raw / KB;
  const over = gzipKb > BUDGET_GZIP_KB || rawKb > BUDGET_RAW_KB;
  const flag = over ? "\u001b[31mOVER\u001b[0m" : "\u001b[32mok\u001b[0m";
  console.log(
    `  ${flag}  ${label.padEnd(28)} ${gzipKb.toFixed(1)} KB gzip  (${rawKb.toFixed(1)} KB raw, ${files.length} chunks)`,
  );
  if (over) {
    violations.push({ label, gzipKb, rawKb });
  }
}

console.log();

if (violations.length > 0) {
  const lines = violations
    .map(
      (v) =>
        `  - ${v.label}: ${v.gzipKb.toFixed(1)} KB gzip / ${v.rawKb.toFixed(1)} KB raw` +
        ` (budget ${BUDGET_GZIP_KB} KB gzip / ${BUDGET_RAW_KB} KB raw)`,
    )
    .join("\n");
  fail(
    `initial route JS over budget:\n${lines}\n\n` +
      `  Trim the bundle (dynamic import heavy/client-only deps, drop unused imports)\n` +
      `  or, if the growth is justified, raise BUNDLE_BUDGET_GZIP_KB in web/package.json's\n` +
      `  check:bundle script and explain why in the PR.`,
  );
}

console.log(
  `\u001b[32m✓ bundle-size gate passed\u001b[0m — worst initial route JS ${(worstGzip / KB).toFixed(1)} KB gzip (budget ${BUDGET_GZIP_KB} KB).`,
);
