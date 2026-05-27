# Mobile & Cross-Platform — Fresh Research + PRD Review (2026-05-27)

**Scope:** (1) fresh 2025–2026 online research for NEW ideas/best-practices in mobile-web & cross-platform AI-chat UX/engineering not already in the existing docs; (2) a critical review of `docs/prd/03-mobile-cross-platform.md`.
**Reviewer inputs:** `docs/research/02-mobile-responsive.md`, `docs/prd/03-mobile-cross-platform.md`, `docs/prd/00-product-overview.md`.

> **Confidence flags**
> - **[Verified]** — supported by a 2025–2026 source fetched/searched in this pass (URL cited).
> - **[Recall]** — general engineering/UX knowledge, not re-verified this pass; treat as a strong default, validate in spec/prototype.
> - **[Uncertain]** — genuinely unsettled or conflicting evidence; do not commit without a spike.

---

## 1. Headline

The existing research and PRD are **strong, well-sourced, and mostly current** — the category-convergence analysis, delivery strategy (PWA→Capacitor, RN rejected), accessibility baseline, and offline-first model are all sound. However, this pass surfaced **two outdated factual claims that are load-bearing in the PRD** and several **new opportunities and risks** the docs miss. The two corrections that matter most:

1. **`dvh` does NOT resolve the iOS keyboard problem.** The PRD makes "`dvh` + `interactive-widget=resizes-content`" a **[P0]** composer mechanism. On **iOS/iPadOS Safari the on-screen keyboard resizes only the *visual* viewport, not the layout viewport**, so `dvh` (and `svh`/`lvh`) do **not** shrink when the keyboard opens. `interactive-widget` is an **Android/Chromium-only** knob. The PRD's primary mechanism is therefore correct on Android and **insufficient on iOS** — exactly the platform it flags as highest-risk. iOS still requires a `visualViewport`-based JS approach (or the VirtualKeyboard API). **[Verified]**
2. **iOS PWA storage is NOT ~50 MB.** Since **Safari 17 (Sept 2023)**, per-origin quota is computed from disk space (browser apps up to ~60% of disk; overall up to ~80%) — typically **tens of GB**, reported via `navigator.storage.estimate()`. The PRD's "~50 MB cap" (repeated in §4.6, §4.9, §5.3, §6.2, §6.4, §8) is **outdated** and weakens the durable-offline trigger reasoning. The real iOS constraint is **eviction** (7-day ITP eviction of non-persisted data), not a tiny cap. **[Verified]**

Everything below expands on these and adds new material.

---

## 2. New ideas & opportunities (not in existing docs)

### 2.1 `VirtuosoMessageList` — a purpose-built AI-streaming-chat virtualizer
- **What:** React Virtuoso now ships a dedicated **`VirtuosoMessageList`** component built specifically for human/AI conversations: streaming responses, auto-scroll, stick-to-bottom, imperative data API for controlling scroll on message arrival, virtualized rendering. The docs reference generic Virtuoso/TanStack Virtual; this is a newer, more targeted option that directly addresses the PRD's "TOP SPIKE." **[Verified]** (virtuoso.dev, github.com/petyosi/react-virtuoso)
- **Also new:** **Virtua** (~3 kB) has *built-in reverse scrolling* and is reported as far easier than TanStack Virtual for chat; TanStack Virtual is explicitly weak for bidirectional/chat use cases per its own maintainers' discussions. **[Verified]** (bestofjs.org/projects/virtua, github.com/TanStack/virtual discussions #195, #477)
- **Why it matters:** de-risks the #1 technical spike. `VirtuosoMessageList` is **commercially licensed**, so the spike must compare: (a) `VirtuosoMessageList` (fastest, license cost), (b) Virtua (free, reverse-scroll built in), (c) TanStack Virtual (most flexible, most effort).
- **Suggestion:** **MVP** — add all three to the §9 spike; default expectation = Virtua or `VirtuosoMessageList`.
- Sources: https://virtuoso.dev/ · https://github.com/petyosi/react-virtuoso · https://bestofjs.org/projects/virtua · https://github.com/TanStack/virtual/discussions/477

### 2.2 INP is now THE failing CWV — adopt `scheduler.yield()` + token-batching as an explicit pattern
- **What:** As of 2026, **INP is the most commonly failed Core Web Vital (~43% of sites fail the 200 ms threshold).** The single most effective fix is breaking long tasks with **`scheduler.yield()`** (with a `setTimeout(0)` fallback), reported to cut p75 INP by 60–65%. For a tap-heavy streaming composer this is directly relevant. **[Verified]** (dev.to "Core Web Vitals in 2026", nitropack.io scheduler.yield, web.dev/optimize-long-tasks)
- **Why it matters:** The PRD sets an INP ≤200 ms budget (§4.10/§8) but specifies **no technique** to hit it. Streaming + markdown re-parsing + virtualization are classic long-task generators.
- **Suggestion:** **MVP** — make "yield to main between expensive chunks (`scheduler.yield()`)" and "coalesce token renders per rAF" named P0 implementation requirements, not just a P1 nice-to-have (PRD currently tags render-coalescing **[P1]** — should be **[P0]** given INP is the hardest budget).
- Sources: https://dev.to/benriemer/core-web-vitals-in-2026-the-practical-fixes-for-inp-lcp-and-cls-that-actually-work-4ef0 · https://nitropack.io/blog/post/introducing-scheduler-yield · https://web.dev/articles/optimize-long-tasks

### 2.3 Container queries are now baseline-safe — viable for the layout shell
- **What:** Container **size** queries have been Baseline since 2023 and cover ~93%+ of users (Chrome 105+, Firefox 110+, Safari 16+), usable in production with zero fallback. 2026 guidance: media queries for page-level shell decisions, container queries for component-level adaptation. **[Verified]** (LogRocket "Container queries in 2026", MDN)
- **Why it matters:** The PRD offers "container queries OR a breakpoint hook" as the single-source-of-truth (§4.1, §5.3) but treats it as undecided. The pane *shell* (how many panes / drawer mode) is genuinely viewport-level → media queries / a breakpoint hook are right; but **the artifact panel and composer toolbar that need to adapt to their *available column width*** (e.g., the 3rd column on desktop vs full-screen on mobile) are exactly the component-level case container queries solve cleanly.
- **Suggestion:** **MVP** — shell = viewport breakpoints; reusable panes (artifact, composer toolbar, message bubble action row) = container queries. Resolve the "OR" in the PRD.
- Sources: https://blog.logrocket.com/container-queries-2026/ · https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries

### 2.4 iOS haptics ARE now possible (label-switch trick, iOS 18+)
- **What:** WebKit still exposes **no `navigator.vibrate`** on iOS. But since **iOS 18**, Safari fires haptic feedback on a `<input type="checkbox switch">` toggled via an associated `<label>` — programmatically `click()`-ing the label emits haptics. OSS wrappers exist (2026). **[Verified]** (caniuse.com/vibration, github ionic-framework #29942, medium @posaune0423 2026)
- **Why it matters:** The PRD tags **[P1] Haptics** assuming the Vibration API and silently gets nothing on iOS. This trick gives the privacy-first product a small but real iOS polish win that incumbents skip.
- **Suggestion:** **P1** — implement haptics via Vibration API (Android) + label-switch shim (iOS 18+); feature-detect and degrade silently elsewhere.
- Sources: https://caniuse.com/vibration · https://github.com/ionic-team/ionic-framework/issues/29942 · https://medium.com/@posaune0423/i-open-sourced-an-oss-library-for-arbitrary-haptic-feedback-in-ios-safari-5b8ca74a5f05

### 2.5 `overscroll-behavior: contain` — and DROP pull-to-refresh
- **What:** `overscroll-behavior-y: contain` on the scroll container prevents scroll-chaining and **browser pull-to-refresh**. A real AI-chat project (LibreChat) filed an issue because **pull-to-refresh causes accidental full chat reloads** on mobile — destroying streaming state. **[Verified]** (MDN overscroll-behavior, developer.chrome.com/blog/overscroll-behavior, github LibreChat #8746)
- **Why it matters:** The PRD proposes **[P1] Pull-to-refresh** as a feature. For a *streaming* chat, native pull-to-refresh is more often a **footgun** (accidental reload mid-stream) than a feature. This is a contradiction with the PRD's own "interrupted-stream recovery" goal.
- **Suggestion:** **MVP** — `overscroll-behavior: contain` on the message list and app root is a P0 hardening item; **remove pull-to-refresh** (or restrict it to the history drawer only, never the conversation).
- Sources: https://developer.chrome.com/blog/overscroll-behavior · https://github.com/danny-avila/LibreChat/issues/8746

### 2.6 Local-first / sync-engine ecosystem has matured — name a candidate
- **What:** 2026 offline-first stacks now include batteries-included sync engines (Dexie Cloud, PowerSync, ElectricSQL, RxDB) and CRDT libs (Yjs, Automerge-WASM) described as "the gold standard for mobile sync." Dexie itself now offers Dexie Cloud sync/collaboration. **[Verified]** (Dexie.org, cssauthor.com offline-first 2026, rxdb.info, dev.to "Advanced Syncing Algorithms 2026")
- **Why it matters:** The PRD picks Dexie/IndexedDB and a hand-rolled queue (sync internals deferred to PRD 04). Fine for MVP, but the spec should at least **acknowledge the build-vs-buy decision** so PRD 04 doesn't reinvent a sync engine. For a privacy-first product, CRDT/local-first also aligns with the "server is best-effort, local is real" story.
- **Suggestion:** **P1** — flag the sync-engine build-vs-buy explicitly as a PRD 04 dependency; MVP can stay hand-rolled.
- Sources: https://dexie.org/ · https://cssauthor.com/offline-first-tech-stack/ · https://rxdb.info/articles/local-first-future.html

### 2.7 Declarative Web Push + iOS 26 default-web-app — re-engagement is slightly less bad than the PRD assumes
- **What:** Safari 18.4 (Mar 2025) shipped **Declarative Web Push** (push without a service worker; now a W3C Working Draft and the preferred format). **iOS 26**: every site added to Home Screen **defaults to opening as a web app even without a manifest**, lowering install friction. Safari 18.4 also added **Screen Wake Lock** for home-screen web apps. **[Verified]** (webkit.org Safari 18.4, aimtell.com "State of Declarative Web Push 2026", magicbell.com 2026, mobiloud.com 2026)
- **Why it matters:** The PRD's iOS-push pessimism is still broadly right (install-gated, low opt-in), but the *implementation* story improved (Declarative Web Push is simpler/more reliable) and iOS 26 reduces install friction. The EU restriction (see §3) was also **reversed**. These soften — but do not eliminate — Capacitor trigger #1.
- **Suggestion:** **MVP/P1** — use Declarative Web Push for the Android/iOS-installed push path; use Screen Wake Lock during long streaming responses so the screen doesn't dim mid-answer.
- Sources: https://webkit.org/blog/16574/webkit-features-in-safari-18-4/ · https://aimtell.com/blog/state-of-declarative-web-push-2026 · https://www.mobiloud.com/blog/progressive-web-apps-ios

### 2.8 Incumbent mobile-web is genuinely weak — the wedge is real and specific
- **What:** ChatGPT has *documented* mobile keyboard/composer bugs: an iOS issue where the skill picker is hidden behind the keyboard over a long composer, and Android reports where tapping the composer yanks the chat to the bottom. Users resort to "share conversation → new tab" just to scroll old responses. **[Verified]** (github openai/codex #22864, community.openai.com keyboard/scroll threads)
- **Why it matters:** Concrete evidence for PRD 00/03's "incumbents under-invest in mobile-web" thesis — and it's specifically the **keyboard + scroll-anchor** problems this PRD targets. Worth citing as competitive proof.
- **Suggestion:** **MVP** — treat "composer never hidden by keyboard regardless of length" and "tapping composer does not yank scroll" as explicit acceptance tests (incumbents fail both).
- Sources: https://github.com/openai/codex/issues/22864 · https://www.cometapi.com/why-cant-i-scroll-down-on-chatgpt/

### 2.9 iOS 26.2 third-party browser engines (Japan first) — forward-looking
- **What:** Non-WebKit engines are slated to become available on iOS starting **iOS 26.2** (initially Japan), which would eventually unlock fuller web APIs (real Vibration API, etc.) on iOS. **[Verified]** (medium @posaune0423 2026)
- **Why it matters:** A long-horizon signal that the "iOS = WebKit-only" assumption underpinning the whole iOS-limits section may erode over the product's life. Don't bank on it, but note it.
- **Suggestion:** **P2/watch** — add to the "revalidate periodically" list.
- Source: https://medium.com/@posaune0423/i-open-sourced-an-oss-library-for-arbitrary-haptic-feedback-in-ios-safari-5b8ca74a5f05

---

## 3. Validated / challenged assumptions

| Existing claim (research/PRD) | 2026 status | Verdict |
|---|---|---|
| **`dvh` + `interactive-widget` fixes the mobile keyboard (composer [P0])** | iOS Safari keyboard resizes only the **visual** viewport → `dvh` does NOT shrink on iOS keyboard show; `interactive-widget` is Android/Chromium-only. iOS still needs `visualViewport` JS. | **CHALLENGED / partly wrong** — see §2.1, §4. **[Verified]** (bramus viewport-resize-behavior explainer; medium tharunbalaji "dvh does not account for virtual keyboards") |
| **iOS PWA storage ~50 MB cap** | Removed in **Safari 17**; now disk-proportional (≈tens of GB; ~60% of disk per browser-app origin). `navigator.storage.estimate()` reports tens of GB on iPhone. | **OUTDATED** — real constraint is **eviction**, not size. **[Verified]** (webkit.org "Updates to Storage Policy", docs.bswen.com 2026 browser-storage quotas) |
| **iOS 7-day cache eviction** | Still in effect (ITP eviction of non-persisted data after ~7 days of no interaction). `StorageManager.persist()` *can* exclude from eviction; WebKit grants it heuristically, **more likely for Home-Screen web apps**. | **CONFIRMED, with mitigation the docs miss** — request `navigator.storage.persist()`. **[Verified]** (webkit.org storage policy, magicbell 2026) |
| **EU iOS 17.4+ blocks PWAs/push** | Apple **reversed** the removal after DMA feedback; standalone PWA support reinstated in the EU. (One 2026 source still lists it as "unresolved/no timeline" — minor conflict.) | **LARGELY RESOLVED** — but **[Uncertain]** at the margin; revalidate. **[Verified]** (mobiloud 2026, magicbell 2026) |
| **Background Sync unavailable on iOS** | Still unavailable in 2026; no change. Replay on `online`/foreground remains the correct workaround. | **CONFIRMED** **[Verified]** (magicbell 2026, mobiloud 2026) |
| **No auto-install prompt on iOS → custom coachmark** | Still no `beforeinstallprompt` on iOS; coachmark still required. iOS 26 makes Home-Screen sites open as web apps by default (less friction *after* install). | **CONFIRMED** **[Verified]** (magicbell 2026, mobiloud 2026) |
| **Web Speech recognition broken in installed iOS PWA; "prefer on-device for privacy"** | Broken-in-PWA confirmed (works only in Safari tab). BUT on iOS/Chrome Web Speech is **server-based** — iOS sends audio to **Apple** for processing (permission modal "send audio to Apple"). It is **not** on-device. | "Broken in PWA" CONFIRMED; **"prefer on-device for privacy" is WRONG for iOS Safari** — a privacy red flag the docs miss. **[Verified]** (whatpwacando.today/speech-recognition, MDN Web Speech) |
| **Web Share Target weak/absent on iOS** | Still **not supported** on iOS Safari in 2026 (open WebKit bug, no ship). | **CONFIRMED** — correctly a Capacitor-era feature. **[Verified]** (magicbell 2026, bugs.webkit.org #194593) |
| **Capacitor is the pragmatic native path; WebView "typically sufficient" for chat** | Confirmed 2026. Capacitor 7 (Jan 2025), 8 in beta (late 2025). WebView scroll ~20–30 ms behind native but gap largely closed on modern devices; mid-range Android still shows it. Capacitor explicitly endorsed for AI apps (iteration speed). | **CONFIRMED** **[Verified]** (pkgpulse 2026, capgo.app "Capacitor for AI apps", edana.ch 2025) |
| **`dvh`/`svh`/`lvh` baseline support** | Baseline **Widely Available June 2025**; ~95% global support; iOS 15.4+. | **CONFIRMED** (but note keyboard caveat above). **[Verified]** (web.dev/blog/viewport-units, testmuai.com) |
| **CWV targets LCP ≤2.5 / INP ≤200 / CLS ≤0.1; ~48% pass** | Targets unchanged. INP now the **most-failed** vital (~43% fail). | **CONFIRMED + sharpened** **[Verified]** (digitalapplied 2026, dev.to CWV 2026) |
| **Vibration API for haptics ([P1])** | No `navigator.vibrate` on iOS at all; Android only. iOS needs the label-switch trick (iOS 18+). | **PARTLY WRONG** as written — see §2.4. **[Verified]** |

---

## 4. PRD 03 review — gaps, errors, outdated items, inconsistencies

Ordered roughly by severity. Section references are to `docs/prd/03-mobile-cross-platform.md`.

### 4.1 [CRITICAL — factual error] §4.3 makes `dvh` the [P0] keyboard mechanism; it fails on iOS
- **§4.3** states: *"app shell uses `dvh` … so the visible viewport adjusts when the keyboard shows — no JS resize observer as the primary mechanism"* and lists `interactive-widget=resizes-content` as **[P0]**.
- **Problem:** On **iOS/iPadOS Safari the keyboard resizes only the visual viewport**, so `dvh` does **not** shrink and a `position: fixed`/`sticky` bottom composer **gets covered by the keyboard** — the exact failure mode the PRD flags as its top composer risk (§4.3 last bullet, §9.2). `interactive-widget` does nothing on iOS (Android/Chromium-only). So the stated P0 mechanism is correct on Android and **non-functional on iOS**. **[Verified]** (bramus explainer: iOS uses `resizes-visual`; tharunbalaji: "dvh does not account for virtual keyboards")
- **Note on source conflict:** the PRD's cited source (franciscomoretti) claims `dvh` "works on iOS Safari" — but that article is about full-height *layout*, and it still says "if you also want Android/Chromium to resize content with the keyboard, set `interactive-widget`," tacitly conceding iOS is the visual-viewport case. The more authoritative W3C/explainer and MDN sources contradict the "dvh fixes the iOS keyboard" reading. **[Uncertain→resolved against the PRD]**
- **Fix:** Demote the §4.3 "no JS observer" claim. Make the **[P0]** mechanism explicitly two-track: (a) Android/Chromium = `dvh` + `interactive-widget=resizes-content`; (b) **iOS = `visualViewport` listener** that sets a CSS var / translates the composer (the well-documented "position via `top` + translate, listen to `visualViewport.resize/scroll`" pattern), with VirtualKeyboard API as progressive enhancement where available. The PRD currently relegates `visualViewport` to "edge-case fallback only" (§4.3) — on iOS it is the **primary** path. This single error undermines the headline composer goal.

### 4.2 [CRITICAL — outdated] "~50 MB" iOS storage cap is wrong and propagates into trigger logic
- Appears in **§4.6** ("~50 MB cap, 7-day eviction"), **§4.9** ("~50 MB storage cap"), **§5.3**, **§6.2 trigger #3** ("beyond iOS PWA's ~50 MB / 7-day limits"), **§6.4 table** ("~50 MB cap — server is source of truth"), and the success-metrics framing.
- **Problem:** Safari 17 removed small caps; quota is now disk-proportional (tens of GB). **[Verified]** Durable-offline-on-iOS is constrained by **eviction**, not capacity. This means:
  - Capacitor **trigger #3** ("need storage beyond ~50 MB") is **largely moot** — you have plenty of space; you'd go native for *eviction-proof persistence + background sync*, not for capacity.
  - You **can** cache far more conversation history offline on iOS than the PRD assumes — a missed product opportunity for the offline experience.
- **Fix:** Replace "~50 MB cap" everywhere with "disk-proportional quota (tens of GB) but **subject to 7-day ITP eviction unless `navigator.storage.persist()` is granted**." Add a **[P0]** requirement to call `navigator.storage.persist()` (more likely granted for installed PWAs) and to read `navigator.storage.estimate()` for budgeting. Rewrite trigger #3 around **eviction/background-sync**, not size.

### 4.3 [HIGH — missing] "prefer on-device for privacy" voice claim is wrong on iOS; privacy disclosure gap
- **§4.7 [P1]** says Web Speech voice should "prefer on-device for privacy."
- **Problem:** On **iOS Safari, Web Speech recognition is server-side — audio is sent to Apple** (explicit permission modal). On Chrome it is also typically server-based. There is no on-device guarantee. For a **privacy-first** product (PRD 00 §7), shipping a "voice" feature that silently ships user audio to Apple/Google without disclosure is an own-goal. **[Verified]** (whatpwacando.today/speech-recognition)
- **Fix:** Correct the claim; add a **[P0]-for-the-feature** privacy disclosure ("dictation sends audio to your browser vendor"), and note that the privacy-first answer is a **self-hosted/BYOK STT** path (the PRD already mentions server-side STT as **[P1]** in §4.7 — elevate it as the *privacy-aligned* option, not a mere fallback).

### 4.4 [HIGH — inconsistency] Pull-to-refresh contradicts streaming/interrupted-stream goals
- **§4.4 [P1]** proposes pull-to-refresh "(optional given streaming; low priority)."
- **Problem:** On mobile web, native pull-to-refresh **reloads the page**, which would kill an in-flight stream and the optimistic/queue state the PRD works hard to preserve (§4.6, user story #4). A real AI-chat app (LibreChat) filed a bug to *disable* it for this reason. **[Verified]**
- **Fix:** **Remove** pull-to-refresh from the conversation surface; add **[P0] `overscroll-behavior: contain`** on the message list + app root (anti scroll-chaining AND blocks accidental reload). If pull-to-refresh is wanted at all, scope it to the **history drawer** only.

### 4.5 [MEDIUM] Render-coalescing / INP technique is under-prioritized
- **§4.10**: "Streaming render coalescing (rAF batch)" is **[P1]**; there is **no mention** of `scheduler.yield()` or main-thread yielding.
- **Problem:** INP ≤200 ms (a **[P0]** budget in §4.10/§8) is the **hardest and most-failed** vital in 2026, and streaming chat is a long-task factory. Putting the main mitigation at P1 with no `scheduler.yield()` is inconsistent with making the budget P0. **[Verified]**
- **Fix:** Promote token-batching to **[P0]** and add `scheduler.yield()` (with `setTimeout(0)` fallback) as a named technique for expensive interaction handlers (send, model switch, markdown re-parse).

### 4.6 [MEDIUM] No JS bundle / performance budget numbers
- **§4.10 / §8** set CWV field targets but **no bundle-size or main-thread budget**.
- **Problem:** LCP/INP on mid-tier phones are dominated by JS parse/exec (~50–80 ms CPU per 100 KB compressed on a mid-range phone). Without a KB budget the CWV targets aren't actionable. **[Verified]** (calibreapp, dev.to bundle 2026)
- **Fix:** Add a **[P0]** budget, e.g. **initial route JS ≤ ~200 KB compressed**, route/panel code-split (artifact/canvas, markdown+highlighter, mermaid/KaTeX lazy — the PRD lists the right *targets* in §4.10 but no number), and a CI bundle-size check. Note KaTeX/mermaid/highlighter (P0 per PRD 00) are heavy — must be lazy-loaded.

### 4.7 [MEDIUM] Capacitor trigger logic needs updating for 2026 facts
- **§6.2 triggers**: #1 iOS push, #3 storage "beyond ~50 MB."
- **Problems:** (a) #3 is based on the wrong storage number (§4.2 above). (b) #1's pessimism is partially softened by **Declarative Web Push + iOS 26 default-web-app + EU reversal** (§2.7, §3) — iOS *installed* push is now more reliable to implement, though opt-in is still install-gated. The PRD's "~16% opt-in (single-source figure)" hedge is good and should stay.
- **Fix:** Rewrite trigger #3 around **eviction-proof durable storage + background sync** (genuine iOS PWA gaps) rather than capacity. Add a note that Declarative Web Push narrows the *implementation* gap for #1 (the *opt-in/install* gap remains). Keep RN-rejected and Capacitor-pragmatic conclusions — both **[Verified]** still correct.

### 4.8 [MEDIUM] Container-query "OR breakpoint-hook" left unresolved; safe-area is more than bottom
- **§4.1 / §5.3** leave "container queries OR a breakpoint hook" undecided.
- **Fix:** Container size queries are Baseline-safe (§2.3) — resolve to: **viewport breakpoints/hook for the shell; container queries for reusable panes**.
- **§4.3 safe-area:** only `safe-area-inset-bottom` is specified. Landscape iPhones and notch/Dynamic-Island devices also need **`-left`/`-right`/`-top`** insets for the composer/header, and the manifest/meta needs **`viewport-fit=cover`** for `env(safe-area-inset-*)` to apply at all. The PRD doesn't mention `viewport-fit=cover` — without it the insets are always 0. **[Verified/Recall]** Add as **[P0]**.

### 4.9 [LOW–MEDIUM] Missing/under-specified items
- **`100svh` first-paint white strip:** on iOS Safari the bottom bar only collapses after scroll, so a full-height surface sized to `lvh` shows a white strip until first scroll. Spec should note **`dvh` for app shell (not `lvh`)** to avoid this. **[Verified]** (testmuai, web.dev viewport-units). PRD §5.3 says "use dvh/svh/lvh" generically — clarify *which* for the full-height shell.
- **`Screen Wake Lock` during long streams:** new since Safari 18.4 for home-screen web apps — prevents the screen dimming mid-answer. Not in PRD. Add **[P1]**. **[Verified]**
- **Virtualizer choice:** §4.5 lists Virtuoso/TanStack; add **Virtua** and **`VirtuosoMessageList`** to the spike (§2.1). The "TanStack Virtual as alternative" framing is questionable given TanStack's own maintainers flag it as hard for chat. **[Verified]**
- **`content-visibility: auto`** for off-screen message bubbles as a cheaper complement/alternative to full virtualization on shorter threads — not mentioned. **[Recall]**
- **IME/composition events:** mobile "Enter = newline" (§4.3) interacts with IME composition (CJK, autocorrect) — send must not fire mid-composition (`isComposing`). Not specified; relevant for the i18n posture in PRD 00. **[Recall]**
- **`navigator.storage.persist()`** to fight 7-day eviction — not mentioned anywhere (see §4.2). **[Verified]**
- **Haptics on iOS** via label-switch trick (§2.4) — §4.4 assumes the Vibration API and gets nothing on iOS. **[Verified]**
- **`autocapitalize`/`autocorrect`/`enterkeyhint="send"`/`inputmode`** on the composer textarea — standard mobile polish, unspecified. Setting `enterkeyhint` is the clean way to label the keyboard's return key. **[Recall]**

### 4.10 [LOW] Minor source/consistency notes
- The PRD inherits the research doc's "~16% web-push opt-in" as a single-source figure — it already flags this well (§6.2). Keep, but treat as illustrative.
- §8 success metrics are good; add a **field INP processing-time** breakdown (input delay vs processing vs presentation) given INP is the risk metric. **[Verified]** (corewebvitals.io INP processing-time)
- §9 open questions are well-chosen; **add** "iOS keyboard mechanism = `visualViewport`, not `dvh`" as a resolved decision (currently mis-framed as a `dvh` risk only).

---

## 5. Top 5 recommendations (prioritized, actionable)

1. **Fix the iOS keyboard mechanism (P0, blocking).** Re-spec §4.3: Android = `dvh` + `interactive-widget=resizes-content`; **iOS = `visualViewport`-driven composer positioning** (primary, not fallback) + `viewport-fit=cover` + all four safe-area insets, VirtualKeyboard API as progressive enhancement. This is the product's stated #1 risk and the current spec is wrong for iOS. **[Verified]**
2. **Correct the storage model everywhere (P0).** Replace "~50 MB cap" with "disk-proportional quota + 7-day eviction unless `navigator.storage.persist()` is granted." Add P0 `storage.persist()` + `storage.estimate()` budgeting. Rewrite Capacitor trigger #3 around **eviction/background-sync**, not capacity — and lean into caching *more* history offline on iOS than previously assumed. **[Verified]**
3. **Make INP a first-class engineering requirement (P0), not a P1.** Token-batching per rAF + `scheduler.yield()` for expensive handlers, plus a **≤~200 KB compressed initial-JS budget** with CI enforcement and lazy-loaded KaTeX/mermaid/highlighter. INP is the most-failed 2026 vital and streaming chat is its worst case. **[Verified]**
4. **De-risk the virtualization spike with current options (P0 spike).** Compare **Virtua** (free, reverse-scroll built-in) and **`VirtuosoMessageList`** (purpose-built for AI streaming, commercial) against TanStack; default away from TanStack for the chat list. Pair with `overscroll-behavior: contain` and **drop pull-to-refresh** on the conversation. **[Verified]**
5. **Fix the voice privacy story (P1, but P0 for the feature).** Correct "prefer on-device" — iOS/Chrome Web Speech is **server-side (audio → vendor)**. Disclose it in-UI; position **self-hosted/BYOK STT as the privacy-aligned path**, consistent with the product's privacy-first wedge. Also: add Declarative Web Push + Screen Wake Lock + iOS haptics (label-switch) as concrete polish wins. **[Verified]**

---

## 6. Sources (this pass)

**Viewport / keyboard / dvh**
- bramus, viewport-resize-behavior explainer (interactive-widget values; iOS = resizes-visual) — https://github.com/bramus/viewport-resize-behavior/blob/main/explainer.md
- web.dev, large/small/dynamic viewport units — https://web.dev/blog/viewport-units
- Tharunbalaji, svh/lvh/dvh guide ("dvh does not account for virtual keyboards") — https://medium.com/@tharunbalaji110/understanding-mobile-viewport-units-a-complete-guide-to-svh-lvh-and-dvh-0c905d96e21a
- TestMu (LambdaTest), viewport unit browser support — https://www.testmuai.com/learning-hub/viewport-unit-variants-browser-support/
- Francisco Moretti, fix keyboard overlap with dvh — https://www.franciscomoretti.com/blog/fix-mobile-keyboard-overlap-with-visualviewport
- saricden, fixed elements respect iOS virtual keyboard (visualViewport) — https://saricden.com/how-to-make-fixed-elements-respect-the-virtual-keyboard-on-ios

**Storage / offline / sync**
- WebKit, Updates to Storage Policy (Safari 17 quota) — https://webkit.org/blog/14403/updates-to-storage-policy/
- BSWEN, browser storage quotas & eviction (2026) — https://docs.bswen.com/blog/2026-04-07-browser-storage-quotas-eviction/
- MDN, Storage quotas and eviction criteria — https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- Dexie (Cloud sync) — https://dexie.org/
- Best offline-first tech stack 2026 — https://cssauthor.com/offline-first-tech-stack/
- RxDB, local-first future — https://rxdb.info/articles/local-first-future.html
- Advanced syncing algorithms 2026 — https://dev.to/devin-rosario/advanced-syncing-algorithms-for-collaborative-mobile-apps-in-2026-1a60

**PWA / iOS / push / Capacitor**
- MagicBell, PWA iOS limitations [2026] — https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide
- MobiLoud, Do PWAs work on iOS [2026] — https://www.mobiloud.com/blog/progressive-web-apps-ios
- WebKit, Safari 18.4 features (Declarative Web Push, Screen Wake Lock) — https://webkit.org/blog/16574/webkit-features-in-safari-18-4/
- Aimtell, State of Declarative Web Push 2026 — https://aimtell.com/blog/state-of-declarative-web-push-2026
- PkgPulse, RN vs Expo vs Capacitor 2026 — https://www.pkgpulse.com/guides/react-native-vs-expo-vs-capacitor-cross-platform-mobile-2026
- Capgo, Capacitor for AI apps — https://capgo.app/blog/capacitor-ai-mobile-apps/
- Edana, should you choose Capacitor (2025) — https://edana.ch/en/2025/07/31/should-you-still-choose-capacitor-today-for-which-types-of-mobile-projects-does-it-remain-relevant/
- WebKit bug, Web Share Target API — https://bugs.webkit.org/show_bug.cgi?id=194593

**Performance / INP / bundle**
- Core Web Vitals in 2026 (practical fixes) — https://dev.to/benriemer/core-web-vitals-in-2026-the-practical-fixes-for-inp-lcp-and-cls-that-actually-work-4ef0
- NitroPack, scheduler.yield() — https://nitropack.io/blog/post/introducing-scheduler-yield
- web.dev, optimize long tasks — https://web.dev/articles/optimize-long-tasks
- Core Web Vitals 2026 (INP/LCP/CLS) — https://www.digitalapplied.com/blog/core-web-vitals-2026-inp-lcp-cls-optimization-guide
- Calibre, bundle size optimization — https://calibreapp.com/blog/bundle-size-optimization
- corewebvitals.io, INP processing time — https://www.corewebvitals.io/core-web-vitals/interaction-to-next-paint/processing-time

**Virtualization / scroll**
- React Virtuoso (VirtuosoMessageList) — https://virtuoso.dev/ · https://github.com/petyosi/react-virtuoso
- Virtua — https://bestofjs.org/projects/virtua
- TanStack Virtual chat discussions — https://github.com/TanStack/virtual/discussions/477 · https://github.com/TanStack/virtual/discussions/195
- MDN, overscroll-behavior — https://developer.mozilla.org/en-US/docs/Web/CSS/overscroll-behavior
- Chrome, take control of your scroll (overscroll-behavior) — https://developer.chrome.com/blog/overscroll-behavior
- LibreChat issue, disable pull-to-refresh — https://github.com/danny-avila/LibreChat/issues/8746

**Container queries**
- LogRocket, container queries in 2026 — https://blog.logrocket.com/container-queries-2026/
- MDN, container queries — https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Containment/Container_queries

**Voice / haptics / competitive**
- whatpwacando.today, speech recognition (server-side, broken in iOS PWA) — https://whatpwacando.today/speech-recognition/
- MDN, Web Speech API — https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- caniuse, Vibration API — https://caniuse.com/vibration
- Ionic Framework, haptic feedback on iOS toggle (label-switch) — https://github.com/ionic-team/ionic-framework/issues/29942
- asuma (medium), arbitrary haptics in iOS Safari (2026; iOS 26.2 engines note) — https://medium.com/@posaune0423/i-open-sourced-an-oss-library-for-arbitrary-haptic-feedback-in-ios-safari-5b8ca74a5f05
- OpenAI Codex issue, skill picker hidden by keyboard (iOS) — https://github.com/openai/codex/issues/22864
- CometAPI, why can't I scroll on ChatGPT — https://www.cometapi.com/why-cant-i-scroll-down-on-chatgpt/
