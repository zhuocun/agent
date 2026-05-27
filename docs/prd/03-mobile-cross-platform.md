# PRD 03 — Mobile & Cross-Platform Experience

**Product:** A transparent, multi-model, privacy-first AI chat for web and mobile (mobile-web first)
**Workstream:** Responsive layout shell, mobile adaptation, PWA, cross-platform delivery
**Owner:** Product (Mobile & Cross-Platform)
**Status:** Draft for build
**Date:** 2026-05-27
**Source research:** `docs/research/02-mobile-responsive.md`

---

## 1. Summary & purpose

Mobile excellence is a stated differentiation lever for this product: incumbents (ChatGPT, Claude, Gemini, Perplexity) under-invest in mobile-web, so a genuinely first-class responsive + PWA experience is a competitive wedge, especially for our priority persona (power users / developers) who copy-paste between phone and desktop, and for privacy-conscious prosumers.

This PRD owns the **mobile/responsive adaptation, the layout shell, and cross-platform delivery**. It does **not** define base chat features (model selection, streaming, artifacts, history semantics) — those live in **PRD 01 (Chat UI)**. This document specifies how that chat experience is framed across breakpoints, how it behaves on touch devices and flaky networks, how it is delivered as a PWA, and when/how a native wrapper follows.

Delivery is decided: **MVP = one responsive Next.js (App Router) web app + a PWA layer.** A **Capacitor** native wrapper follows later, triggered by concrete needs (reliable iOS push, App Store presence, durable offline, native device APIs). React Native is explicitly rejected (full UI rewrite, no meaningful chat-perf gain).

---

## 2. Goals & non-goals

### Goals
- A single responsive codebase whose **layout shell** adapts at defined breakpoints (mobile single-pane + overlay drawer → tablet → desktop 2-pane → large desktop 3-pane with artifact panel).
- A mobile composer that is rock-solid against on-screen-keyboard quirks (modern `dvh` + `interactive-widget=resizes-content` + safe-area insets).
- Smooth, performant long-conversation scrolling during token streaming on mid-tier phones.
- Resilient behavior on flaky / offline networks (optimistic send, draft persistence, retry queue, interrupted-stream recovery).
- App-like installability on Android via PWA; best-effort app-like UX on iOS within Safari/PWA limits.
- Meet mobile Core Web Vitals budgets and mobile accessibility baselines.
- A clear, trigger-based path to a Capacitor native build without a rewrite.

### Non-goals
- Defining base chat features / streaming protocol / artifact rendering (PRD 01).
- Backend architecture, sync engine internals, storage schema (PRD 04).
- A React Native app, or any second UI codebase (rejected — see §6).
- Native iOS/Android builds in the MVP (deferred to Capacitor phase).
- Desktop installable (Tauri/Electron) builds in MVP (out of scope; revisit later).
- A bottom tab bar in MVP (deferred until ≥3 peer top-level destinations exist — see §4.2).

---

## 3. Key user stories (mobile-centric)

1. **Power user on the move:** "On my phone I start a question on the train, the keyboard never covers my input, I tap Send, and the answer streams smoothly even on 4G."
2. **History switcher:** "I swipe / tap the menu to open my conversation list, search it, start a new chat, and the OS Back button closes the drawer instead of dumping me out of the app."
3. **Flaky network:** "I hit Send in a tunnel; my message appears instantly, and when signal returns it sends automatically — my half-typed draft is never lost."
4. **Interrupted stream:** "A streamed answer cut off mid-sentence; I get a one-tap Continue/Regenerate instead of a broken bubble."
5. **Reader during streaming:** "I scroll up to re-read while the model is still typing and the view does NOT yank me to the bottom; a 'jump to latest' button appears when I want it."
6. **Installer (Android):** "I install the app to my home screen, it opens full-screen, and I get a push when a long task finishes."
7. **Installer (iOS):** "Safari won't auto-prompt, so the app shows me a clear 'Add to Home Screen' coachmark; I understand what I do and don't get on iOS."
8. **Accessibility user:** "Every swipe action also has a visible button; VoiceOver/TalkBack reads the composer and message actions; streaming doesn't spam my screen reader."
9. **Voice input:** "I dictate a prompt with the mic button when my browser supports it, and the feature degrades gracefully when it doesn't (e.g., installed iOS PWA)."
10. **Attach from phone:** "I attach a photo from camera or library via the + button to ask about it."

---

## 4. Functional / UX requirements

Tags: **[P0/MVP]** ship for launch · **[P1]** fast-follow · **[P2]** later / Capacitor-era.

### 4.1 Layout shell & panes

- **[P0]** Single responsive codebase; the layout shell is derived from **one source of truth** (a breakpoint hook or container queries), not duplicated per-component. Panes and drawer state read from the same state.
  - *Acceptance:* resizing the viewport across breakpoints (or rotating a device) transitions the shell without reloading and without orphaned/duplicated drawer state.
- **[P0]** Mobile (`sm`, `< 768px`): single pane (chat only); history is a **temporary overlay drawer** (hamburger, top-left); artifact/code/citation views open **full-screen or as a bottom sheet** (defer to PRD 01 for artifact content).
- **[P1]** Tablet (`md`, `768–1023px`): chat full-width with dismissible/persistent drawer; artifact overlays or replaces chat. Push-vs-overlay decided by prototype (§9).
- **[P0]** Desktop (`lg`, `1024–1439px`): permanent sidebar + chat (2-pane). Artifact panel enters as a **3rd column** (chat narrows) when invoked.
- **[P1]** Large desktop (`xl`, `≥ 1440px`): sidebar + chat + artifact panel coexist comfortably (3-pane).
- Full breakpoint spec in **§5**.

### 4.2 Mobile navigation

- **[P0]** Hamburger (top-left) opens history overlay drawer containing: **Search chats**, **New chat**, pinned conversations first, then recent history list. (Mirrors category convention to reduce switching cost.)
- **[P0]** **Edge-swipe** opens/closes the drawer; the hamburger button is the always-available tappable alternative.
- **[P0]** **History API integration:** opening a drawer / bottom sheet / full-screen artifact pushes a history state so the device/gesture **Back** dismisses overlays in order: bottom sheet → drawer → artifact full-screen → chat root → browser history.
  - *Acceptance:* with the drawer open, pressing Back closes the drawer and stays in the conversation; pressing Back at chat root behaves per browser. In standalone/PWA mode (no browser chrome), an in-app Back affordance is present on every nested view.
- **[P0]** "New chat" reachable in ≤1 tap from the chat screen (drawer + a persistent affordance).
- **[P2]** **Bottom tab bar** (Chats / Discover / Library / Settings) introduced **only when** ≥3 durable peer destinations exist. Until then, do not add one (a chat app's primary surface is the conversation; "navigation" is really history + new chat, i.e., a list, not 3–5 peers). When added: max 5 items; history stays inside the Chats tab's drawer; use overflow/Priority+ for 6+.

### 4.3 Mobile composer & keyboard

- **[P0]** Composer pinned to the bottom; app shell uses **`dvh`** (e.g., `h-dvh` flex column), not raw `vh`, so the visible viewport adjusts when the keyboard shows — **no JS resize observer as the primary mechanism**.
- **[P0]** Add viewport meta **`interactive-widget=resizes-content`** so Android/Chromium resizes content (not just the visual viewport) on keyboard show; works additively with `dvh`.
- **[P0]** **Safe-area insets:** `padding-bottom: calc(env(safe-area-inset-bottom) + Xpx)` so the composer clears the iOS home indicator / notch.
- **[P0]** **Legacy fallback:** feature-test and fall back to `100vh`; keep `visualViewport` measurement only as an edge-case fallback, not the default path.
- **[P1]** Progressive enhancement: use VirtualKeyboard API `env(keyboard-inset-*)` (Chromium-only) to reserve precise space below the list/input; returns `0px` when hidden.
- **[P0]** **Explicit Send button** (large, thumb-reachable, meets tap-target min).
- **[P0]** **Auto-grow textarea:** grows from 1 line to a max (~5–8 lines) then internal scroll.
- **[P0]** **Mobile Enter = newline** (no Shift on touch keyboards); Send button sends. Desktop keeps `Enter`=send / `Shift+Enter`=newline (PRD 01 owns desktop key handling).
- **[P1]** Make Enter-behavior **configurable** in settings; A/B validate the default.
- **[P0]** **iOS keyboard quirks** explicitly tracked as risk: `dvh` improves but does not fully guarantee fixed-bottom behavior on all iOS versions. **Real-device lab testing on multiple iPhone/iOS versions is required before launch** (§9).
- **[P0]** Attach affordance (+ / paperclip) opens a **bottom sheet**: Camera / Photo Library / Files. Mic/voice button adjacent (see §4.7). All meet tap-target minimums (§4.8).

### 4.4 Touch & gestures (every gesture has a tappable alternative)

- **[P0]** **Long-press a message bubble** → context menu (copy, edit, regenerate, react, delete — actions per PRD 01). Tappable alternative: a kebab/overflow on the bubble.
- **[P0]** **Swipe-to-delete / archive** a conversation row in the drawer. Tappable alternative: row kebab menu. Behavior consistent everywhere it appears.
- **[P0]** **Scroll-to-bottom FAB** ("jump to latest") appears when the user has scrolled up; paired with smart auto-scroll.
- **[P0]** **Smart auto-scroll (anchor-to-bottom):** if the user is within ~N px of the bottom when a new token/message arrives, auto-scroll to follow; if they have scrolled up to read, **suppress auto-scroll** and surface the FAB. Do not yank the view. (This is the single most common mobile-chat annoyance to get right — see spike §9.)
  - *Acceptance:* during a streaming response, scrolling up to read keeps the viewport stationary; tapping the FAB re-pins to bottom and resumes following.
- **[P1]** **Haptics:** subtle vibration on long-press and on send (sub-100ms visual feedback regardless). Honor reduced-motion / system settings.
- **[P1]** **Pull-to-refresh** on history/conversation (optional given streaming; low priority).

### 4.5 Message-list performance (top technical spike — see §9)

- **[P0]** **Virtualize** long conversations (only visible messages in the DOM). Library: **React Virtuoso** (purpose-built for dynamic heights, reverse/infinite scroll, sticky headers) as the leading candidate; **TanStack Virtual** as alternative. Decide in the spike.
- **[P0]** Virtualization must coexist with **streaming + variable bubble heights + smart auto-scroll** without jumpiness. Measure-and-cache item heights.
  - *Acceptance:* a 1,000+ message conversation scrolls at ~60fps on a mid-tier Android device; streaming a long answer does not cause scroll jitter or height-jump artifacts.

### 4.6 Offline & flaky-network

- **[P0]** **Optimistic send:** the user's message renders immediately; the network request runs in the background and reconciles/retries on failure. Users never block on a flaky API.
- **[P0]** **IndexedDB** (e.g., Dexie) stores messages, chat metadata, **per-conversation composer drafts**, and an **unsent-actions queue** (separate tables). Schema/sync internals owned by PRD 04.
- **[P0]** **Retry with exponential backoff;** queued operations carry metadata (type, payload, timestamp, status) and preserve **ordering for dependent changes**.
- **[P0]** **Draft persistence:** interrupted/typed drafts survive reload/navigation (WhatsApp-style).
- **[P0]** **Interrupted-stream recovery:** a network drop mid-stream marks the partial assistant message incomplete and offers one-tap **Continue / Regenerate**; partial tokens are persisted so a reconnect can resume or replace cleanly.
- **[P0]** **Server is source of truth.** Treat the local cache as best-effort, especially on iOS (~50 MB cap, 7-day eviction). Re-fetch from server; never assume durable offline history on iOS.
- **[P1]** **Background Sync** to replay queued sends when back online on Android. **Also replay on `online`/foreground events** since Background Sync is unavailable on iOS.

### 4.7 Mobile input (voice / camera / share)

- **[P1]** **Voice / speech-to-text** via Web Speech API (`SpeechRecognition`) as **progressive enhancement** (prefer on-device for privacy). Caveats surfaced in UI: unsupported in Firefox; **does not work in an installed iOS PWA** (works in Safari tab). Hide/disable the mic where unsupported.
- **[P0]** **Camera / photo attach** baseline: offer **two distinct affordances** — a camera input (`<input type="file" accept="image/*" capture="environment">`, opens the camera directly) **and** a separate library/files input (`<input type="file" accept="image/*">`, **no** `capture`, so the OS picker offers gallery/files). A single input *with* `capture` suppresses the library path, so do not rely on one input for both. (Robust native picker comes with Capacitor later.)
- **[P2]** **Web Share Target** (installed app appears in OS share sheet to receive shared text/links/images). Android-supported; **iOS support weak/absent for PWAs — verify before committing** (§9). Treat full share-target as a Capacitor-era capability.
- **[P1]** Server-side STT fallback considered if cross-platform voice becomes a priority.

### 4.8 Mobile accessibility

- **[P0]** **Tap targets 44–48px** (iOS 44pt / Android 48dp), ≥8px spacing; WCAG 2.2 SC 2.5.8 minimum (≥24×24 CSS px) is the floor, not the target.
- **[P0]** **Screen readers:** VoiceOver (iOS) + TalkBack (Android). Semantic structure; ARIA roles/labels on composer, Send, attach, and message actions. Streaming output announces via a **polite live region** (not spammy per-token).
- **[P0]** **Gesture alternatives:** every gesture (swipe-to-delete, long-press menu, edge-swipe drawer) has a visible non-gesture control.
- **[P0]** **Contrast** ≥4.5:1 body text (also aids outdoor readability).
- **[P1]** **Dynamic type:** respect iOS Dynamic Type / Android `sp`; use `rem`, avoid fixed-px text.
- **[P1]** **Reduced motion:** honor `prefers-reduced-motion` for streaming animations and transitions.

### 4.9 PWA

- **[P0]** **Web app manifest** (name, icons, theme/background color, `display: standalone`, start URL, scope).
- **[P0]** **Service worker** caching the **app shell** for instant load (Workbox or equivalent; details in PRD 04).
- **[P0]** **Android install** via `beforeinstallprompt` (deferred, contextual prompt — not on first load).
- **[P0]** **Custom iOS "Add to Home Screen" coachmark** (Safari has no auto-prompt). Shown contextually to Safari/iOS users; dismissible and not nagging.
- **[P1]** **Web push on Android** (reliable re-engagement channel).
- **[P0]** **Enumerate & design around iOS PWA limits** (see §6.4 table). Specifically:
  - Web push only when **installed to home screen** AND **iOS 16.4+**; not from Safari tabs.
  - **EU iOS 17.4+**: PWAs may open as Safari tabs → push restricted (verify current 2026 status — §9).
  - ~**50 MB** storage cap; **7-day** cache eviction when unused; **no background sync/fetch**; **no auto-install prompt**; **Web Speech broken in installed iOS PWA**.
  - *Acceptance:* the iOS build degrades gracefully — no feature silently fails; unsupported features are hidden or clearly labeled.

### 4.10 Performance budgets

- **[P0]** Core Web Vitals (mobile, field/RUM): **LCP ≤ 2.5s**, **INP ≤ 200ms**, **CLS ≤ 0.1**. Set internal budgets and monitor RUM (metrics ownership: PRD 05).
- **[P0]** **CLS protection:** reserve space for streaming content, images (`srcset` + explicit dimensions), and the composer; use `dvh`/`svh` to avoid keyboard-driven shift.
- **[P0]** **Code-split / lazy-load** routes and heavy panels: artifact/canvas panel, markdown + code-highlighting, heavy model-output renderers. Keep initial JS minimal.
- **[P1]** **Streaming render coalescing:** batch token updates per animation frame (rAF) rather than re-rendering per token; throttle auto-scroll; avoid layout thrash.
- **[P1]** **Images:** compress, lazy-load, responsive `srcset`/`sizes`, reserved dimensions.
- **[P2]** **Battery:** coalesce DOM writes, pause non-visible work, avoid busy timers; monitor as future CWV signals (animation smoothness/battery) emerge.

---

## 5. Responsive layout spec

> **Exact px values below are defaults aligned with verified guidance — flag for prototype validation with real content + a device lab (§9).** Treat breakpoints as device-class ranges, not magic numbers.

### 5.1 Breakpoint table

| Token | Range (px) | Surface class | Panes | Navigation / shell rules | Validation |
|---|---|---|---|---|---|
| `sm` (mobile) | `< 768` | Mobile | **Single pane** (chat only) | History = temporary **overlay drawer** (hamburger top-left). Tools/attach = **bottom sheet**. Artifact = **full-screen / bottom sheet**. Composer pinned bottom with safe-area + `dvh`. | **Validate px** |
| `md` (tablet) | `768–1023` | Tablet | Chat full-width + collapsible drawer | Drawer **dismissible/persistent**; **push-vs-overlay TBD by prototype**. Artifact = overlay or replaces chat. | **Validate px + push/overlay** |
| `lg` (desktop) | `1024–1439` | Desktop S | **2-pane** | Permanent sidebar + chat. Artifact slides in as a **3rd column** (chat narrows) when invoked. | **Validate px** |
| `xl` (large desktop) | `≥ 1440` | Desktop L | **3-pane** | Sidebar + chat + artifact panel coexist comfortably. Chat column capped for readability. | **Validate px** |

### 5.2 Pane rules

- Number of visible panes and the way navigation is exposed are **adaptive** (swap at breakpoints); content **within** each pane is **fluid** (messages reflow, composer grows). Hybrid model.
- Drawer behavior maps to MUI-style conventions: temporary/overlay (mobile) → persistent/dismissible (tablet) → permanent (desktop).
- Artifact panel escalates: full-screen/bottom-sheet (mobile) → overlay/replace (tablet) → 3rd column on demand (desktop) → always-available (large desktop).

### 5.3 Cross-cutting layout rules

- Use **`dvh` / `svh` / `lvh`** (not raw `vh`) for full-height surfaces; `100vh` only as a legacy iOS fallback.
- **Reserve space (anti-CLS)** for streaming content, images (dimensions + `srcset`), and the composer.
- **One source of truth** for the shell (container queries or a breakpoint hook); panes/drawer derive from it.
- **Chat reading column capped (~70–80ch)** on wide screens for legibility.
- **Tap targets 44–48px;** primary actions in the thumb zone (bottom third; bottom-right favored for right-handers; ~49% of users browse one-handed).

---

## 6. Cross-platform delivery strategy

### 6.1 MVP — responsive web app + PWA (now)

Ship **one responsive Next.js (App Router) web app, progressively enhanced into a PWA.** Rationale: fastest to market, single codebase, universal reach, instant updates, no app-store gatekeeping — and it satisfies the mobile-web-first mandate while giving Android users a near-native installed experience. Scope = everything tagged [P0]/[P1] in §4.

### 6.2 Later — Capacitor native wrapper (triggered)

Add a **Capacitor** shell that wraps the existing web app in a WebView + native plugin bridge, reusing **~100% of the web/PWA codebase**. This unlocks App Store / Play presence, native push (APNs), reliable offline / larger storage, share extensions, and a robust native camera/file picker — with a flat learning curve for web devs.

**Explicit triggers to start the Capacitor build:**
1. **iOS push-driven re-engagement becomes a core KPI** (web push on iOS is too weak: ~16% opt-in — single-source figure, we instrument our own opt-in per §8 — install-gated, EU-restricted). *This is the primary trigger.*
2. **App-store presence / discoverability** is required for the business.
3. **Durable offline / large local storage** is needed beyond iOS PWA's ~50 MB / 7-day limits.
4. **Native share-target, deeper camera/file integration, or device APIs** are needed.

**Capacitor-era tradeoffs / obligations:**
- **App Store Guideline 4.2 (minimum functionality):** a thin WebView wrapper risks rejection. Must add genuine native value (push, robust offline, widgets, Siri shortcuts, share extensions, native navigation). Expect possible rejection/resubmission cycles.
- **Guideline 5.1.2 (AI / privacy, 2025):** sharing personal data with third-party AI systems requires **explicit disclosure and clear user permission before transmitting**. Directly relevant — design consent UX accordingly (coordinate with privacy/PRD 04).
- **Google Play** is generally more lenient toward web-wrapped/PWA paths (TWA / Play-listed PWA) — verify current policy.
- Ongoing native build/release pipeline overhead.

### 6.3 Why not React Native / Tauri

- **React Native (rejected):** would require **rewriting the entire UI** in RN components (no reuse of our responsive web UI / Tailwind / component library) for **no meaningful performance benefit on a chat app** — modern WebViews are "typically sufficient" for message lists, streaming, and typing indicators. RN only justified if native fidelity/perf becomes non-negotiable (heavy continuous hardware like BLE/AR), which is not our case. Choosing RN would defeat the single-codebase advantage that is core to our delivery strategy.
- **Tauri (not for mobile MVP):** mobile maturity lags Capacitor; better suited to a possible future **desktop** installable build. Revisit only for desktop.

### 6.4 PWA capabilities by platform

| Capability | Android (Chrome) | iOS (Safari) |
|---|---|---|
| Install / add-to-home | `beforeinstallprompt` auto-prompt | **Manual only** (Share → Add to Home Screen); no auto-prompt → custom coachmark |
| Web push | Broad | **16.4+ AND installed-to-home only**; not from tabs; **EU 17.4+ restricted (verify current 2026 status — §9)** |
| Background sync / fetch | Supported | **None** — replay on foreground/`online` instead |
| Storage quota | Hundreds of MB | **~50 MB cap** — server is source of truth |
| Cache persistence | Persistent | **7-day eviction** if unused; cleared with Safari history |
| Web Speech (recognition) | Supported (Chromium) | **Broken in installed PWA** (works in Safari tab) |
| Hardware (BLE/NFC/USB) | Many | Not supported; camera/mic/geo permission-dependent |

**Implication:** PWA gives excellent app-like UX on Android, a *partial* one on iOS. The Capacitor wrapper is the iOS mitigation.

---

## 7. Dependencies & cross-references

- **PRD 01 — Chat UI:** owns base chat features, streaming protocol, message actions (copy/edit/regenerate/react/delete), artifact/canvas content, model selection, desktop key handling. This PRD frames and adapts them for mobile; do not duplicate.
- **PRD 04 — Architecture / PWA / Storage:** owns service-worker/caching strategy internals, IndexedDB schema, sync engine, offline reconciliation, backend source-of-truth contract, and the AI-data-disclosure/consent mechanism (used by §6.2 Guideline 5.1.2). This PRD states UX requirements against those systems.
- **PRD 05 — Metrics:** owns RUM/analytics instrumentation that backs §8 success metrics (mobile CWV, retention, install rate, mobile TTFT).
- **Tech baseline:** Next.js App Router + Vercel AI SDK; responsive web; Tailwind/component library reused into Capacitor later.

---

## 8. Success metrics

| Metric | Target / intent | Source |
|---|---|---|
| Mobile LCP (p75, field) | ≤ 2.5s | PRD 05 RUM |
| Mobile INP (p75, field) | ≤ 200ms | PRD 05 RUM |
| Mobile CLS (p75, field) | ≤ 0.1 | PRD 05 RUM |
| % mobile sessions passing all 3 CWV | Beat the ~48% web baseline; set internal floor | PRD 05 RUM |
| Mobile TTFT (time-to-first-token) | Track + budget (coordinate w/ PRD 01/04) | PRD 05 |
| Mobile D1 / D7 / D30 retention | Track; primary mobile-quality signal | PRD 05 |
| PWA install rate (Android) | Track install-prompt accept rate | PRD 05 |
| iOS Add-to-Home-Screen coachmark conversion | Track (expect low; informs Capacitor trigger #2) | PRD 05 |
| Web-push opt-in (Android) | Track (iOS expected ~16% — informs Capacitor trigger #1) | PRD 05 |
| Message-list scroll FPS (mid-tier Android) | ~60fps target, incl. during streaming | Synthetic / lab |
| Interrupted-stream recovery success rate | High; track Continue/Regenerate usage | PRD 05 |

---

## 9. Open questions & risks

1. **TOP SPIKE — virtualization + streaming + variable heights + auto-scroll.** Highest technical risk in the message list. Prototype Virtuoso vs TanStack Virtual against real streaming + smart anchor-to-bottom; budget dedicated spike time before committing.
2. **iOS keyboard edge cases.** `dvh` + `interactive-widget` improves but does not fully guarantee fixed-bottom composer behavior across iOS versions. **Requires a real-device lab** across multiple iPhone/iOS versions before launch.
3. **Breakpoint validation.** Exact px values and the **tablet drawer push-vs-overlay** decision need prototype validation with real content.
4. **Web Share Target on iOS.** Assumed weak/absent for PWAs; **verify current status** before committing to share-to-AI on mobile web (otherwise it's a Capacitor-era feature).
5. **EU iOS 17.4+ push restriction.** Apple's EU PWA policy has been in flux; **revalidate 2026 status** before designing iOS push UX.
6. **Send-vs-newline default on mobile.** Industry-standard default (Enter = newline) should be A/B validated and made configurable.
7. **Competitive teardown (Claude / Perplexity mobile).** Confirm exact drawer/tab/bottom-sheet and artifact patterns (Gemini/ChatGPT verified; these recalled).
8. **Google Play PWA policy specifics** (TWA path / current rules) — verify before Capacitor/Play submission.

---

## 10. References

**Primary research:** `docs/research/02-mobile-responsive.md`

**Key source URLs (from research):**
- Responsive build guide — https://www.weweb.io/blog/how-to-build-a-responsive-web-app-guide
- MUI Drawer responsive sidebar — https://kombai.com/mui/drawer/
- Responsive breakpoints 2025 (BrowserStack) — https://www.browserstack.com/guide/responsive-design-breakpoints
- Gemini Android UI overhaul — https://android.gadgethacks.com/news/google-gemini-android-app-gets-major-ui-overhaul/
- Bottom navigation 2025 guide — https://blog.appmysite.com/bottom-navigation-bar-in-mobile-apps-heres-all-you-need-to-know/
- Mobile keyboard overlap with dvh — https://www.franciscomoretti.com/blog/fix-mobile-keyboard-overlap-with-visualviewport
- VirtualKeyboard API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/VirtualKeyboard_API
- Safe-area / stick-to-bottom (DEV) — https://dev.to/vladimirschneider/how-stick-element-to-bottom-of-viewport-on-mobile-1pg6
- VirtualizedMessageList (GetStream) — https://getstream.io/chat/docs/sdk/react/components/core-components/virtualized_list/
- Streaming chat scroll-to-bottom (Dave Lage) — https://davelage.com/posts/chat-scroll-react/
- Offline-first 2025 (LogRocket) — https://blog.logrocket.com/offline-first-frontend-apps-2025-indexeddb-sqlite/
- Web Vitals (web.dev) — https://web.dev/articles/vitals
- Core Web Vitals 2026 — https://www.corewebvitals.io/core-web-vitals
- Web Speech API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- Speech Recognition PWA capability — https://progressier.com/pwa-capabilities/speech-recognition
- PWA iOS limitations (MagicBell) — https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide
- Push notifications in PWAs (MagicBell) — https://www.magicbell.com/blog/using-push-notifications-in-pwas
- PWA on iOS (Brainhub) — https://brainhub.eu/library/pwa-on-ios
- Capacitor vs React Native 2025 (NextNative) — https://nextnative.dev/blog/capacitor-vs-react-native
- RN vs Expo vs Capacitor 2026 (PkgPulse) — https://www.pkgpulse.com/guides/react-native-vs-expo-vs-capacitor-cross-platform-mobile-2026
- Guideline 4.2 Minimum Functionality — https://iossubmissionguide.com/guideline-4-2-minimum-functionality/
- App Store AI rules 2025 (OpenForge) — https://openforge.io/app-store-review-guidelines-2025-essential-ai-app-rules/
- WCAG2Mobile-22 (W3C) — https://www.w3.org/TR/wcag2mobile-22/
- Mobile accessibility guide 2026 (Corpowid) — https://corpowid.ai/blog/mobile-application-accessibility-practical-humancentered-guide-android-ios
