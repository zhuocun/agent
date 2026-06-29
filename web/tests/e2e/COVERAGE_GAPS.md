# E2E coverage policy

FE coverage is collected through the Playwright suite (Istanbul via the
`COVERAGE=1` webpack pass in `next.config.ts`, drained per-test by
`coverage-fixture.ts`). It is **FE-only** — the BE has its own pytest suite.

## Commands

```bash
pnpm test:e2e:coverage   # run every spec under COVERAGE=1, write web/coverage/
pnpm coverage:report     # merge → text/lcov/html/json-summary, then check-coverage
```

`coverage:report` ends in `nyc check-coverage`, so it exits non-zero below the
floor. CI enforces this in the `web-coverage` job (`.github/workflows/ci.yml`)
and uploads the lcov report.

## The gate (`web/.nycrc.json`)

| Metric | Floor | Achieved (last run) |
| --- | --- | --- |
| Statements | 73% | 76.4% |
| Lines | 77% | 80.26% |
| Functions | 75% | 78.51% |
| Branches | 64% | 67.23% |

Floors sit ~3 pts under the achieved numbers to absorb run-to-run noise.
Branches lag statements/lines structurally (each feature-detect fallback is a
branch), so its floor is lowest. **Ratchet policy:** when a change lifts a
metric durably, raise its floor to ~2–3 pts under the new achieved number so
regressions are caught without making the gate brittle.

## Exclusions (why the gate is browser-reachable code only)

`window.__coverage__` only exists in the browser, so `nyc` excludes:

- `src/app/**` — App Router server components (no `"use client"`) execute in the
  Node RSC process and are never instrumented. The client leaf each route
  renders (`ChatThread`, `PublicConversationView`, `PlatformStatusView`) **is**
  instrumented, so the behavior is still covered.
- `tests/**`, `scripts/**`, `*.config.*`, `**/*.d.ts` — non-product code.

## Residual Layer-C gaps (left to the floor, not chased)

Genuinely browser-unreachable-in-headless code keeps a few files low and is
deliberately not pursued: feature-detect fallbacks (`scheduler-yield.ts`,
`use-haptic.ts`, `use-visual-viewport.ts`, speech APIs in
`use-speech-*.ts`), `prefers-reduced-motion` (`motion.ts`), touch-gesture
handlers (`use-swipe-*.ts`), PWA `beforeinstallprompt` (`install-coachmark.tsx`),
offline/IndexedDB replay (`offline-store.ts`), and defensive `catch`/parse-fail
arms in `apiClient.ts` / `stream-client.ts`. The single biggest remaining
Layer-B opportunity is `chat-thread.tsx` (~66% stmts) — a mega-orchestrator
whose edit/retry/branch-switch and keyboard paths are only partially driven.
