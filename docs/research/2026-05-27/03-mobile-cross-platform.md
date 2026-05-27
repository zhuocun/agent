# Research & PRD Review — 03 Mobile & Cross-Platform

**Date:** 2026-05-27
**Researcher:** Mobile & Cross-Platform
**Scope:** (A) fresh online research pass (current as of May 2026) + (B) critical review of PRD 03.
**Method:** Live web search/fetch May 2026; verified platform claims against primary docs (MDN, WebKit, Chrome for Developers) and recent secondary sources. PRD 03 read in full; PRD 00 skimmed for framing.

---

## 1. Summary

- **PRD 03 is in unusually good shape and mostly current.** Its three big "corrected/verified" calls — iOS storage is disk-proportional not ~50 MB, iOS keyboard fix must be `visualViewport` (not `dvh`/`interactive-widget`), and Web Speech is server-side not on-device — all hold up against May-2026 sources. The dropped pull-to-refresh decision is correct.
- **Two concrete things have gone stale and need editing.** (1) The **iOS haptics shim** (`<input type="checkbox switch">` + label `.click()`) recommended in §4.4 **appears to have been patched out in recent iOS** — community reports (an `ios-haptics` repo + an MDN browser-compat issue) say it no longer fires programmatically; no primary Apple release note pins this to a version (community threads cite "iOS 26.5"), so treat web haptics on iOS as **unreliable** rather than a confirmed kill. (2) The **TanStack Virtual "weak for chat"** claim in §4.5/§9 looks outdated per a **single, two-days-old (May 25, 2026)** TanStack post introducing `anchorTo: 'end'` + `followOnAppend`; treat TanStack as a co-equal spike candidate and let the spike — not one fresh post — decide.
- **The EU iOS PWA "[Uncertain]" tag is over-cautious and should be resolved.** Apple's removal was reversed in **March 2024** and standalone Home-Screen web apps (with push) have shipped in the EU since. The lingering "one 2026 source still lists it unresolved" is a stale secondary source, not a live risk. Recommend downgrading from `[Uncertain]` to "resolved; standalone PWA + push available in EU."
- **iOS web-push reachability is the load-bearing constraint, and the PRD frames it correctly.** Web push remains install-gated (iOS 16.4+, Home-Screen only, not Safari tabs). Web-push opt-in benchmarks (~10–15% well-placed, ~5–8% steady-state) confirm the Capacitor trigger #1 logic; the PRD's "~16% iOS" figure is plausible and conservatively flagged single-source.
- **Performance posture is correct and well-targeted.** INP is still the most-failed vital (~43% of sites fail; ~48% of mobile sites pass all three CWV — both PRD figures verified). rAF token-batching + `scheduler.yield()` is exactly how production chat (incl. ChatGPT) streams smoothly; promoting rAF-coalescing to P0 is right.
- **A latent strategic tension worth surfacing:** the PRD says "server is source of truth" (§4.6) while 2026 offline-first best practice and the product's own "local is real / privacy-first" story (§4.6 build-vs-buy note) point toward local-first-with-sync. This is a defensible MVP choice but should be an explicit decision, not an unstated default — flagged for PRD 04.
- **dvh/svh/lvh are now Baseline Widely Available (June 2025)** and `interactive-widget` is supported in **Chrome 108+ and Firefox 132+** (not strictly "Android/Chromium-only" — minor wording fix). Screen Wake Lock and Declarative Web Push (Safari 18.4) are confirmed; Web Share Target remains unimplemented on iOS (PRD correct).
- **Net:** no architectural rework needed. The deliverable is a short list of targeted edits (haptics, TanStack, EU tag) plus a couple of clarifications and one strategic flag.

---

## 2. New ideas & developments (online research)

### Theme A — iOS keyboard / viewport realities (validates the PRD's core mechanism)

- **The Virtual Keyboard API is still entirely absent from Safari/WebKit in May 2026** — no `navigator.virtualKeyboard`, no `geometrychange`, no `env(keyboard-inset-*)`. `visualViewport` (since 2019) remains the *only* API that accounts for the on-screen keyboard on iOS. (zouhir.org "The Virtual Keyboard API Is Broken Where It Matters Most"; ishadeed.com; MDN VirtualKeyboard API — accessed 2026-05-27)
  - **Implication for us:** PRD 03 §4.3's decision to make `visualViewport` JS the **primary** iOS path (not a fallback) is correct and still current. The §4.10 note that viewport units do not track the iOS keyboard is also correct. No change needed; this is the strongest part of the PRD.
- **dvh/svh/lvh reached Baseline Widely Available in June 2025** (Chrome/Edge 108+, Firefox 101+, Safari 15.4+). `dvh` tracks the live viewport (small↔large) with a mid-scroll shift; `svh` is stable. (DEV "CSS *vh units"; LambdaTest/TestMu "Viewport Unit Variants"; thelinuxcode 2026 guide — accessed 2026-05-27)
  - **Implication:** §5.3's "prefer `dvh` for the app shell, `svh`/`lvh` as needed" guidance is sound and the units are now safe to use without fallbacks beyond a `100vh` legacy floor.
- **`interactive-widget=resizes-content` is supported in Chrome 108+ AND Firefox 132+** (not iOS). Chrome is also rolling out viewport-resize-behavior changes on Android. (Chrome for Developers "Prepare for viewport resize behavior changes"; MDN viewport meta; HTMHell — accessed 2026-05-27)
  - **Implication:** Minor wording correction to §4.3/§5.1 — it's "Chromium + Firefox," not "Android/Chromium-only." Behavior on iOS is unchanged (still no-op), so the two-track logic stands.

### Theme B — iOS PWA platform state (push, storage, wake lock, share)

- **Web push on iOS is unchanged: install-gated (16.4+, Home-Screen only), not from Safari tabs.** Declarative Web Push (Safari 18.4, Mar 2025) simplifies the installed path (no service worker required). iOS 26 opens Home-Screen sites as web apps by default, lowering post-install friction. (magicbell.com PWA-iOS-2026; mobiloud.com PWA-iOS-2026; webscraft.org "PWA Push on iOS in 2026" — accessed 2026-05-27)
  - **Implication:** §4.9/§6.4 are accurate. The opt-in/install-gated gap (the real driver of Capacitor trigger #1) persists; Declarative Web Push narrows only the *implementation* gap, exactly as the PRD already says.
- **iOS storage: confirmed disk-proportional via `StorageManager.estimate()` (Safari 17+); the constraint is 7-day eviction of non-persisted data, with Home-Screen web apps having their OWN use-counter (first-party data not deleted on the Safari 7-day rule).** `navigator.storage.persist()` is granted heuristically, more likely for installed web apps. (WebKit "Updates to Storage Policy"; MDN "Storage quotas and eviction"; Apple Developer Forums thread 710157 — accessed 2026-05-27)
  - **Implication:** §4.6/§6.4 storage corrections are verified. **Nuance to add:** for an *installed* iOS web app, first-party script-written data is not subject to the Safari 7-day deletion at all — so an installed PWA's durability is meaningfully better than the PRD's "7-day eviction" framing implies. This strengthens the case that capacity is not the issue and softens (without removing) the durable-offline Capacitor trigger.
- **Screen Wake Lock now fully works in installed iOS PWAs (the long-standing PWA bug was fixed in iOS 18.4).** (progressier.com Screen-Wake-Lock; whatpwacando.today; magicbell.com — accessed 2026-05-27)
  - **Implication:** §4.9 Wake Lock item is safe to keep at P1 and now works in the installed-PWA case, not just Safari tabs.
- **Web Share Target remains unimplemented on iOS Safari (open WebKit bug 194593).** (MDN share_target; bugs.webkit.org 194593; progressier.com Web Share — accessed 2026-05-27)
  - **Implication:** §4.7/§9.4 are correct — share-to-AI on mobile web is a Capacitor-era capability. Open question #4 can be marked verified/closed.

### Theme C — Message-list virtualization for streaming chat (a real shift)

- **TanStack Virtual now has first-class, recommended chat support.** A **May 25, 2026** TanStack blog post ("Chat UIs Are Lists Until They Aren't") introduces `anchorTo: 'end'` (bottom-anchoring, stable prepend of history) and `followOnAppend` (stick-to-bottom unless the user scrolled up), including streaming size-delta handling, and states chat "should feel boring to build." (tanstack.com/blog/tanstack-virtual-chat — accessed 2026-05-27)
  - **Implication:** This directly contradicts PRD §4.5 and §9, which say "TanStack Virtual — explicitly weak for bidirectional/chat per its own maintainers; treat as fallback." That claim is now **stale**. TanStack should be a co-equal spike candidate, not a relegated fallback. It is free, headless, and very widely used.
- **React Virtuoso (`VirtuosoMessageList`) remains purpose-built for human/AI streaming chat** (imperative scroll-on-arrival API, stick-to-bottom) and is commercially licensed for the message-list component. **Virtua (~3 kB)** remains a free zero-config option with built-in reverse scrolling. (github.com/petyosi/react-virtuoso; virtuoso.dev; bestofjs Virtua; getstream.io VirtualizedMessageList — accessed 2026-05-27)
  - **Implication:** The spike now has **three** strong, chat-capable candidates (Virtua, VirtuosoMessageList, TanStack Virtual). Decision axes: license cost (Virtuoso), bundle size (Virtua wins), and control/ecosystem (TanStack). Recommend evaluating all three against the §4.3/§4.5 acceptance tests.
- **CSS scroll anchoring (`overflow-anchor`) and `overscroll-behavior` are stable and well-documented** for preventing scroll jump during DOM mutation and blocking pull-to-refresh/scroll-chaining. (MDN scroll anchoring; MDN overscroll-behavior — accessed 2026-05-27)
  - **Implication:** §4.4's `overscroll-behavior: contain` decision is sound. Consider explicitly pairing `overflow-anchor` behavior with the virtualization choice in the spike (some virtualizers manage anchoring themselves and may need `overflow-anchor: none`).

### Theme D — Performance / INP for streaming (validates the PRD)

- **INP is still the most-failed Core Web Vital in 2026 (~43% of sites fail the 200ms p75 threshold; some report ~47%). ~48% of mobile sites pass all three CWV.** `scheduler.yield()` is the named technique for breaking >50ms long tasks; >50ms = a "long task." (web.dev "Optimize long tasks"; nitropack.io scheduler.yield; corewebvitals.io; digitalapplied.com CWV-2026; linkgraph.com INP-2026 — accessed 2026-05-27)
  - **Implication:** §4.10's INP framing and the ~43% / ~48% figures are **verified accurate**. Keeping rAF-coalescing and `scheduler.yield()` at P0 is correct.
- **Production chat streams smoothly by buffering tokens in a `useRef` array and flushing once per `requestAnimationFrame`, never re-rendering per token** — explicitly cited as how ChatGPT-class apps stream in React. `startTransition`/`useTransition` mark token updates non-urgent to protect input responsiveness. (akashbuilds.com "Why React Apps Lag With Streaming Text"; sitepoint.com "Streaming Backends & React"; debugbear.com rAF — accessed 2026-05-27)
  - **Implication:** §4.10's "batch token updates per animation frame" is exactly the production pattern. Worth adding `startTransition` for token-state updates as a complementary technique in the implementation notes (not a new requirement).

### Theme E — Capacitor vs RN vs PWA (2026 state — validates the decision, with one caveat)

- **2026 consensus: modern WebViews are "excellent," and "if your web app already performs well in a mobile browser, it will perform similarly inside Capacitor."** Capacitor reuses the web codebase; RN renders native views but requires a UI rewrite. (nextnative.dev Capacitor-vs-RN; pkgpulse.com 2026; kanopylabs.com 2026; reveation.io — accessed 2026-05-27)
  - **Implication:** §6.3's rejection of React Native (full rewrite, no chat-perf win) is well-supported in 2026.
- **Caveat (new, relevant):** multiple 2026 comparisons name Capacitor's weak spots as **"complex list virtualization, heavy real-time data rendering, and gesture-intensive interactions"** — and a streaming, virtualized chat list is precisely that. The WebView scroll path can lag native by ~20–30ms on mid-range Android. (nextnative.dev; capgo.app "Comparing RN vs Capacitor" — accessed 2026-05-27)
  - **Implication:** This doesn't change the PWA-first/Capacitor-later decision, but it means the §9 virtualization spike should **also validate the chosen virtualizer inside a Capacitor WebView on a mid-tier Android device**, not just in mobile Safari/Chrome. Add to the spike scope so we don't discover a regression at the Capacitor trigger.

### Theme F — Voice / camera / mobile input

- **Web Speech recognition on iOS is server-side (Safari prompts before routing audio to Apple), is throttled/unreliable, and does NOT work in an installed iOS PWA (works in Safari tab only).** (MDN Web Speech API; xjavascript.com iOS speech; WebKit Documentation issue 120 — accessed 2026-05-27)
  - **Implication:** §4.7's privacy correction (disclose "dictation sends audio to your browser vendor"; not on-device; broken in installed PWA; self-hosted/BYOK STT as the privacy-aligned path) is **fully verified** and well-judged for a privacy-first product.

### Theme G — Mobile AI chat UX patterns (incumbents)

- Incumbents' on-device chat polish (Claude's tappable clarifying-question chips, ChatGPT's mid-stream re-prompt) is improving, but granular mobile-web composer/keyboard/send-stop implementation detail is not well-documented in public sources — the competitive-teardown open question (§9 #7) genuinely requires hands-on device testing rather than desk research. (clickforest.com 2026 comparisons; aimagicx.com Apr-2026 head-to-head — accessed 2026-05-27)
  - **Implication:** Keep §9 #7 open; it's an empirical lab task, not closeable by research. The PRD's framing that incumbents under-invest in mobile-web (documented composer-covered-by-keyboard and scroll-yank failures) remains a credible wedge.

---

## 3. PRD review findings

> Tagged `[error]` (factually wrong now) · `[gap]` (missing) · `[inconsistency]` · `[scope]` (over/under-scoped) · `[risk]` (call-out).

1. **[error] §4.4 Haptics — the iOS shim appears no longer reliable.** The PRD recommends "`<input type="checkbox switch">` + label-`click()` shim (iOS 18+)" for iOS haptics. **The programmatic label-`.click()` haptic trigger appears to have been patched out in recent iOS** — community reports indicate haptics now fire only on a *direct user* toggle, not programmatically. Confidence is medium: the sources are community-level (`ios-haptics` repo + MDN browser-compat issue 29166), not a primary Apple release note, and the specific "iOS 26.5" version is community-cited rather than documented. (github.com/tijnjh/ios-haptics; mdn browser-compat-data issue 29166 — accessed 2026-05-27)
   - **Action:** Replace the iOS-haptics recommendation. On iOS, treat web haptics as **not reliably available** and degrade silently (visual feedback only). Keep the Android Vibration API path. Note `navigator.vibrate` has inconsistent/limited iOS support and should be feature-detected. Since §4.4 haptics is already P1 and degrade-silently, this is a low-cost wording fix, not a scope change.

2. **[error] §4.5 + §9 #1 — TanStack Virtual may no longer be "weak for chat."** PRD states TanStack is "explicitly weak for bidirectional/chat per its own maintainers; treat as fallback, not the default." A **single, two-days-old (May 25, 2026)** TanStack post — not yet corroborated elsewhere — says the library now ships `anchorTo: 'end'` + `followOnAppend` with streaming size-delta handling and recommends it for chat. The action below is low-risk regardless of how that single source ages, since it only adds a spike candidate. (tanstack.com/blog/tanstack-virtual-chat — accessed 2026-05-27)
   - **Action:** Remove the "weak for chat / fallback" framing. List **three** co-equal spike candidates — Virtua (free, ~3 kB), `VirtuosoMessageList` (purpose-built, commercial), TanStack Virtual (free, headless, now chat-capable) — and decide on the acceptance tests, not on a stale maintainer quote.

3. **[inconsistency] §4.9 / §6.4 / §9 #5 — the EU iOS PWA "[Uncertain]" tag is stale and self-contradictory.** Apple reversed the EU Home-Screen-web-app removal in **March 2024**; standalone PWAs with push have shipped in the EU since. The PRD hedges this in three places citing "one 2026 source still lists it unresolved." That secondary source is wrong/stale. (theregister.com 2024-03-02; 9to5mac.com 2024-03-01; Apple Developer DMA support page — accessed 2026-05-27)
   - **Action:** Resolve the `[Uncertain]` tag to "resolved — standalone EU PWA + push reinstated since iOS 17.4 (Mar 2024)." Close open question §9 #5. (Note: a few secondary blogs still parrot the original removal; treat those as outdated, not as live conflict.)

4. **[gap] §4.6 / §6.4 — understates installed-iOS-PWA storage durability.** The PRD frames iOS durability as "7-day ITP eviction unless `storage.persist()`." Per WebKit, **Home-Screen web apps are not part of Safari and have their own use-counter; first-party script-written data is not subject to the Safari 7-day deletion.** (webkit.org "Updates to Storage Policy"; Apple Developer Forums 710157 — accessed 2026-05-27)
   - **Action:** Add a sentence clarifying that *installed* iOS web apps already get materially better data durability than the 7-day rule suggests; the 7-day rule bites hardest for *uninstalled Safari-tab* usage. This further weakens "durable offline" as a Capacitor trigger (trigger #3) — keep the trigger, but scope it to "guaranteed durability + true background replay," which the PRD already does.

5. **[error/minor] §4.3 / §5.1 — `interactive-widget` is "Chromium + Firefox," not "Android/Chromium-only."** Supported in Chrome 108+ and **Firefox 132+**. (Chrome for Developers viewport-resize-behavior; MDN viewport meta — accessed 2026-05-27)
   - **Action:** One-word fix. Doesn't affect the two-track logic (iOS is still a no-op, so `visualViewport` stays primary on iOS).

6. **[risk/gap] §6.3 + §9 #1 — virtualization must be validated inside a Capacitor WebView, not just mobile browsers.** 2026 Capacitor comparisons specifically name "complex list virtualization / heavy real-time rendering" as the WebView's weak spot — exactly our streaming chat list. (nextnative.dev; capgo.app — accessed 2026-05-27)
   - **Action:** Extend the §9 virtualization spike acceptance to include a mid-tier Android **Capacitor WebView** run, so the eventual native wrapper doesn't surface a scroll/streaming regression. Cheap to add now (the spike is already P0), expensive to discover later.

7. **[inconsistency/risk] §4.6 "Server is source of truth" vs the product's "local is real" privacy story.** 2026 offline-first best practice and the PRD's own §4.6 build-vs-buy note (Dexie Cloud/PowerSync/ElectricSQL/RxDB/Yjs) lean local-first-with-sync, where the local DB is the source of truth even when online. The PRD asserts the opposite default. (blog.logrocket.com offline-first-2025; cssauthor.com offline-first-2026; dexie.org — accessed 2026-05-27)
   - **Action:** This is a legitimate MVP simplification (server-authoritative is simpler and safer for billing/transparency correctness), **but it should be an explicit, owned decision in PRD 04, not an unstated default**, because it interacts with the privacy-first "your data is local" positioning. Flag to PRD 04; no change required in PRD 03 beyond a cross-reference note.

8. **[scope — OK, affirming] P0/P1 split is appropriately lean.** Text-only composer P0 (camera/attach P1), haptics/voice/wake-lock/web-push all P1, virtualization + optimistic send + INP budget P0. This matches the lean mobile-web-first MVP mandate. No over/under-scoping found. The dropped pull-to-refresh (§4.4) is the correct call and well-justified.

9. **[gap — minor] §4.10 — add `startTransition` to the streaming-render note.** The verified production pattern pairs rAF token-batching with React `startTransition`/`useTransition` to mark token updates non-urgent. (akashbuilds.com; sitepoint.com — accessed 2026-05-27)
   - **Action:** Add as an implementation note under §4.10 streaming coalescing (not a new requirement).

10. **[gap — minor] §4.9 web-push opt-in numbers.** The "~16% iOS" figure is plausible but single-source. Web-push (not native-app push) benchmarks: ~10–15% with well-placed prompts, ~5–8% steady-state. Native-app push opt-in is far higher (iOS ~54% in 2026 Airship data), which is part of why Capacitor trigger #1 exists. (batch.com 2025 benchmark; airship.com 2026; mobiloud push stats — accessed 2026-05-27)
    - **Action:** Keep the figure flagged single-source (PRD already does) but add the web-vs-native push opt-in gap as the *quantified* rationale for trigger #1.

**Verified-correct PRD claims (no action — listed so the review is auditable):** iOS keyboard = `visualViewport` primary (§4.3); viewport units don't track iOS keyboard (§4.10); iOS storage disk-proportional not ~50 MB (§4.6/§6.4); Web Speech server-side + broken in installed iOS PWA (§4.7); Web Share Target absent on iOS (§4.7/§9.4); Screen Wake Lock + Declarative Web Push since Safari 18.4 (§4.9); no background sync on iOS (§4.6/§6.4); INP most-failed vital ~43% / ~48% mobile pass (§4.10/§8); `viewport-fit=cover` required for non-zero safe-area insets (§4.3); RN rejection rationale (§6.3); App Store Guideline 4.2/5.1.2 obligations (§6.2).

---

## 4. Recommendations (prioritized)

### P0 — fix before this PRD is treated as build-ready
- **R1.** Rewrite §4.4 iOS haptics: the label-`.click()` shim is patched out in iOS 26.5 — drop it; iOS = no reliable web haptics, degrade silently; keep Android Vibration API. (Finding 1)
- **R2.** Rewrite §4.5/§9 #1 TanStack framing: three co-equal chat-capable virtualizer candidates (Virtua / VirtuosoMessageList / TanStack Virtual); decide on acceptance tests. (Finding 2)
- **R3.** Resolve the EU iOS PWA `[Uncertain]` tag (§4.9/§6.4/§9 #5) to "reinstated since Mar 2024"; close open question #5. (Finding 3)
- **R4.** Extend the §9 virtualization spike to include a Capacitor-WebView run on mid-tier Android. (Finding 6)

### P1 — clarifications that improve correctness
- **R5.** Add the installed-iOS-PWA storage-durability nuance to §4.6/§6.4 (own use-counter; first-party data survives the Safari 7-day rule). (Finding 4)
- **R6.** Fix §4.3/§5.1 wording: `interactive-widget` = Chromium 108+ **and** Firefox 132+. (Finding 5)
- **R7.** Add `startTransition` to the §4.10 streaming-coalescing implementation note. (Finding 9)
- **R8.** Quantify Capacitor trigger #1 with the web-vs-native push opt-in gap. (Finding 10)

### P2 — strategic / cross-PRD
- **R9.** Flag the "server source of truth" vs "local-first" decision to PRD 04 as an explicit, owned decision tied to the privacy positioning. (Finding 7)
- **R10.** Keep §9 #7 (Claude/Perplexity mobile teardown) open as a device-lab task — not closeable by desk research.

---

## 5. Open questions

1. **Virtualizer choice** — does TanStack Virtual's new `followOnAppend`/`anchorTo:'end'` actually beat Virtua and VirtuosoMessageList on *our* streaming + variable-height + smart-anchor acceptance tests, including inside a Capacitor WebView on mid-tier Android? (Spike.)
2. **Local-first vs server-authoritative** — is the MVP staying server-authoritative (simpler, billing-safe) or moving toward local-first-with-sync to match the privacy story? (PRD 04 decision.)
3. **iOS haptics** — accept "no web haptics on iOS" for the foreseeable future, or is this a (minor) Capacitor-era nicety worth listing as a native trigger sweetener? (Likely accept; low value.)
4. **`navigator.storage.persist()` grant rate** — how reliably is it granted for our installed PWA in practice, and do we surface a UI nudge to install (improving grant odds) without nagging? (Instrument in PRD 05.)
5. **Web-push value on Android** — given web-push steady-state opt-in is ~5–8%, is the §4.9 P1 Android web-push effort justified pre-Capacitor, or should it wait? (Monetization/retention call — PRD 05.)
6. **Mid-stream re-prompt UX** — incumbents (ChatGPT) allow editing the prompt while streaming; is that in scope for our composer, and does it interact with stop-preserves-partial (PRD 01)? (Cross-PRD.)

---

## 6. Sources (accessed 2026-05-27)

**iOS keyboard / viewport**
- The Virtual Keyboard API Is Broken Where It Matters Most — https://zouhir.org/blog/virtual-keyboard-api/
- The virtual keyboard API (Ahmad Shadeed) — https://ishadeed.com/article/virtual-keyboard-api/
- VirtualKeyboard API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/VirtualKeyboard_API
- Fix mobile keyboard overlap with visualViewport (F. Moretti) — https://www.franciscomoretti.com/blog/fix-mobile-keyboard-overlap-with-visualviewport
- Prepare for viewport resize behavior changes coming to Chrome on Android — https://developer.chrome.com/blog/viewport-resize-behavior
- <meta name="viewport"> (MDN) — https://developer.mozilla.org/en-US/docs/Web/HTML/Guides/Viewport_meta_element
- Control Viewport Resize with `interactive-widget` (HTMHell) — https://www.htmhell.dev/adventcalendar/2024/4/
- CSS *vh (dvh, lvh, svh) units (DEV) — https://dev.to/frehner/css-vh-dvh-lvh-svh-and-vw-units-27k4
- Viewport Unit Variants browser support (LambdaTest/TestMu) — https://www.testmuai.com/learning-hub/viewport-unit-variants-browser-support/
- Viewport Units 2026 (TheLinuxCode) — https://thelinuxcode.com/viewport-units-in-css-mastering-vh-vw-and-the-modern-dvhsvhlvh-family-2026/

**iOS PWA / push / storage / wake lock / share**
- PWA iOS Limitations and Safari Support [2026] (MagicBell) — https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide
- Do PWAs Work on iOS? Complete Guide 2026 (Mobiloud) — https://www.mobiloud.com/blog/progressive-web-apps-ios
- PWA Push Notifications on iOS in 2026 (Webscraft) — https://webscraft.org/blog/pwa-pushspovischennya-na-ios-u-2026-scho-realno-pratsyuye?lang=en
- Updates to Storage Policy (WebKit) — https://webkit.org/blog/14403/updates-to-storage-policy/
- Storage quotas and eviction criteria (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- Safari iOS PWA Data Persistence Beyond 7 Days (Apple Developer Forums 710157) — https://developer.apple.com/forums/thread/710157
- Screen Wake Lock PWA Demo (Progressier) — https://progressier.com/pwa-capabilities/screen-wake-lock
- Screen Wake Lock (whatpwacando.today) — https://whatpwacando.today/wake-lock/
- share_target (MDN) — https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/share_target
- WebKit bug 194593 — Add support for Web Share Target API — https://bugs.webkit.org/show_bug.cgi?id=194593

**EU PWA reversal**
- Apple reverses decision to remove Home Screen web apps in EU (The Register, 2024-03-02) — https://www.theregister.com/2024/03/02/apple_reverses_pwa_decision/
- iOS 17.4 won't remove Home Screen web apps in the EU after all (9to5Mac, 2024-03-01) — https://9to5mac.com/2024/03/01/apple-home-screen-web-apps-ios-17-eu/
- Update on apps distributed in the EU (Apple Developer) — https://developer.apple.com/support/dma-and-apps-in-the-eu/

**Virtualization / scroll**
- Chat UIs Are Lists Until They Aren't (TanStack Blog, 2026-05-25) — https://tanstack.com/blog/tanstack-virtual-chat
- react-virtuoso (GitHub) — https://github.com/petyosi/react-virtuoso
- React Virtuoso — https://virtuoso.dev/
- Virtua (Best of JS) — https://bestofjs.org/projects/virtua
- VirtualizedMessageList (GetStream) — https://getstream.io/chat/docs/sdk/react/components/core-components/virtualized_list/
- Overview of scroll anchoring (MDN) — https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Scroll_anchoring/Overview
- overscroll-behavior (MDN) — https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overscroll-behavior

**Performance / INP / streaming render**
- Optimize long tasks (web.dev) — https://web.dev/articles/optimize-long-tasks
- How to Test scheduler.yield() (NitroPack) — https://nitropack.io/blog/post/introducing-scheduler-yield
- Core Web Vitals 2026 (corewebvitals.io) — https://www.corewebvitals.io/core-web-vitals
- Core Web Vitals 2026: INP, LCP & CLS Optimization (DigitalApplied) — https://www.digitalapplied.com/blog/core-web-vitals-2026-inp-lcp-cls-optimization-guide
- INP Optimization Complete Guide 2026 (LinkGraph) — https://www.linkgraph.com/blog/interaction-to-next-paint-optimization/
- Why React Apps Lag With Streaming Text (Akash Kumar) — https://akashbuilds.com/blog/chatgpt-stream-text-react
- Streaming Backends & React: Controlling Re-render Chaos (SitePoint) — https://www.sitepoint.com/streaming-backends-react-controlling-re-render-chaos/
- Improve Web Performance With requestAnimationFrame (DebugBear) — https://www.debugbear.com/blog/requestanimationframe

**Capacitor vs RN**
- Capacitor vs React Native 2025 (NextNative) — https://nextnative.dev/blog/capacitor-vs-react-native
- React Native vs Expo vs Capacitor 2026 (PkgPulse) — https://www.pkgpulse.com/guides/react-native-vs-expo-vs-capacitor-cross-platform-mobile-2026
- Comparing React Native vs Capacitor (Capgo) — https://capgo.app/blog/comparing-react-native-vs-capacitor/
- Capacitor vs RN vs Flutter: Hybrid Apps 2026 (Kanopy) — https://kanopylabs.com/blog/capacitor-vs-react-native-vs-flutter

**Haptics**
- ios-haptics (GitHub, tijnjh) — https://github.com/tijnjh/ios-haptics
- navigator.vibrate works on iOS Safari (mdn browser-compat-data #29166) — https://github.com/mdn/browser-compat-data/issues/29166
- Vibration API PWA Demo (Progressier) — https://progressier.com/pwa-capabilities/vibration-api

**Voice / Web Speech**
- Web Speech API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- Add iOS Speech Recognition Support to Your Web App (xjavascript) — https://www.xjavascript.com/blog/add-ios-speech-recognition-support-for-web-app/
- Unclear interimResults Web Speech in Safari iOS (WebKit Documentation #120) — https://github.com/WebKit/Documentation/issues/120

**Push opt-in benchmarks**
- The Great Push Notifications Benchmark 2025 (Batch) — https://batch.com/ressources/etudes/benchmark-notifications-push-crm-mobile
- Mobile App Push Notification Benchmarks 2026 (Airship) — https://www.airship.com/resources/mobile-app-push-notification-benchmarks-2026/
- 50+ Push Notification Statistics (Mobiloud) — https://www.mobiloud.com/blog/push-notification-statistics

**Offline-first patterns**
- Offline-first frontend apps in 2025 (LogRocket) — https://blog.logrocket.com/offline-first-frontend-apps-2025-indexeddb-sqlite/
- Best Offline-First Tech Stack for 2026 (CSS Author) — https://cssauthor.com/offline-first-tech-stack/
- Dexie.js — https://dexie.org/

**Competitive (incumbents)**
- Gemini 3 Pro vs ChatGPT vs Claude vs Perplexity 2026 (Clickforest) — https://www.clickforest.com/en/blog/gemini-3-pro-vs-chatgpt-vs-claude-vs-perplexity
- ChatGPT vs Claude vs Perplexity vs Gemini April 2026 (AI Magicx) — https://www.aimagicx.com/blog/chatgpt-vs-claude-vs-perplexity-vs-gemini-april-2026
