---
name: ui-sweep
description: Review (and, when asked, fix) UI/UX regressions in a web app via headless-browser screenshots across routes, viewports, themes, and interaction states. Use when asked to audit the UI, review the design, find visual or accessibility regressions, screenshot the app, verify visual changes look right, or "make the UI look right." Framework-agnostic (React/Vue/Svelte/plain). Builds and serves the app, renders it headlessly, and pairs each screenshot with a root-cause probe and, when fixes are wanted, a surgical fix. Needs an app that builds and runs locally; not for product/feature work or new pages.
---

# UI Sweep

Act as a screenshot-driven UI/UX reviewer and, only when authorized, a
surgical fixer. Prioritize authorized scope and valid evidence → grounded
issue and root-cause conclusions → requested coverage → surgical authorized
changes.

## Standing rules

The screenshot matrix is the discovery loop —
don't skip it because "the change looks small." A screenshot you never
confirmed actually rendered is worse than no screenshot: it hides the
regression behind a loading spinner.

- **Review-only boundary:** If the ask was to audit, review, screenshot,
  or verify, stop after the root-cause probes and report each issue with
  its severity (blocks use, degrades use, or cosmetic), confidence,
  route × viewport × theme, the screenshot, the probe result and the
  `file:line` of the cause; run steps 7–8 only when the user asks for fixes
  or confirms a fix you proposed, not when they only agree that the issues
  are real. Mark an unresolved cause as unknown rather than inventing a
  `file:line`.
- Fix **root causes, not symptoms**; probe every issue before editing.
- Do **not** add features, refactor architecture, introduce
  dependencies, or write new tests, and touch a test only when an
  existing one breaks. The isolated capture-driver setup in **Setup**
  is the defined dependency exception.
- **Keep the repo clean.** The browser driver is the repo's existing
  dependency or installed in the script directory; capture script +
  screenshots live outside the repo (or a gitignored path). Confirm
  `git status` shows only the intended app fix — never the harness, the
  driver, or the PNGs.

## Loop

1. **Set up the capture environment.** See **Setup** — this is where
   sweeps fail, so do every step.
2. **Discover the surface** (routes × themes × interaction states, at
   the harness's viewports) from the repo, not from memory. See
   **Repo-agnostic discovery**.
3. **Capture** the matrix with the harness in
   `references/playwright-harness.md`. Keep the harness structure
   (mocks, content wait, error capture, verification) unchanged;
   parameterize the port, API base and observed request surface, fixtures
   and routing, auth and theme seed, and the capture matrix, including each
   entry's `media`, `steps`, final route/state checks and choice of one of
   the harness's existing viewports, and delete the font-abort route only
   when the font host is reachable.
4. **Confirm each shot rendered** before trusting it. See **Verify the
   capture** — read the harness's stage failures, `UNRENDERED`,
   `UNMOCKED` and coverage/media diagnostics, then hash the PNGs and
   investigate duplicates without treating them as verdicts.
5. **Review** every PNG against the **Review checklist**. List issues
   first; don't fix yet.
6. **Probe root cause** for every issue with a one-shot `page.evaluate`
   before editing. Reading code excerpts guesses wrong on framework
   traps. Apply the **Review-only boundary** after the probes.
7. **Fix in themed batches**, one commit each. Re-capture after each
   batch and confirm the issue is gone.
8. **Quality gates + clean repo** before commit. See **Quality bar**.

## Setup

1. **Install the browser driver and a browser binary** without touching
   the repo's manifest or lockfile:
    - If the repo's `package.json` already lists `playwright`, reuse
      that install (see step 3).
    - Otherwise install it in the capture script's own directory, never
      in the repo:
      `mkdir -p /tmp/uxsweep && cd /tmp/uxsweep && npm init -y && npm i playwright`.
      Running `npm i` inside a pnpm or yarn workspace fails on
      `workspace:` dependencies and rewrites `node_modules`.
    - `npx playwright install chromium` from wherever `playwright` is
      installed (downloads ~300 MB — Chromium plus a headless shell; may
      need `--with-deps` on a bare box). If the network blocks the CDN,
      stop and tell the user — the sweep can't run here.
    - Browsers may land outside the default cache when
      `PLAYWRIGHT_BROWSERS_PATH` is set in the environment; the runtime
      reads the same variable, so leave it as-is and just verify a
      launch (`chromium.launch()`) succeeds before capturing.
    - Establish the installed driver and browser versions and check the
      requested media APIs against their current official documentation.
      Reusing an install does not establish capability. Confirm each
      requested media query's effective value in the target page before
      relying on a preference capture; API/schema support and browser
      rendering support are separate. Keep unsupported or ignored modes
      explicitly unsupported or unverified, never passing evidence.
2. **Capture against a production build, not the dev server.** Dev
   servers (Vite, webpack, Next dev) lazily compile route-split / heavy
   module graphs on first hit; under headless automation a heavy route
   can sit in its loading/Suspense state indefinitely and never fire its
   data queries — you screenshot a spinner and never know. Build once
   and serve the build on a stable port:
    - Run the repo's build script (`npm run build`, `pnpm build`, …),
      then serve it: `npx vite preview --port <p> --strictPort`,
      `npx serve -s dist -l <p>`, `next start -p <p>`, etc. Confirm the
      port the server prints matches the harness's `BASE_URL`: `serve`
      silently moves to a free port when `<p>` is taken.
    - Production chunks are pre-bundled and load deterministically.
    - **Necessary, not always sufficient.** The build is the reliable
      surface to *launch* from, but a deeply nested route can still fail
      to render when reached by a direct deep-link — reach those by UI
      navigation (see below).
    - Caveat: a build may use different env defaults than dev (feature
      flags, API engine), so some chrome differs — fine for visual
      review; note it. Only fall back to the dev server for a trivial
      app with no route splitting; for any other app whose build fails,
      supply what the build lacks through its environment without
      editing the repo, and stop and tell the user if it still fails.
3. **Put the capture script where its imports resolve.** ESM resolves
   `import "playwright"` from the script file's own directory, not the
   cwd. Running a script from `/tmp` fails with `ERR_MODULE_NOT_FOUND`
   unless `playwright` is installed there. With the script-directory
   install from step 1 it already resolves. When reusing the repo's
   `playwright`, symlink the repo's `node_modules` into the script's
   directory (`ln -sfn <repo>/node_modules <scriptdir>/node_modules`).

## Repo-agnostic discovery (detect, don't hardcode)

- **Port / base URL:** read the `dev` / `preview` / `start` script in
  `package.json` (or the framework config). Don't assume `:3000`.
- **API base:** grep the app's HTTP client / `.env*` for the base path
  (`/api`, `/api/v1`, an absolute origin). The mock route glob must
  match it. Don't assume `/api/v1`.
- **Routes:** read the router config (React Router routes file, Next
  `app/`/`pages/`, Vue router) for the real paths and params. Pick the
  highest-traffic routes plus any the change under review touched.
- **Mock shapes:** derive from the API client's TypeScript types or a
  couple of real fixtures, not from guesswork. See the auth/mock rules
  below.

## Auth + mocks

- **Mock every awaited response needed by the selected route/state.**
  Derive request identity from the actual method and full URL, preserving
  relevant query and body distinctions (and headers when they select a
  response). Return the discovered status, headers/content type and body
  shape for success and error states, including non-JSON or bodyless
  responses when required. Await asynchronous fixture selection and
  fulfillment; diagnose selection/fulfillment failures and unmatched calls
  explicitly. Never forward an unknown call live or substitute invented
  data to make a shot reviewable.
- **Declare the interception surface and its limits.** Match the discovered
  browser API origins/paths with `context.route`, block service workers in
  the capture context, and compare matched hits with independently observed
  relevant browser requests. A matching route proves only matched browser
  interception: service-worker traffic, WebSockets, server-side calls,
  other origins and calls outside the match need separate accounting when
  the selected state uses them. Establish the required mocks for those
  channels or report the affected evidence as unverified; an empty
  `UNMOCKED` list alone does not prove full backend/API coverage. The real
  backend is usually blocked from the sandbox; missing responses can leave
  a page loading or in error.
- **Return arrays where the app maps over a collection.** A scalar or
  `"ok"` string where an array is expected throws
  `(x ?? []).map is not a function` and trips the error boundary — a
  fixture-induced error; trace the actual cause before assigning app fault.
- **Seed auth before first paint** with `addInitScript` writing whatever
  token/session the app checks, and mock the session/identity endpoint
  to return a user. For public pages, return `401` from the session
  probe so the app stays on the unauthenticated route.

## Navigation + timing (stable rendering)

- **Drive the app like a user.** A direct `goto` is fine for top-level
  routes, public or behind the seeded auth (login, a list page). For a
  deeply nested route, or one a guard admits only after its parent loads
  (e.g. `/projects/:id/board`), render the parent and click into the
  child — do not deep-link `goto` it or fake `history.pushState`. A
  direct `goto` to a nested route can leave it stuck in Suspense with
  only the app-shell queries firing; clicking into it from the rendered
  parent fires the route's own data queries and renders it fully. In the
  harness, the click-through goes in the capture entry's `steps`.
- **Wait for content, not for "loading" to vanish.** A "no loading
  text" or `networkidle` check passes prematurely (e.g. just before an
  auth redirect kicks off the next load). Wait for a known content
  selector/text to appear (generous timeout), then a short settle, then
  shoot. Keep setup, navigation, emulation, state, readiness, capture and
  final diagnostics inside a stage-aware per-case error boundary. Record
  the failed stage and available evidence, attempt owned context/browser
  cleanup without masking the original failure, and handle later cases
  where feasible.

## Verify the capture (cheap, catches silent failures)

- **Classify only after successful screenshot acquisition and final
  observed evidence.** A missed content wait or page error, including one
  emitted during capture, makes a shot un-rendered, whatever its hash.
  Recheck final route, expected content/state and effective media after
  acquisition; a changed or unverifiable result is not valid evidence.
  The harness labels an acquired invalid PNG `<name>__UNRENDERED.png`;
  failed acquisition is a stage failure, not a valid screenshot. Probe
  invalid evidence before review; this covers the observed window, not
  all future errors.
- **Reviewed shots print no `UNMOCKED:` line or fixture failure.** Add
  typed fixtures and re-capture; resolve relevant out-of-surface requests
  and channel limits under **Auth + mocks** before trusting the shot.
- **Hash every PNG** (`md5sum`). Duplicate bytes across routes, states or
  media variants are diagnostic clues. Compare final route/state,
  expected content, API/fixture and error evidence, DOM/readiness and
  whether the media behavior applies. Identical valid pixels can be
  legitimate; file a finding only with evidence of an expected difference
  being absent. Re-navigate or repair the harness when evidence shows a
  capture failure; never review or commit off un-rendered shots.
- **Verify reduced motion by mechanism and intent.** Compare the same
  element under effective `"no-preference"` and `"reduce"` using the
  relevant CSS rules/keyframes, JavaScript preference handling, SVG or
  Web Animations API behavior and appropriate live observations. Computed
  `animationName`, `animationDuration`, `transitionDuration` or
  `scrollBehavior` alone cannot certify every mechanism. Motion may be
  removed, reduced or replaced rather than eliminated. The harness's
  animation-disabled PNGs and their hashes do not prove support.
- **Probe before blaming the code.** For any blank/stuck/odd shot, read
  the harness's recorded API hits and console/page errors for that shot,
  together with a one-shot `page.evaluate` dump of `location.href` and
  trimmed `document.body.innerText`. A `page.evaluate` alone cannot see
  intercepted requests or console events. Treat observations as causal
  hypotheses: trace actual requests, responses, fixtures, state, guards,
  mounting, CSS and readiness before blaming or exonerating app code.
  Only auth calls firing can suggest a guard or mount problem, but does
  not establish its cause.

## Review checklist

Per PNG, in both light and dark and at phone + desktop widths:

- **Layout:** overflow / clipping, content under fixed chrome, broken
  grids, text truncation/ellipsis on labels, safe-area gaps. If web
  fonts were blocked, confirm truncation and wrapping issues with the
  real font before filing them as confirmed; where the real font cannot
  load, report them at low confidence and name the fallback font.
- **Theme:** any element that ignores dark mode (light-mode hex baked as
  a CSS-var fallback), low-contrast text, invisible borders.
- **State:** loading/empty/error parity; focus rings present and
  ≥ 3:1; disabled vs. active read correctly; touch targets ≥ 44 px on
  coarse pointers.
- **A11y modes:** drive `colorScheme`, `contrast: "more"`,
  `reducedMotion: "reduce"`, and `forcedColors: "active"` through
  `emulateMedia` — they are routinely unstyled. A still shot cannot
  show motion, so apply **Verify reduced motion by mechanism and intent**.
  Confirm driver/browser capability and effective queries as in **Setup**;
  unsupported or ignored modes remain unsupported or unverified.
  `prefers-reduced-transparency` is not an `emulateMedia` option, and
  unknown keys are silently ignored, so a call that raises no error
  proves nothing. In Chromium, drive it over CDP with the harness's
  `emulateReducedTransparency` step, which sets it and confirms
  `matchMedia("(prefers-reduced-transparency: reduce)").matches` before
  the shot. Otherwise verify the CSS in code.
- **Looks wrong but is correct:** intentional
  translucency/blur, deliberately muted "coming soon" controls,
  brand-specific spacing. Confirm against tokens/design intent before
  "fixing" them.

## Quality bar

- Gates before each commit, using the commands this repo's scripts
  define: typecheck clean, the tests covering the touched paths green,
  full test suite green.

## Self-check

Before declaring a sweep done, confirm:

- [ ] Setup ran in full: `playwright` resolved from the repo's existing
  dependency or installed in the script directory, with the manifest and
  lockfile untouched; a chromium binary installed; a `chromium.launch()`
  confirmed to succeed before the first capture; and the capture script
  placed where `import "playwright"` resolves. Driver/browser versions,
  requested media API capability and effective queries were established;
  unsupported/ignored modes remain explicitly unsupported or unverified.
- [ ] The capture used the recipe in `references/playwright-harness.md` with
  its structure (mocks, content wait, error capture, verification)
  unchanged, parameterizing only the port, the API base and observed request
  surface, the fixtures and routing, the auth and theme seed, and the capture
  matrix (each entry's `media`, `steps`, final route/state checks and choice
  of one of the existing viewports), and at most deleting the font-abort
  route when the font host is reachable — not a harness written from scratch.
- [ ] Every shot was taken against a production build served on a stable
  port that matches `BASE_URL` — a dev server only for a trivial app with
  no route splitting; any chrome that differs from dev because the build
  uses different env defaults is noted rather than filed as an issue.
- [ ] The port / base URL, the API base path, the route list, and the mock
  shapes were each read out of this repo — the `dev`/`preview`/`start`
  script or framework config, the HTTP client or `.env*`, the router
  config, and the API client's types or real fixtures — not assumed.
- [ ] Required responses for selected states have awaited, typed fixtures
  keyed by actual method/URL and relevant query/body/header distinctions,
  with the discovered success/error status and response shape; no reviewed
  shot printed `UNMOCKED` or fixture failures. Matched interception was
  compared with independently observed relevant requests, and applicable
  channel limits were accounted for without claiming complete backend coverage;
  endpoints the app maps over return arrays; auth is seeded before first
  paint with `addInitScript` and the session/identity endpoint is mocked,
  returning `401` for the public routes.
- [ ] Every deeply nested route, or one a guard admits only after its parent
  loads, was reached by clicking through from its rendered parent in the
  entry's `steps` — no direct `goto`, no faked `history.pushState` — and
  each shot waited for a known content selector or text to appear plus a
  short settle, not on `networkidle` or on "loading" disappearing.
- [ ] The captured matrix covers the picked routes — the highest-traffic
  ones plus every route the change under review touched — at phone and
  desktop widths in both light and dark, plus the interaction states under
  review, each in at least one viewport and theme, driven by an entry's
  `steps` and named by its `state`.
- [ ] Reviewed PNGs were acquired successfully and classified only after
  final route/content/state/media and observed error evidence, including
  errors during capture; none is `UNRENDERED` or an unresolved stage failure.
  Stage diagnostics survived failures and owned cleanup was attempted
  without masking the original failure, with later cases handled where feasible.
  Every PNG was hashed (`md5sum`); duplicates were investigated against
  route/state, content, API/errors, DOM/readiness and applicable media
  behavior rather than treated as verdicts. Reduced motion was judged by
  mechanism and intent, never by animation-disabled pixels or hashes.
  Blank, stuck or odd shots got the combined API/error and `page.evaluate`
  evidence and causal tracing before app code was blamed or exonerated.
- [ ] Every PNG was reviewed against all five checklist groups — layout,
  theme, state, a11y modes, looks-wrong-but-correct — and the issue list was written
  before the first fix. `colorScheme`, `contrast: "more"`,
  `reducedMotion: "reduce"` and `forcedColors: "active"` were driven
  through `emulateMedia` with capability/effective-query verification, or
  remained explicitly unsupported/unverified. `prefers-reduced-transparency`
  was driven over CDP and confirmed with `matchMedia` before the shot, or,
  outside Chromium, verified in code.
- [ ] Nothing was "fixed" for looking wrong while being correct —
  intentional translucency/blur, deliberately muted "coming soon"
  controls, and brand-specific spacing were each confirmed against tokens
  or design intent first.
- [ ] Every issue got its `page.evaluate` root-cause probe before any edit,
  and each fix addresses that root cause rather than the symptom.
- [ ] No feature, architecture refactor, new dependency, or new test was
  added; a test was touched only because an existing one broke.
- [ ] A review-only ask (audit, review, screenshot, verify) stopped after
  the probes and reported the issue list; nothing was edited or committed
  without a request for fixes.
- [ ] If fixes were requested: they landed in themed batches, one commit
  each, with a re-capture after each batch confirming the issue is gone.
- [ ] If fixes were requested: before each commit, with this repo's own
  commands, typecheck clean, the tests covering the touched paths green,
  and the full test suite green.
- [ ] `git status` shows only the intended app fix (nothing, for a
  review-only sweep) — not the capture script, not the screenshots, not the
  browser driver in the manifest or lockfile.
