// Audit global setup: refuse to run against the wrong build, and clear the
// previous run's generated output (never FINDINGS-RAW.md or other hand-written
// files in the audit dir).

import fs from "node:fs";
import path from "node:path";

const WEB_DIR = path.resolve(__dirname, "..", "..");
const AUDIT_DIR = path.join(WEB_DIR, "test-results", "audit");

function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (e.name.endsWith(".js")) out.push(p);
  }
  return out;
}

export default async function globalSetup(): Promise<void> {
  const buildId = path.join(WEB_DIR, ".next", "BUILD_ID");
  if (!fs.existsSync(buildId)) {
    throw new Error(
      "No production build found (.next/BUILD_ID). Run `pnpm audit:ui` (it builds first), not the no-build variant.",
    );
  }
  // The browser must call the BE directly (see audit.config.ts); a build made
  // for the same-origin rewrite would buffer SSE and silently lose the
  // mid-stream surface.
  const chunks = walk(path.join(WEB_DIR, ".next", "static"));
  const direct = chunks.some((f) =>
    fs.readFileSync(f, "utf8").includes("http://localhost:8000"),
  );
  if (!direct) {
    throw new Error(
      "The .next build does not inline NEXT_PUBLIC_API_BASE_URL=http://localhost:8000. Rebuild with `pnpm audit:ui`.",
    );
  }
  for (const sub of ["shots", "captures", "focus", "pdf"]) {
    fs.rmSync(path.join(AUDIT_DIR, sub), { recursive: true, force: true });
  }
  for (const f of ["probes.json", "probes.md", "capture-log.json"]) {
    fs.rmSync(path.join(AUDIT_DIR, f), { force: true });
  }
  fs.mkdirSync(path.join(AUDIT_DIR, "captures"), { recursive: true });
}
