---
name: visual-ux-sweep
description: Review and fix UI/UX regressions in a web app via headless-browser screenshots across routes, viewports, themes, and interaction states. Use when asked to audit the UI, review the design, find visual or accessibility regressions, screenshot the app, verify visual changes look right, or "make the UI look right." Framework-agnostic (React/Vue/Svelte/plain). Pairs each screenshot with a root-cause probe and a surgical fix; not for product/feature work or new pages.
---

# Visual UX Sweep

Find UI/UX issues by screenshot review and fix them in tight commits.
The screenshot matrix is the discovery loop — don't skip it because
"the change looks small." A screenshot you never confirmed actually
rendered is worse than no screenshot: it hides the regression behind a
loading spinner.

## Loop

1. **Set up the capture environment.** See **Setup** — this is where
   sweeps fail, so do every step.
2. **Discover the surface** (routes × viewports × themes × interaction
   states) from the repo, not from memory. See **Repo-agnostic
   discovery**.
3. **Capture** the matrix with the harness in
   `references/playwright-harness.md`. Use the recipe verbatim;
   parameterize the repo-specific bits.
4. **Confirm each shot rendered** before trusting it. See **Verify the
   capture** — hash the PNGs; identical hashes across distinct
   routes/themes mean a route never rendered.
5. **Review** every PNG against the **Review checklist**. List issues
   first; don't fix yet.
6. **Probe root cause** for every issue with a one-shot `page.evaluate`
   before editing. Reading code excerpts guesses wrong on framework
   traps.
7. **Fix in themed batches**, one commit each. Re-capture after each
   batch and confirm the issue is gone.
8. **Quality gates + clean repo** before commit. See **Quality bar**.

## Setup (do every step — this is where sweeps fail)

1. **Install the browser driver and a browser binary.** Playwright is
   usually NOT a project dependency, so installing it must not pollute
   the manifest:
    - `npm i playwright --no-save` (keeps `package.json` / lockfile
      untouched).
    - `npx playwright install chromium` (downloads ~300 MB — Chromium
      plus a headless shell; may need `--with-deps` on a bare box). If
      the network blocks the CDN, stop and tell the user — the sweep
      can't run here.
    - Browsers may land outside the default cache when
      `PLAYWRIGHT_BROWSERS_PATH` is set in the environment; the runtime
      reads the same variable, so leave it as-is and just verify a
      launch (`chromium.launch()`) succeeds before capturing.
2. **Capture against a PRODUCTION BUILD, not the dev server.** Dev
   servers (Vite, webpack, Next dev) lazily compile route-split / heavy
   module graphs on first hit; under headless automation a heavy route
   can sit in its loading/Suspense state indefinitely and never fire its
   data queries — you screenshot a spinner and never know. Build once
   and serve the build on a stable port:
    - `npm run build`, then serve it: `npx vite preview --port <p>`,
      `npx serve -s dist`, `next start`, etc.
    - Production chunks are pre-bundled and load deterministically.
    - **Necessary, not always sufficient.** The build is the reliable
      surface to *launch* from, but a deeply nested route can still fail
      to render when reached by a direct deep-link — reach those by UI
      navigation (see below). Verified on a real app: a list page that
      hung forever in dev rendered on the preview build, but the nested
      board route under it stayed stuck on a direct `goto` and only
      rendered after a click-through from its parent.
    - Caveat: a build may use different env defaults than dev (feature
      flags, API engine), so some chrome differs — fine for visual
      review; note it. Only fall back to the dev server for a trivial
      app with no route splitting.
3. **Put the capture script where its imports resolve.** ESM resolves
   `import "playwright"` from the script file's own directory, not the
   cwd. Running a script from `/tmp` fails with `ERR_MODULE_NOT_FOUND`.
   Either keep the script inside the repo, or symlink the repo's
   `node_modules` into the script's directory
   (`ln -sfn <repo>/node_modules <scriptdir>/node_modules`).

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

- **Intercept ALL API calls** in the browser context
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
  the child — do NOT deep-link `goto` it or fake `history.pushState`.
  Verified: a direct `goto` to a nested route left it stuck in Suspense
  with only the app-shell queries firing (`users`, `health`, members);
  clicking into it from the rendered parent fired every data query and
  rendered it fully. The harness reference shows the click-through.
- **Wait for content, not for "loading" to vanish.** A "no loading
  text" or `networkidle` check passes prematurely (e.g. just before an
  auth redirect kicks off the next load). Wait for a known content
  selector/text to APPEAR (generous timeout), then a short settle, then
  shoot.

## Verify the capture (cheap, catches silent failures)

- **Hash every PNG** (`md5sum`). Identical hashes across distinct
  routes/themes mean those routes did NOT render — you captured the same
  loading/error screen. Re-navigate or fix the harness; never review or
  commit off un-rendered shots.
- **Probe before blaming the code.** For any blank/stuck/odd shot, run a
  one-shot `page.evaluate` dumping `location.href`,
  `document.body.innerText` (trimmed), the set of intercepted API calls,
  and console/page errors. This distinguishes a harness/mock artifact
  from a real app bug (e.g. it reveals "only the auth endpoints fired,
  the route's own queries never did").

## Review checklist

Per PNG, in both light and dark and at phone + desktop widths:

- **Layout:** overflow / clipping, content under fixed chrome, broken
  grids, text truncation/ellipsis on labels, safe-area gaps.
- **Theme:** any element that ignores dark mode (light-mode hex baked as
  a CSS-var fallback), low-contrast text, invisible borders.
- **State:** loading/empty/error parity; focus rings present and
  ≥ 3:1; disabled vs. active read correctly; touch targets ≥ 44 px on
  coarse pointers.
- **A11y modes:** drive `colorScheme`, `contrast: "more"`,
  `reducedMotion: "reduce"`, and `forcedColors: "active"` through
  `emulateMedia` (these are the options it actually supports) — they are
  routinely unstyled. `prefers-reduced-transparency` has no `emulateMedia`
  switch yet, so verify that one in code / manually.
- **Anti-patterns that look wrong but are correct:** intentional
  translucency/blur (glass), deliberately muted "coming soon" controls,
  brand-specific spacing. Confirm against tokens/design intent before
  "fixing" them.

## Quality bar

- Fix **root causes, not symptoms**.
- Do **not** add features, refactor architecture, introduce
  dependencies, or write new tests unless an existing test breaks.
- Gates before each commit: typecheck clean, `jest <touched-paths>`
  green, full test suite green.
- **Keep the repo clean.** Browser driver is `--no-save`; capture script
  + screenshots live outside the repo (or a gitignored path). Confirm
  `git status` shows only the intended app fix — never the harness, the
  driver, or the PNGs.
