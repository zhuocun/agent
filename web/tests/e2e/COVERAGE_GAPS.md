# E2E Coverage — Baseline & Gap Report (ST-2)

Baseline measurement of the **unmodified** Playwright suite (81 tests) run
through ST-1's Istanbul coverage pipeline, plus an actionable gap inventory for
ST-3..ST-8 and a proposed CI floor for ST-9.

## 1. How this was produced

```bash
cd web && pnpm test:e2e:coverage   # COVERAGE=1 playwright test --retries=1 ; nyc report
# then for the precise per-metric numbers used below:
npx nyc report --reporter=text --reporter=text-summary --reporter=json-summary \
  --temp-dir coverage/.nyc_output --report-dir coverage
```

- All 81 specs passed (exit 0). Coverage is **FE-only**: the istanbul webpack
  pass in `next.config.ts` instruments `web/src/**` and the
  `coverage-fixture.ts` drains `window.__coverage__` after each test.
- Raw artifacts: `coverage/lcov.info`, `coverage/coverage-summary.json`,
  `coverage/index.html` (HTML report).

## 2. Baseline totals

| Metric | % | Covered / Total |
| --- | --- | --- |
| Statements | **67.81%** | 4368 / 6441 |
| Branches | **60.44%** | 2580 / 4268 |
| Functions | **68.68%** | 1066 / 1552 |
| Lines | **71.24%** | 4079 / 5725 |

100 source files exist under `src/**`; **92** were loaded by at least one test
(15 of those at 100% on every metric), **77** are <100% on at least one metric,
and **8** were never loaded at all (see §3). The totals above are computed over
the 92 loaded files only — never-loaded files do not appear in `.nyc_output`,
so they neither count toward nor drag the percentage (this matters for the ST-9
gate; see §6).

## 3. Structural limits of this measurement (read before ST-3..ST-8)

Eight files produce **zero** coverage data because the browser-side istanbul
collector never sees them. They split into two kinds:

### 3a. Server Components — unreachable by this method (Layer-C, by construction)

`window.__coverage__` only exists in the browser. The App Router entry files
have **no `"use client"`** and execute in the Node RSC process, so they can
never be instrumented by this pipeline regardless of which flows we add.

| File | Role | Disposition |
| --- | --- | --- |
| `src/app/layout.tsx` | root layout (fonts, metadata, providers) | Layer-C — exclude from gate |
| `src/app/page.tsx` | `/` route → renders `ChatThread` | Layer-C — exclude from gate |
| `src/app/manifest.ts` | PWA manifest generator | Layer-C — exclude from gate |
| `src/app/share/[token]/page.tsx` | share route → `PublicConversationView` | Layer-C — exclude from gate |
| `src/app/status/page.tsx` | status route → `PlatformStatusView` | Layer-C — exclude from gate |

The *client* leaf each route renders (`ChatThread`, `PublicConversationView`,
`PlatformStatusView`) **is** instrumented and shows up below, so the behavior is
still covered — only the thin server wrapper is invisible.

### 3b. Dead/unused modules — no importers (Layer-C, candidates for deletion)

| File | Finding | Disposition |
| --- | --- | --- |
| `src/components/chat/history-search-dialog.tsx` | superseded by `command-palette.tsx` ("former HistorySearchDialog"); **no importers** | delete (ST-4) or exclude |
| `src/components/chat/spend-dialog.tsx` | `SpendDialog` defined but **no importers**; spend now lives in settings General tab | delete (ST-5/ST-8) or exclude |
| `src/components/ui/skeleton.tsx` | `Skeleton` exported but **never imported** anywhere | delete (ST-7) or exclude |

> **Recommendation for ST-9:** add a `.nycrc` that excludes `src/app/**` and
> the three dead modules (or delete the dead modules in their owning subtask).
> Otherwise an `--all`-style gate would score them 0% and make a meaningful
> floor impossible.

## 4. Per-file baseline table

Full `nyc --reporter=text` output is saved at
`/opt/cursor/artifacts/coverage_baseline_per_file.txt`. Group rows + the 15
fully-covered files are omitted here; the 77 <100% files are detailed in §5.

Fully covered (100% on all four metrics): `theme-provider.tsx`,
`ai-disclosure.tsx`, `live-region.tsx`, `typing-indicator.tsx`,
`ui/button.tsx`, `ui/checkbox.tsx`, `ui/collapsible.tsx`, `ui/scroll-area.tsx`,
`ui/separator.tsx`, `ui/switch.tsx`, `lib/i18n/messages.ts`, `lib/mock-data.ts`,
`lib/model-tiers.ts`, `lib/reasoning-efforts.ts`, `lib/utils.ts`.

## 5. Gap inventory by ST bucket

Columns: **S/B/F/L** = statements / branches / functions / lines %. **Flow** =
Layer-B flow ID (1–19) the gap should be closed by, or **C** = Layer-C
(defensive/unreachable — leave to the threshold, don't chase). Uncovered line
numbers are the istanbul DA-zero lines; full lists in
`coverage/lcov.info`.

### ST-3 — core chat & streaming (composer, message-list, reasoning, follow-ups, markdown, stream/data layer)

| File | S | B | F | L | Flow | Key uncovered | Hypothesis for missing flow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `chat-thread.tsx` | 55.8 | 43.7 | 51.5 | 57.6 | 2,3 | ~1.5k lines across 658–4198 | Mega-orchestrator: most branches (edit/retry/branch-switch, error toasts, keyboard handlers, deep-link tabs) never driven. Biggest single win. |
| `composer.tsx` | 68.0 | 65.8 | 76.1 | 70.7 | 2,7 | 493–507,984–1067,1075–1173 | Attachment/paste/drag-drop, slash/template triggers, IME and send-disabled edge paths unexercised. |
| `assistant-message.tsx` | 69.8 | 66.7 | 68.6 | 72.6 | 2,12 | 125–142,291–302,409–512,654–773 | Branchy render: tool/agentic/error/citation variants + collapse/expand and copy paths not hit. |
| `user-message.tsx` | 28.0 | 37.3 | 31.6 | 30.2 | 2,3 | 43–193 (most of file) | Edit-in-place / resend / attachment preview never triggered — almost entirely untested. |
| `message-actions.tsx` | 30.0 | 60.3 | 25.0 | 32.1 | 3 | 82–140,263–393,494 | Copy/regenerate/continue/feedback/read-aloud action handlers barely invoked. |
| `message-list.tsx` | 93.8 | 75.0 | 100 | 100 | 2 | branches 207,242,261,281–291,302 | Empty/loading/virtualization branch combinations partially covered. |
| `markdown-renderer.tsx` | 97.4 | 66.7 | 87.5 | 97.1 | 2 | 73 | One rehype/citation branch + a code-block variant unhit. |
| `reasoning-panel.tsx` | 87.5 | 94.1 | 75.0 | 87.5 | 12 | 40–41 | Collapsed↔expanded toggle / empty-reasoning branch missed. |
| `attribution-row.tsx` | 93.8 | 65.5 | 100 | 93.8 | 12 | 32 | Tier/cost attribution badge variant (e.g. BYOK vs platform) not rendered. |
| `follow-up-chips.tsx` | 84.2 | 57.1 | 83.3 | 94.1 | 19 | 72 | Chip-click → composer prefill branch (and empty list) partly missed. |
| `welcome-screen.tsx` | 90.0 | 86.4 | 80.0 | 90.0 | 1,2 | 177 | One CTA/example-prompt branch on empty thread unhit. |
| `stream-client.ts` | 74.7 | 59.0 | 82.8 | 80.3 | 2,3 | 745–759,1198–1336,1402–1406 | SSE error/abort/reconnect, tool-call deltas, and stop/continue control frames not exercised. |
| `apiClient.ts` | 79.5 | 62.5 | 78.9 | 84.5 | 1,4 | 198–204,307–308,455–720 | Non-2xx/error branches of many endpoints (retry, 401, parse-fail) untested. Cross-cutting. |
| `offline-store.ts` | 63.4 | 52.0 | 53.1 | 71.3 | 1 | 89–110,163–185,201,210 | Offline queue / IndexedDB persistence + replay path not driven (online-only tests). |
| `format-attachment-size.ts` | 66.7 | 100 | 100 | 50.0 | 7 | 4 | Non-byte (KB/MB) size branch — needs a sized attachment. |
| `types.ts` | 75.0 | 100 | 66.7 | 66.7 | C | 644 | Runtime helper/guard in a types module; mostly type-only. Layer-C. |
| `chat-chrome-padding.ts` | 100 | 50.0 | 100 | 100 | C | branch 33–34 | Defensive viewport-padding branch; low value. Layer-C. |
| `scheduler-yield.ts` | 36.8 | 50.0 | 33.3 | 43.8 | C | 38–50 | `scheduler.yield`/`isInputPending` feature-detect fallbacks; env-dependent. Mostly Layer-C. |
| `motion.ts` | 66.7 | 66.7 | 100 | 100 | C | branch 2 | `prefers-reduced-motion` branch; hard to flip in CI. Layer-C. |
| `use-virtual-message-window.ts` | 96.8 | 83.9 | 100 | 100 | 18 | 37–45,57,117,122 | Virtualization window edges (very long thread scroll) not hit. |
| `use-speech-recognition.ts` | 60.0 | 50.0 | 84.6 | 65.5 | 18 | 115–172,184–185 | Voice input: result/err/end handlers need a mocked SpeechRecognition. Partly Layer-C (no API in Chromium headless). |
| `use-speech-synthesis.ts` | 47.4 | 37.5 | 54.5 | 50.0 | 18 | 125–198,203–206 | Read-aloud: utterance lifecycle needs mocked speechSynthesis. Partly Layer-C. |
| `use-visual-viewport.ts` | 74.1 | 50.0 | 66.7 | 83.3 | 18 | 32,65–68 | Mobile keyboard visualViewport resize path; desktop-only runner. Partly Layer-C. |

### ST-4 — navigation, palette, shortcuts, theming, i18n, banners, coachmark

| File | S | B | F | L | Flow | Key uncovered | Hypothesis for missing flow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `app-shell.tsx` | 49.2 | 21.4 | 72.7 | 50.9 | 1 | 39–83,166–204 | Responsive shell: drawer/sidebar collapse, mobile vs desktop layout branches unexercised. |
| `app-header.tsx` | 100 | 66.7 | 100 | 100 | 4 | branches 113,181–221 | Header action/menu branch variants (e.g. logged-in vs guest) partly missed. |
| `sidebar.tsx` | 72.8 | 64.5 | 66.7 | 76.6 | 4,5 | 195–209,1315–1373,2300–2510 | Pin/archive/tag/group, project sections, swipe actions, context menus not all driven. |
| `command-palette.tsx` | 76.5 | 70.1 | 74.2 | 79.2 | 6,19 | 257–315,422–491,626–897 | Palette search modes, history results, keyboard nav, and action dispatch branches missed. |
| `slash-commands-popover.tsx` | 43.6 | 20.0 | 40.0 | 43.8 | 19 | 56–58,94–160 | Slash-command menu open/filter/select almost entirely untested. |
| `shortcuts-dialog.tsx` | 77.2 | 78.3 | 76.5 | 77.3 | 18 | 151–166,200–219,357–358 | Per-shortcut rebinding/reset rows + conflict states not driven. |
| `theme-toggle.tsx` | 87.5 | 85.7 | 66.7 | 85.7 | 19 | 55 | One theme-cycle branch (system→light→dark) unhit. |
| `install-coachmark.tsx` | 48.4 | 37.5 | 50.0 | 50.0 | 19 | 23–54 | PWA install prompt (`beforeinstallprompt`) flow never fired. Partly Layer-C (event not emitted headless). |
| `degraded-status-banner.tsx` | 87.5 | 50.0 | 71.4 | 95.2 | 19 | 95 | Degraded/recovered transition branch needs a degraded `/status`. |
| `temporary-chat-banner.tsx` | 100 | 100 | **0** | 100 | 19 | the dismiss callback fn | Banner renders but its dismiss handler is never invoked. |
| `key-caps.tsx` | 100 | 75.0 | 100 | 100 | 18 | branch 19 | One platform (mac/win) key-glyph branch unhit. |
| `shortcut-defaults.ts` | 76.1 | 58.3 | 80.0 | 80.0 | 18 | 114–335 (scattered) | Several default shortcut entries/handlers never registered or fired. |
| `shortcut-format.ts` | 71.9 | 45.0 | 85.7 | 90.0 | 18 | 21,36 | Modifier-combo formatting branches (e.g. Shift/Alt) missed. |
| `use-keyboard-shortcuts.ts` | 82.9 | 59.3 | 85.7 | 96.7 | 18 | 81 | A guard branch (input-focused / disabled) not hit. |
| `lib/i18n/context.tsx` | 69.0 | 26.9 | 66.7 | 77.1 | 19 | 37–39,80–83,108,121–125 | Locale switch / missing-key fallback / interpolation branches untested (only default locale used). |
| `use-haptic.ts` | 71.4 | **0** | 100 | 100 | C | branch 24–25 | `navigator.vibrate` feature-detect; absent in headless. Layer-C. |
| `use-swipe-actions.ts` | 51.6 | 40.5 | 90.0 | 56.3 | 18 | 138–212,242–259 | Touch swipe gestures on sidebar rows; pointer/touch events not simulated. Partly Layer-C. |

### ST-5 — settings, BYOK, preferences, account, model/tier, memory, templates

| File | S | B | F | L | Flow | Key uncovered | Hypothesis for missing flow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `settings-dialog.tsx` | 58.6 | 62.9 | 57.1 | 60.5 | 17,7 | 386–470,998–1153,1472–1528 | Many tabs/sections (export, delete, retention, budget editor, deep-links) not opened. |
| `byok-form.tsx` | 73.3 | 56.9 | 72.2 | 73.4 | 8 | 137–197,281–322,357 | Add/validate/rotate/remove key, error + masked-display branches under-tested. |
| `auth-dialog.tsx` | 62.7 | 69.6 | 70.0 | 64.3 | 17 | 38–55,84–92,106–107,196 | Sign-up vs sign-in toggle, validation errors, and post-auth merge path missed. |
| `activity-dialog.tsx` | 67.3 | 51.3 | 61.5 | 73.5 | 17 | 121–150,273 | Activity list paging / empty / per-session-revoke branches not driven. |
| `memory-dialog.tsx` | 88.0 | 69.0 | 95.2 | 93.0 | 14 | 76–77,99,125,139 | Edit/delete/disable-memory branches + empty state missed. |
| `model-directory-dialog.tsx` | 89.7 | 79.3 | 91.7 | 94.3 | 7 | 216–217 | One filter/sort or unavailable-tier branch unhit. |
| `model-mode-picker.tsx` | 87.5 | 88.7 | 82.3 | 88.9 | 7 | 124,183–184,384,452–469,686 | Mode switch (auto/manual), reasoning + web-search + vision toggles partly covered. |
| `tier-picker.tsx` | 76.9 | 85.7 | 71.4 | 75.0 | 7 | 46–47,157 | Disabled/unavailable tier rows and selection-persist branch missed. |
| `template-library-dialog.tsx` | 89.5 | 75.0 | 92.3 | 93.6 | 15 | 76–77,106,141,155,277 | Create/edit/delete template + search branches not all driven. |
| `template-picker-popover.tsx` | 78.4 | 51.4 | 90.0 | 83.3 | 15 | 39–41,82–84 | Picker open/filter/insert-into-composer branches missed. |
| `usage-meter.tsx` | 100 | 56.6 | 100 | 100 | 13 | branches 32–193 | Threshold color/over-budget/near-limit branch variants not rendered. |

### ST-6 — share & status routes

| File | S | B | F | L | Flow | Key uncovered | Hypothesis for missing flow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `share-dialog.tsx` | 60.2 | 56.7 | 70.0 | 63.3 | 16 | 39–47,87–98,126–205 | Create/revoke link, copy, visibility toggle, and error branches under-tested. |
| `public-conversation-view.tsx` | 82.0 | 64.3 | 72.2 | 91.4 | 16 | 68–71,90 | Expired/not-found/empty public-view branches not hit. |
| `public-attribution-row.tsx` | 91.7 | 50.0 | 100 | 91.7 | 16 | 26 | Public attribution badge variant unhit. |
| `platform-status-view.tsx` | 69.0 | 46.7 | 63.6 | 83.3 | 1 | 47–60 | Degraded/outage status states (only healthy rendered). |
| `app/share/[token]/page.tsx` | — | — | — | — | C | not loaded | Server component — Layer-C (§3a). |
| `app/status/page.tsx` | — | — | — | — | C | not loaded | Server component — Layer-C (§3a). |

### ST-7 — UI primitives via consuming surfaces

| File | S | B | F | L | Flow | Key uncovered | Hypothesis for missing flow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ui/toast.tsx` | 72.9 | 68.4 | 58.8 | 78.6 | 19 | 51,67–69,81,131,181–194 | Toast variants (success/error/action) + auto-dismiss/queue not all fired by surfaces. |
| `ui/dropdown-menu.tsx` | 100 | 44.4 | 53.3 | 100 | 7 | branches 22,128–131 | Submenu/checkbox-item/disabled branches unused by current consumers. |
| `ui/drawer.tsx` | 100 | 55.5 | 30.0 | 100 | 18 | branches 41–84 | Drawer drag/snap/dismiss handlers (mobile) rarely invoked. |
| `ui/dialog.tsx` | 92.0 | 84.6 | 86.7 | 95.8 | 19 | 84 | One close-on-overlay / esc branch missed. |
| `ui/tooltip.tsx` | 100 | 80.0 | 100 | 100 | 19 | branch 8 | Delay/side tooltip branch unhit. |
| `ui/badge.tsx` | 100 | **0** | 100 | 100 | 7 | branch 32 | Variant-class branch never exercised with a non-default variant. |
| `ui/skeleton.tsx` | — | — | — | — | C | not loaded | Dead/unused (§3b) — delete or exclude. |

### ST-8 — agentic, tools, compare, cost/spend, web-search edge branches

| File | S | B | F | L | Flow | Key uncovered | Hypothesis for missing flow |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `agentic-assistant-parts.tsx` | 66.7 | 50.0 | 80.0 | 71.4 | 10 | 50,87,94–112 | Deep-research plan/step/result render branches not driven end-to-end. |
| `subagent-panel.tsx` | 85.0 | 72.4 | 88.9 | 88.9 | 10 | 68,74–76,251 | Subagent expand/collapse + status (running/failed) branches missed. |
| `agentic-layout.ts` | 97.0 | 94.4 | 100 | 100 | 10 | 40 | One layout-tree branch for nested subagents unhit. |
| `tool-part.tsx` | 80.7 | 78.6 | 85.7 | 86.5 | 11 | 310,351–377 | Tool call pending/error/result + approve/deny render branches partial. |
| `tool-group-panel.tsx` | 85.7 | 60.0 | 100 | 100 | 11 | branches 33–35,81–82 | Grouped-tool collapse + mixed-status branches missed. |
| `tool-groups.ts` | 81.4 | 67.0 | 100 | 85.8 | 11 | 82–101,399–424 | Tool-group classification branches for less-common tool kinds untested. |
| `compare-view.tsx` | 96.8 | 84.6 | 91.7 | 96.4 | 9 | 189 | One compare layout/error branch unhit. |
| `compare-column.tsx` | 93.5 | 82.3 | 100 | 93.3 | 9 | 78,87 | Per-column loading/error/winner branches partial. |
| `web-search-panel.tsx` | 85.7 | 87.5 | 100 | 89.2 | 7 | 27–28,39,65 | Empty-results / collapsed / source-open branches missed. |
| `sources-panel.tsx` | 74.4 | 58.1 | 76.9 | 75.0 | 7,10 | 49–100,236,306–309 | Citation list expand/dedup/open-source branches under-tested. |
| `spend-analytics-panel.tsx` | 44.8 | 84.1 | 64.3 | 48.1 | 13 | 29–69,290–309 | Spend charts/series + range-filter rendering largely untested (rate-limited 429s seen in baseline run). |
| `cost-estimate.ts` | 100 | 85.7 | 100 | 100 | 12 | branch 53 | One pricing branch (free/unpriced tier) unhit. |
| `money.ts` | 64.7 | 52.9 | 66.7 | 75.0 | 12 | 17,34–35 | Currency/rounding/zero-and-sub-cent formatting branches missed. |
| `telemetry.ts` | 66.7 | **0** | 50.0 | 100 | C | branch 13 | Analytics enable/disable gate; env-dependent. Mostly Layer-C. |
| `citation-rehype.ts` | 91.4 | 84.2 | 100 | 100 | 2 | branches 45,57,77 | Malformed/duplicate citation parse branches unhit. |
| `spend-dialog.tsx` | — | — | — | — | C | not loaded | Dead/unused (§3b) — delete or exclude. |

> `use-swipe-dismiss.ts` (S=16.1, B=28.6) is consumed by `ui/drawer.tsx` /
> dialogs and belongs with ST-7's drawer work; it needs simulated
> pointer/touch drag and is partly Layer-C (touch gestures in a desktop runner).

## 6. Proposed Layer-C threshold for ST-9

**What is realistically reachable.** After ST-3..ST-8 land their Layer-B flows,
the persistent residue is genuine Layer-C: feature-detect fallbacks
(`scheduler.yield`, `navigator.vibrate`, `visualViewport`, speech APIs absent in
headless Chromium), `prefers-reduced-motion`, PWA `beforeinstallprompt`,
defensive `catch`/parse-fail arms in `apiClient`/`stream-client`, and
type-guard helpers in `types.ts`. Branch coverage stays structurally the lowest
because each of those is a branch.

**Pre-requisite (do in ST-9 or earlier):** add a `.nycrc` that **excludes**
`src/app/**` and the three dead modules from §3b (or delete the dead modules),
so the gate scores only browser-reachable code.

**Proposed CI floor** (`nyc check-coverage`, global), chosen ~3–5 pts under the
realistically reachable ceiling to absorb run-to-run noise:

| Metric | Baseline (now) | Realistic ceiling (post Layer-B) | **ST-9 floor (propose)** |
| --- | --- | --- | --- |
| Statements | 67.81% | ~92% | **85%** |
| Lines | 71.24% | ~92% | **85%** |
| Functions | 68.68% | ~90% | **82%** |
| Branches | 60.44% | ~82% | **72%** |

Rationale: branches lag statements/lines by ~10 pts both at baseline and at the
ceiling, so its floor is set lower. Start at these numbers, confirm green once
ST-8 merges, then **ratchet each floor up to ~2 pts under the achieved number**
to prevent silent regressions without making the gate brittle.

## 7. Bucket summary (gap counts)

| Bucket | Files needing attention | Layer-B targets | Layer-C / dead |
| --- | --- | --- | --- |
| ST-3 core chat & streaming | 23 | 19 | 4 (`types.ts`, `chat-chrome-padding.ts`, `scheduler-yield.ts`, `motion.ts`) |
| ST-4 nav/palette/shortcuts/i18n/banners | 18 | 16 | 2 (`use-haptic.ts`; `history-search-dialog.tsx` dead) |
| ST-5 settings/BYOK/account/model/templates | 11 | 11 | 0 |
| ST-6 share & status | 6 | 4 | 2 (`app/share/[token]/page.tsx`, `app/status/page.tsx` — server) |
| ST-7 UI primitives | 8 | 7 | 1 (`ui/skeleton.tsx` dead) |
| ST-8 agentic/tools/compare/cost | 16 | 14 | 2 (`telemetry.ts`; `spend-dialog.tsx` dead) |
| Cross-cutting server entries | 3 | 0 | 3 (`app/layout.tsx`, `app/page.tsx`, `app/manifest.ts` — §3a) |
| **Total** | **85** | **71** | **14** |

= **77** loaded files <100% + **8** never-loaded (§3) = **85** files needing
attention; ~**71** are Layer-B reachable, ~**14** are Layer-C
(defensive/unreachable/dead). Bucket assignment is by primary owning surface;
a handful of `lib/` hooks are cross-cutting (noted inline). `history-search-dialog.tsx`
(ST-4), `use-swipe-dismiss.ts` (ST-7) are folded into their owning buckets above.
