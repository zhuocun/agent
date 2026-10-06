---
name: visual-ux-sweep
description: Review (and, when asked, fix) UI/UX regressions in a web app via headless-browser screenshots across routes, viewports, themes, and interaction states. Use when asked to audit the UI, review the design, find visual or accessibility regressions, screenshot the app, verify visual changes look right, or "make the UI look right." Framework-agnostic (React/Vue/Svelte/plain). Renders the running app and pairs each screenshot with a root-cause probe and, when fixes are wanted, a surgical fix. Not for a code-level review of a frontend diff or PR that reads source without rendering it (use cr-fe), product/feature work, or new pages.
---

# Visual UX Sweep

Find UI/UX issues by screenshot review and, when fixes are wanted, fix
them in tight commits. The screenshot matrix is the discovery loop —
don't skip it because "the change looks small." A screenshot you never
confirmed actually rendered is worse than no screenshot: it hides the
regression behind a loading spinner.

## Loop

1. **Set up the capture environment.** See **Setup** — this is where
   sweeps fail, so do every step.
2. **Discover the surface** (routes × viewports × themes × interaction
   states) from the repo, not from memory. See **Repo-agnostic
   discovery**.
3. **Capture** the matrix with the harness in
   `references/playwright-harness.md`. Keep the harness structure
   (mocks, content wait, error capture, verification) unchanged;
   parameterize the port, API base, fixtures, auth and theme seed, and
   the capture matrix, including each entry's `media` and `steps`.
4. **Confirm each shot rendered** before trusting it. See **Verify the
   capture** — read the harness's `UNRENDERED` and `UNMOCKED` output,
   then hash the PNGs; identical hashes across distinct routes mean a
   route never rendered.
5. **Review** every PNG against the **Review checklist**. List issues
   first; don't fix yet.
6. **Probe root cause** for every issue with a one-shot `page.evaluate`
   before editing. Reading code excerpts guesses wrong on framework
   traps. If the ask was to audit, review, screenshot, or verify, stop
   here and report the issue list with its probe evidence; run steps
   7–8 only when the user asked for fixes or confirms them.
7. **Fix in themed batches**, one commit each. Re-capture after each
   batch and confirm the issue is gone.
8. **Quality gates + clean repo** before commit. See **Quality bar**.

## Setup (do every step — this is where sweeps fail)

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
      app with no route splitting.
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
  highest-traffic + the ones your diff touched.
- **Mock shapes:** derive from the API client's TypeScript types or a
  couple of real fixtures, not from guesswork. See the auth/mock rules
  below.

## Auth + mocks

- **Intercept every API call** in the browser context
  (`context.route("**/<api-base>/**", …)`) and fulfill plausible JSON —
  the real backend is usually blocked from the sandbox. An un-mocked
  call hangs or errors and the page never leaves loading.
- **Return arrays where the app maps over a collection.** A scalar or
  `"ok"` string where an array is expected throws
  `(x ?? []).map is not a function` and trips the error boundary — a
  self-inflicted "bug" that isn't in the code.
- **Seed auth before first paint** with `addInitScript` writing whatever
  token/session the app checks, and mock the session/identity endpoint
  to return a user. For public pages, return `401` from the session
  probe so the app stays on the unauthenticated route.

## Navigation + timing (stable rendering)

- **Drive the app like a user.** A direct `goto` is fine for top-level /
  public routes (login, a list page). For a deeply nested or guarded
  route (e.g. `/projects/:id/board`), render the parent and click into
  the child — do not deep-link `goto` it or fake `history.pushState`.
  A direct `goto` to a nested route can leave it stuck in Suspense with
  only the app-shell queries firing; clicking into it from the rendered
  parent fires the route's own data queries and renders it fully. In
  the harness, the click-through goes in the capture entry's `steps`.
- **Wait for content, not for "loading" to vanish.** A "no loading
  text" or `networkidle` check passes prematurely (e.g. just before an
  auth redirect kicks off the next load). Wait for a known content
  selector/text to appear (generous timeout), then a short settle, then
  shoot.

## Verify the capture (cheap, catches silent failures)

- **Any shot whose content wait missed or that threw a page error is
  un-rendered, whatever its hash.** The harness saves it as
  `<name>__UNRENDERED.png` and lists it at the end; probe it before
  review.
- **Reviewed shots print no `UNMOCKED:` line.** An unmocked call gets a
  placeholder (`[]` for a GET, `{ ok: true }` otherwise), so an object endpoint breaks the page and the
  breakage looks like an app bug. Add a typed fixture and re-capture.
- **Hash every PNG** (`md5sum`). Identical hashes across distinct routes
  mean the route did not render — you captured the same loading/error
  screen. Re-navigate or fix the harness; never review or commit off
  un-rendered shots. Identical hashes between media variants of the
  same route (light/dark, contrast, forced-colors, reduced-transparency)
  mean the app ignores that feature. If both shots passed their content
  wait, file it as a review finding (for light/dark, a Theme issue), not
  a capture failure. Reduced motion is the exception: the harness
  disables animations in every shot, so a correct app and one that
  ignores the preference hash the same, and the match proves nothing.
  Check it with the harness's computed-style probe under
  `reducedMotion: "reduce"`, compared with the same element under
  `"no-preference"` (`animationName`, `animationDuration`,
  `transitionDuration` of the animated elements), or in code.
- **Probe before blaming the code.** For any blank/stuck/odd shot, read
  the harness's recorded API hits and console/page errors for that shot,
  together with a one-shot `page.evaluate` dump of `location.href` and
  trimmed `document.body.innerText`. A `page.evaluate` alone cannot see
  intercepted requests or console events. This distinguishes a
  harness/mock artifact from a real app bug (e.g. it reveals "only the
  auth endpoints fired, the route's own queries never did").

## Review checklist

Per PNG, in both light and dark and at phone + desktop widths:

- **Layout:** overflow / clipping, content under fixed chrome, broken
  grids, text truncation/ellipsis on labels, safe-area gaps. If web
  fonts were blocked, confirm truncation and wrapping issues with the
  real font before filing.
- **Theme:** any element that ignores dark mode (light-mode hex baked as
  a CSS-var fallback), low-contrast text, invisible borders.
- **State:** loading/empty/error parity; focus rings present and
  ≥ 3:1; disabled vs. active read correctly; touch targets ≥ 44 px on
  coarse pointers.
- **A11y modes:** drive `colorScheme`, `contrast: "more"`,
  `reducedMotion: "reduce"`, and `forcedColors: "active"` through
  `emulateMedia` — they are routinely unstyled. A still shot cannot
  show motion, so judge reduced motion from the computed-style probe or
  the CSS, not from the screenshot.
  `prefers-reduced-transparency` is not an `emulateMedia` option, and
  unknown keys are silently ignored, so a call that raises no error
  proves nothing. In Chromium, drive it over CDP with the harness's
  `emulateReducedTransparency` step, which sets it and confirms
  `matchMedia("(prefers-reduced-transparency: reduce)").matches` before
  the shot. Otherwise verify the CSS in code.
- **Anti-patterns that look wrong but are correct:** intentional
  translucency/blur (glass), deliberately muted "coming soon" controls,
  brand-specific spacing. Confirm against tokens/design intent before
  "fixing" them.

## Quality bar

- Fix **root causes, not symptoms**.
- Do **not** add features, refactor architecture, introduce
  dependencies, or write new tests unless an existing test breaks.
- Gates before each commit, using the commands this repo's scripts
  define: typecheck clean, the tests covering the touched paths green,
  full test suite green.
- **Keep the repo clean.** The browser driver is the repo's existing
  dependency or installed in the script directory; capture script +
  screenshots live outside the repo (or a gitignored path). Confirm
  `git status` shows only the intended app fix — never the harness, the
  driver, or the PNGs.

## Self-check

Before declaring a sweep done, confirm:

- [ ] Setup ran in full: `playwright` resolved from the repo's existing
  dependency or installed in the script directory, with the manifest and
  lockfile untouched; a chromium binary installed; a `chromium.launch()`
  confirmed to succeed before the first capture; and the capture script
  placed where `import "playwright"` resolves.
- [ ] The capture used the recipe in `references/playwright-harness.md` with
  its structure (mocks, content wait, error capture, verification)
  unchanged, parameterizing only the port, the API base, the fixtures, the
  auth and theme seed, and the capture matrix, including each entry's
  `media` and `steps` — not a harness written from scratch.
- [ ] Every shot was taken against a production build served on a stable
  port that matches `BASE_URL` — a dev server only for a trivial app with
  no route splitting; any chrome that differs from dev because the build
  uses different env defaults is noted rather than filed as an issue.
- [ ] The port / base URL, the API base path, the route list, and the mock
  shapes were each read out of this repo — the `dev`/`preview`/`start`
  script or framework config, the HTTP client or `.env*`, the router
  config, and the API client's types or real fixtures — not assumed.
- [ ] Every API call under the discovered base is intercepted and fulfilled
  with plausible JSON, and no reviewed shot printed an `UNMOCKED:` line;
  endpoints the app maps over return arrays; auth is seeded before first
  paint with `addInitScript` and the session/identity endpoint is mocked,
  returning `401` for the public routes.
- [ ] Every nested or guarded route was reached by clicking through from its
  rendered parent in the entry's `steps` — no direct `goto`, no faked
  `history.pushState` — and each shot waited for a known content selector
  or text to appear plus a short settle, not on `networkidle` or on
  "loading" disappearing.
- [ ] The captured matrix covers the discovered routes at phone and desktop
  widths in both light and dark, plus the interaction states under review,
  each driven by an entry's `steps` and named by its `state`.
- [ ] No shot reviewed as rendered appears in the harness's `UNRENDERED`
  list (content wait missed or page error), whatever its hash. Every PNG
  was hashed (`md5sum`) and no two distinct routes share a hash; identical
  hashes between media variants of one route, other than reduced motion,
  were filed as findings, not re-captured. Reduced motion was judged by
  the computed-style probe or in code, never by its hash. Any blank, stuck,
  or odd shot got its recorded API hits and console/page errors read,
  together with a one-shot `page.evaluate` dump of `location.href` and
  trimmed `document.body.innerText`, before the app's code was blamed.
- [ ] Every PNG was reviewed against all five checklist groups — layout,
  theme, state, a11y modes, anti-patterns — and the issue list was written
  before the first fix. `colorScheme`, `contrast: "more"`,
  `reducedMotion: "reduce"` and `forcedColors: "active"` were driven
  through `emulateMedia`. `prefers-reduced-transparency` was driven over CDP
  and confirmed with `matchMedia` before the shot, or, outside Chromium,
  verified in code.
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
