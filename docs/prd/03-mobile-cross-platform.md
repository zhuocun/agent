# PRD 03 — Mobile & Cross-Platform Experience

**Product:** A transparent, multi-model, cost-leading AI chat for web and mobile (mobile-web first)
**Workstream:** Responsive layout shell, mobile adaptation, PWA, cross-platform delivery
**Owner:** Product (Mobile & Cross-Platform)
**Status:** Draft for build
**Date:** 2026-05-27

---

## 1. Summary & purpose

Mobile excellence is a stated differentiation lever for this product: incumbents (ChatGPT, Claude, Gemini, Perplexity) under-invest in mobile-web, so a genuinely first-class responsive + PWA experience is a competitive wedge, especially for our priority persona (power users / developers) who copy-paste between phone and desktop, and for privacy-conscious prosumers.

This PRD owns the **mobile/responsive adaptation, the layout shell, and cross-platform delivery**. It does **not** define base chat features (model selection, streaming, artifacts, history semantics) — those live in **PRD 01 (Chat UI)**. This document specifies how that chat experience is framed across breakpoints, how it behaves on touch devices and flaky networks, how it is delivered as a PWA, and when/how a native wrapper follows.

Delivery is decided: **MVP = one responsive Next.js (App Router) web app + a PWA layer.** A **Capacitor** native wrapper follows later, triggered by concrete needs (reliable iOS push, App Store presence, durable offline, native device APIs). React Native is explicitly rejected (full UI rewrite, no meaningful chat-perf gain).

---

## 2. Goals & non-goals

### Goals
- A single responsive codebase whose **layout shell** adapts at defined breakpoints (mobile single-pane + overlay drawer → tablet → desktop 2-pane → large desktop 3-pane with artifact panel).
- A mobile composer that is rock-solid against on-screen-keyboard quirks via a two-track mechanism: **iOS = `visualViewport` JS positioning (primary)**; Chromium/Firefox = `dvh` + `interactive-widget=resizes-content` (no-op on iOS); plus `viewport-fit=cover` + all four safe-area insets (see §4.3; corrected).
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
10. **Attach from phone (P1):** "When vision/PDF ships, I attach a photo from camera or library via the + button to ask about it." *(Out of P0 — text-only MVP.)*

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

> **Corrected (verified, blocking):** on iOS/iPadOS Safari the software keyboard resizes only the **visual** viewport, not the layout viewport — so `dvh`/`svh`/`lvh` do **not** shrink on keyboard show and a `dvh`-only sticky/fixed bottom composer **gets covered by the keyboard**. `interactive-widget=resizes-content` is supported in **Chromium 108+ and Firefox 132+** but is a **no-op on iOS**, so `visualViewport` stays primary on iOS. The composer mechanism is therefore **two-track**, with `visualViewport` JS as the **primary** path on iOS (not a fallback).

- **[P0]** Composer pinned to the bottom. **iOS primary mechanism = `visualViewport`-driven positioning:** listen to `visualViewport` `resize`/`scroll` and position the composer (via a CSS var / `top` + transform) to track the shrinking visual viewport so it stays above the keyboard. This is the default path on iOS, **not** an edge-case fallback. *(Shipped — `lib/use-visual-viewport.ts`, consumed by `app-shell.tsx` to drive the keyboard inset.)*
- **[P0]** **Android/Chromium + Firefox track:** app shell uses **`dvh`** (e.g., `h-dvh` flex column), not raw `vh`, plus viewport meta **`interactive-widget=resizes-content`** (supported in Chromium 108+ and Firefox 132+) so the browser resizes content (not just the visual viewport) on keyboard show. (These do not help on iOS, where `interactive-widget` is a no-op — see note above.)
- **[P0]** **`viewport-fit=cover`** in the viewport meta — **required** for `env(safe-area-inset-*)` to be non-zero at all.
- **[P0]** **All four safe-area insets:** apply `env(safe-area-inset-bottom/top/left/right)` to composer/header (e.g., `padding-bottom: calc(env(safe-area-inset-bottom) + Xpx)`), so the composer/header clear the home indicator, notch/Dynamic Island, and landscape-iPhone left/right insets — not bottom only.
- **[P1]** **Progressive-enhancement layer** (demoted from the primary path): `dvh`/`svh`/`lvh` full-height sizing where supported, and the **VirtualKeyboard API** `env(keyboard-inset-*)` (Chromium-only) to reserve precise space below the list/input; returns `0px` when hidden. Treat as enhancement over the `visualViewport` baseline, not as the iOS keyboard fix.
- **[P0]** **Explicit Send button** (large, thumb-reachable, meets tap-target min).
- **[P0]** **Auto-grow textarea:** grows from 1 line to a max (~5–8 lines) then internal scroll. Set `enterkeyhint="send"`, `inputmode`, and sensible `autocapitalize`/`autocorrect` on the textarea for clean mobile keyboard behavior.
- **[P0]** **Mobile Enter = newline** (no Shift on touch keyboards); Send button sends. Desktop keeps `Enter`=send / `Shift+Enter`=newline (PRD 01 owns desktop key handling).
- **[P0]** **IME composition handling:** Send must not fire while an IME composition is in progress — gate on `event.isComposing` (and `compositionstart`/`compositionend`) so CJK/autocorrect composition is not cut off mid-input. Relevant to the i18n posture in PRD 00.
- **[P1]** Make Enter-behavior **configurable** in settings; A/B validate the default.
- **[P0]** **iOS keyboard quirks** explicitly tracked as risk: even with the `visualViewport` mechanism, fixed-bottom behavior varies across iOS versions. **Real-device lab testing on multiple iPhone/iOS versions is required before launch** (§9). Acceptance: the composer is **never covered by the keyboard regardless of composer length**, and **tapping the composer does not yank the scroll** (both are documented incumbent failures).
- **[P1 — partially shipped]** Attach affordance (+ / paperclip) opens a **bottom sheet**: Camera / Photo Library / Files. Mic/voice button adjacent (see §4.7). All meet tap-target minimums (§4.8). **P0: omit +/paperclip**; composer is text-only (PRD 01 §4.3).
  - **Shipped:** a single paperclip → multi-file picker (image / PDF / text; provider-gated — shown only on attachment-capable tiers, so **inert on the prod DeepSeek backend** and live under Anthropic; see PRD 01 §4.3). **NOT shipped:** the Camera (`capture="environment"`) / Photo Library / Files split into a **bottom-sheet chooser** — that distinct-affordance split (§4.7) is still deferred.

### 4.4 Touch & gestures (every gesture has a tappable alternative)

- **[P0]** **Long-press a message bubble** → context menu (copy, edit, regenerate, react, delete — actions per PRD 01). Tappable alternative: a kebab/overflow on the bubble. *(Shipped.)*
- **[P0]** **Swipe-to-delete / archive** a conversation row in the drawer. Tappable alternative: row kebab menu. Behavior consistent everywhere it appears. *(Shipped — swipe via `lib/use-swipe-actions.ts` with a row kebab fallback; the destructive action is delete, since archive is deferred per PRD 01 §4.5.)*
- **[P0]** **Scroll-to-bottom FAB** ("jump to latest") appears when the user has scrolled up; paired with smart auto-scroll. *(Shipped — `message-list.tsx`, `aria-label="Jump to latest"`.)*
- **[P0]** **Smart auto-scroll (anchor-to-bottom):** if the user is within ~N px of the bottom when a new token/message arrives, auto-scroll to follow; if they have scrolled up to read, **suppress auto-scroll** and surface the FAB. Do not yank the view. (This is the single most common mobile-chat annoyance to get right — see spike §9.) *(Shipped — `atBottom` tracking in `message-list.tsx`.)*
  - *Acceptance:* during a streaming response, scrolling up to read keeps the viewport stationary; tapping the FAB re-pins to bottom and resumes following.
- **[P0]** **`overscroll-behavior: contain`** on the message list and app root — prevents scroll-chaining **and** blocks browser pull-to-refresh, which would otherwise reload the page and **kill an in-flight stream + optimistic/queue state** (LibreChat filed exactly this bug). Hardening item that protects the §4.6 interrupted-stream goals.
- **[P1]** **Haptics:** subtle vibration on long-press and on send (sub-100ms visual feedback regardless). Implement via the **Vibration API on Android** (feature-detected). **Treat web haptics on iOS as unreliable / not dependable** — the old `<input type="checkbox switch">` + label-`click()` shim appears no longer to fire programmatically on recent iOS (community-level evidence — an `ios-haptics` repo + an MDN browser-compat issue — not a primary Apple release note, so do not treat this as a confirmed, version-pinned kill). On iOS, **degrade silently to visual feedback only**; do not depend on web haptics. Feature-detect and degrade silently elsewhere. Honor reduced-motion / system settings.
- **~~[P1] Pull-to-refresh~~ — DROPPED**: native pull-to-refresh reloads the page and kills in-flight streams, contradicting interrupted-stream recovery (§4.6, user story #4). Superseded by `overscroll-behavior: contain` above. If ever wanted, scope to the **history drawer only**, never the conversation. *(Roadmap note for PRD 05.)*

### 4.5 Message-list performance (top technical spike — see §9)

- **[P0 — shipped]** **Virtualize** long conversations (only visible messages in the DOM). **Shipped via a bespoke measure-and-cache window hook** (`lib/use-virtual-message-window.ts`), **not** one of the spike's candidate libraries: the message list virtualizes past a threshold (~80 messages), measuring and caching each row's height and rendering only a windowed slice plus top/bottom padding spacers (`message-list.tsx`). The library evaluation below is therefore moot unless a perf ceiling is hit. **Original three co-equal spike candidates (§9), retained for the record:**
  - **Virtua** (~3 kB) — free, zero-config, **built-in reverse scrolling**.
  - **`VirtuosoMessageList`** (React Virtuoso) — purpose-built for human/AI streaming chat (streaming, stick-to-bottom, imperative scroll-on-arrival API); **commercially licensed**.
  - **TanStack Virtual** — free, headless/most flexible. **Reportedly now supports chat** (`anchorTo: 'end'` / `followOnAppend`), **to be confirmed by the spike** (single, very recent source — do not treat as established fact).
- **[P0]** Virtualization must coexist with **streaming + variable bubble heights + smart auto-scroll** without jumpiness. Measure-and-cache item heights. Pair with `overscroll-behavior: contain` (§4.4).
- **[P1]** **`content-visibility: auto`** on off-screen message bubbles as a cheaper complement (or alternative on shorter threads) to full virtualization.
  - *Acceptance:* a 1,000+ message conversation scrolls at ~60fps on a mid-tier Android device; streaming a long answer does not cause scroll jitter or height-jump artifacts.

### 4.6 Offline & flaky-network

- **[P0]** **Optimistic send:** the user's message renders immediately; the network request runs in the background and reconciles/retries on failure. Users never block on a flaky API.
- **[P0]** **IndexedDB** (e.g., Dexie) stores messages, chat metadata, **per-conversation composer drafts**, and an **unsent-actions queue** (separate tables). Schema/sync internals owned by PRD 04.
- **[P0]** **Retry with exponential backoff;** queued operations carry metadata (type, payload, timestamp, status) and preserve **ordering for dependent changes**.
- **[P0]** **Draft persistence:** interrupted/typed drafts survive reload/navigation (WhatsApp-style).
- **[P0]** **Interrupted-stream recovery (partial persist, no SSE replay):** a network drop, server error, or failed stream marks the assistant message **incomplete** in UI and persists all partial tokens server-side. Offer one-tap **Continue** (send continuation as a new request) and **Regenerate** (re-run last user turn). *AC:* no empty/broken bubble; actions work after reload. This is **not** resumable-stream replay.
- **[P1 — shipped]** **Resumable-stream replay** (PRD 04 §5.1): same-device reconnect replays buffered SSE from `stream.id`. When replay is unavailable (Redis evicted), fall back to the P0 partial + Continue/Regenerate UX. Do not label P0 Continue as "resume stream."
  - **Shipped:** on a mid-stream read error the client re-fetches `GET /api/conversations/{id}/stream/{streamId}` once and resumes consuming the replayed SSE (`lib/stream-client.ts`, `resetForReplay` / `reconnectAttemptedRef`); a non-ok reconnect (e.g. 410 `STREAM_REPLAY_TRUNCATED`) surfaces the typed error and falls back to the **P0 Continue/Regenerate** path (also shipped — `message-actions.tsx` `canContinue`/Regenerate).
- **[P0]** **Storage quota & eviction (corrected, verified):** iOS PWA storage is **NOT ~50 MB** — since Safari 17 the per-origin quota is **disk-proportional (typically tens of GB)**, readable via `navigator.storage.estimate()`. The real iOS constraint is **7-day ITP eviction of non-persisted data**, not capacity. Implication: we **can** cache far more conversation history offline on iOS than previously assumed.
- **[P0]** **Request `navigator.storage.persist()`** to exclude the local store from 7-day eviction (more likely granted for installed PWAs); read `navigator.storage.estimate()` for budgeting. *(Schema/sync internals owned by PRD 04.)*
- **[P0]** **Server is source of truth.** Treat the local cache as best-effort; re-fetch from server on load. Even with disk-proportional quota, do not assume durable offline history on iOS unless `storage.persist()` was granted.
- **[P1]** **Background Sync** to replay queued sends when back online on Android. **Also replay on `online`/foreground events** since Background Sync is unavailable on iOS.
- **[P1]** **Sync-engine build-vs-buy** is a flagged **PRD 04 dependency**: MVP stays hand-rolled (Dexie + queue), but PRD 04 should consciously decide vs a batteries-included sync engine / CRDT path (Dexie Cloud, PowerSync, ElectricSQL, RxDB, Yjs/Automerge) before reinventing one — aligns with the privacy-first "local is real" story.

### 4.7 Mobile input (voice / camera / share)

- **[P1]** **Voice / speech-to-text** via Web Speech API (`SpeechRecognition`) as **progressive enhancement**.
  - **Privacy correction (verified):** Web Speech recognition is **NOT on-device** — on iOS Safari it **sends audio to Apple** (explicit "send audio to Apple" permission modal) and Chrome is also typically server-side. For a privacy-first product (PRD 00 §7), this must be a **disclosed, optional** feature: surface an in-UI disclosure ("dictation sends audio to your browser vendor") before first use — treat the disclosure as **P0-for-the-feature**. Do **not** describe it as on-device/privacy-preserving.
  - The **privacy-aligned path is a self-hosted / BYOK STT** option (see server-side STT below) — position it as the privacy-first answer, not a mere fallback.
  - Caveats surfaced in UI: unsupported in Firefox; **does not work in an installed iOS PWA** (works in Safari tab). Hide/disable the mic where unsupported.
- **[P1 — partially shipped]** **Camera / photo attach** baseline: offer **two distinct affordances** — a camera input (`<input type="file" accept="image/*" capture="environment">`, opens the camera directly) **and** a separate library/files input (`<input type="file" accept="image/*">`, **no** `capture`, so the OS picker offers gallery/files). Depends on PRD 01 §4.3 attachments + PRD 02 FR-30/31. **P0 does not expose camera/library inputs.** (Robust native picker comes with Capacitor later.)
  - **Shipped:** a single combined file input (image / PDF / text, no `capture`); the **Camera-vs-Library two-input split is NOT shipped** (see §4.3). Provider-gated, so inert on DeepSeek.
- **[P2]** **Web Share Target** (installed app appears in OS share sheet to receive shared text/links/images). Android-supported; **iOS support weak/absent for PWAs — verify before committing** (§9). Treat full share-target as a Capacitor-era capability.
- **[P1]** **Self-hosted / BYOK server-side STT** as the **privacy-aligned** voice path (not merely a fallback) — the on-thesis option if cross-platform voice becomes a priority, and the way to avoid silently shipping user audio to Apple/Google.

### 4.8 Mobile accessibility

- **[P0]** **Tap targets 44–48px** (iOS 44pt / Android 48dp), ≥8px spacing; WCAG 2.2 SC 2.5.8 minimum (≥24×24 CSS px) is the floor, not the target.
- **[P0]** **Screen readers:** VoiceOver (iOS) + TalkBack (Android). Semantic structure; ARIA roles/labels on composer, Send, attach, and message actions. Streaming output announces via a **polite live region** (not spammy per-token). *(Shipped — `live-region.tsx` is a single `role="status" aria-live="polite"` region carrying discrete status transitions.)*
- **[P0]** **Gesture alternatives:** every gesture (swipe-to-delete, long-press menu, edge-swipe drawer) has a visible non-gesture control.
- **[P0]** **Contrast** ≥4.5:1 body text (also aids outdoor readability).
- **[P1]** **Dynamic type:** respect iOS Dynamic Type / Android `sp`; use `rem`, avoid fixed-px text.
- **[P1]** **Reduced motion:** honor `prefers-reduced-motion` for streaming animations and transitions.

### 4.9 PWA

- **[P0]** **Web app manifest** (name, icons, theme/background color, `display: standalone`, start URL, scope).
- **[P0]** **Service worker** caching the **app shell** for instant load (Workbox or equivalent; details in PRD 04).
- **[P0]** **Android install** via `beforeinstallprompt` (deferred, contextual prompt — not on first load).
- **[P0]** **Custom iOS "Add to Home Screen" coachmark** (Safari has no auto-prompt). Shown contextually to Safari/iOS users; dismissible and not nagging. *(Shipped — `install-coachmark.tsx`.)*
- **[P1]** **Web push on Android** (reliable re-engagement channel). Use **Declarative Web Push** (Safari 18.4, Mar 2025; W3C Working Draft, now the preferred format) for the Android/iOS-installed push path; simpler/more reliable than the service-worker push flow.
- **[P1]** **`Screen Wake Lock`** during long streaming answers so the screen doesn't dim mid-response (available for home-screen web apps since Safari 18.4). Honor battery/system constraints; release on stream end.
- **[P0]** **Enumerate & design around iOS PWA limits** (see §6.4 table). Specifically:
  - Web push only when **installed to home screen** AND **iOS 16.4+**; not from Safari tabs. (Opt-in remains install-gated; *implementation* is improved by Declarative Web Push.)
  - **EU iOS 17.4+ (resolved):** Apple **reversed** the standalone-PWA removal after DMA feedback; standalone EU Home-Screen web apps + push have been reinstated since **iOS 17.4 (March 2024)**. This is well-sourced and settled; a few secondary blogs still parrot the original removal — treat those as outdated, not a live risk.
  - Storage is **disk-proportional (tens of GB)**, **not ~50 MB** (corrected §4.6); real constraint is **7-day eviction unless `navigator.storage.persist()` is granted**; **no background sync/fetch**; **no auto-install prompt**; **Web Speech broken in installed iOS PWA**.
  - **iOS 26** opens Home-Screen sites as web apps by default (even without a manifest) → lower install friction *after* install.
  - *Acceptance:* the iOS build degrades gracefully — no feature silently fails; unsupported features are hidden or clearly labeled.

### 4.10 Performance budgets

- **[P0]** Core Web Vitals (mobile, field/RUM): **LCP ≤ 2.5s**, **INP ≤ 200ms**, **CLS ≤ 0.1**. Set internal budgets and monitor RUM (metrics ownership: PRD 05). **INP is the most-failed 2026 vital (~43% of sites fail the 200ms threshold) and streaming chat is its worst case** — treat INP as the hardest budget and the techniques below as P0, not nice-to-haves.
- **[P0]** **INP — yield to the main thread:** for expensive interaction handlers (send, model switch, markdown re-parse), break long tasks with **`scheduler.yield()`** (with a `setTimeout(0)` fallback) so input stays responsive during streaming. Named technique (reported ~60–65% p75-INP reduction).
- **[P0]** **Streaming render coalescing:** batch token updates **per animation frame (rAF)** rather than re-rendering per token; throttle auto-scroll; avoid layout thrash. (Promoted P1→P0 — this is the primary INP mitigation for a token-streaming list.)
- **[P0]** **Bundle / main-thread budget:** **initial route JS ≤ ~200 KB compressed**, enforced by a **CI bundle-size check**. JS parse/exec dominates LCP/INP on mid-tier phones (~50–80ms CPU per 100 KB compressed), so the CWV targets are not actionable without a KB budget.
- **[P0]** **CLS protection:** reserve space for streaming content, images (`srcset` + explicit dimensions), and the composer; use `dvh`/`svh` for stable full-height sizing. (Note: iOS keyboard-driven shift is handled by the §4.3 `visualViewport` mechanism, **not** viewport units, which do not track the iOS keyboard.)
- **[P0]** **Code-split / lazy-load** routes and heavy panels: artifact/canvas panel, markdown + code-highlighting, heavy model-output renderers. **KaTeX + syntax highlighter** must be lazy-loaded, not in the initial bundle. **Mermaid engine is P1** (PRD 01 §4.4); P0 may ship zero Mermaid JS. Keep initial JS minimal (within the budget above).
- **[P1]** **Images:** compress, lazy-load, responsive `srcset`/`sizes`, reserved dimensions.
- **[P2]** **Battery:** coalesce DOM writes, pause non-visible work, avoid busy timers; monitor as future CWV signals (animation smoothness/battery) emerge.

---

## 5. Responsive layout spec

> **Exact px values below are defaults aligned with verified guidance — flag for prototype validation with real content + a device lab (§9).** Treat breakpoints as device-class ranges, not magic numbers.

### 5.1 Breakpoint table

| Token | Range (px) | Surface class | Panes | Navigation / shell rules | Validation |
|---|---|---|---|---|---|
| `sm` (mobile) | `< 768` | Mobile | **Single pane** (chat only) | History = temporary **overlay drawer** (hamburger top-left). Attach = **single file picker shipped (provider-gated, inert on DeepSeek)**; the Camera/Library/Files bottom-sheet chooser remains deferred (§4.3/§4.7). Artifact = **full-screen / bottom sheet**. Composer pinned bottom with all four safe-area insets + `viewport-fit=cover`; keyboard handled via the two-track mechanism (§4.3 — iOS `visualViewport` primary). | **Validate px** |
| `md` (tablet) | `768–1023` | Tablet | Chat full-width + collapsible drawer | Drawer **dismissible/persistent**; **push-vs-overlay TBD by prototype**. Artifact = overlay or replaces chat. | **Validate px + push/overlay** |
| `lg` (desktop) | `1024–1439` | Desktop S | **2-pane** | Permanent sidebar + chat. Artifact slides in as a **3rd column** (chat narrows) when invoked. | **Validate px** |
| `xl` (large desktop) | `≥ 1440` | Desktop L | **3-pane** | Sidebar + chat + artifact panel coexist comfortably. Chat column capped for readability. | **Validate px** |

### 5.2 Pane rules

- Number of visible panes and the way navigation is exposed are **adaptive** (swap at breakpoints); content **within** each pane is **fluid** (messages reflow, composer grows). Hybrid model.
- Drawer behavior maps to MUI-style conventions: temporary/overlay (mobile) → persistent/dismissible (tablet) → permanent (desktop).
- Artifact panel escalates: full-screen/bottom-sheet (mobile) → overlay/replace (tablet) → 3rd column on demand (desktop) → always-available (large desktop).

### 5.3 Cross-cutting layout rules

- Use **`dvh` / `svh` / `lvh`** (not raw `vh`) for full-height surfaces; **prefer `dvh` for the app shell** (sizing the shell to `lvh` shows a white strip on iOS until first scroll); `100vh` only as a legacy fallback. **Note:** these units do **not** track the iOS keyboard — the keyboard fix is the `visualViewport` mechanism in §4.3, not viewport units.
- **Reserve space (anti-CLS)** for streaming content, images (dimensions + `srcset`), and the composer.
- **Single source of truth** for the shell — resolved: **viewport breakpoints / a breakpoint hook for the shell** (pane count, drawer mode = genuinely viewport-level), and **container (size) queries — Baseline-safe — for reusable panes** that adapt to their available column width (artifact panel, composer toolbar, message-bubble action row). Panes/drawer derive from the shell source.
- **Chat reading column capped (~70–80ch)** on wide screens for legibility.
- **Tap targets 44–48px;** primary actions in the thumb zone (bottom third; bottom-right favored for right-handers; ~49% of users browse one-handed).

---

## 6. Cross-platform delivery strategy

### 6.1 MVP — responsive web app + PWA (now)

Ship **one responsive Next.js (App Router) web app, progressively enhanced into a PWA.** Rationale: fastest to market, single codebase, universal reach, instant updates, no app-store gatekeeping — and it satisfies the mobile-web-first mandate while giving Android users a near-native installed experience. Scope = everything tagged [P0]/[P1] in §4.

### 6.2 Later — Capacitor native wrapper (triggered)

Add a **Capacitor** shell that wraps the existing web app in a WebView + native plugin bridge, reusing **~100% of the web/PWA codebase**. This unlocks App Store / Play presence, native push (APNs), reliable offline / larger storage, share extensions, and a robust native camera/file picker — with a flat learning curve for web devs.

**Explicit triggers to start the Capacitor build:**
1. **iOS push-driven re-engagement becomes a core KPI** (web push on iOS remains install-gated, with low opt-in: ~16% — single-source figure, we instrument our own opt-in per §8). *This is the primary trigger.* Note: **Declarative Web Push (Safari 18.4) narrows the *implementation* gap** for installed-PWA push, but the *opt-in/install-gated* gap that drives this trigger remains.
2. **App-store presence / discoverability** is required for the business.
3. **Eviction-proof durable storage and/or background sync** is needed — *not* raw capacity. **Corrected:** the old "~50 MB" cap is wrong (Safari 17+ quota is disk-proportional, tens of GB), so capacity is *not* the constraint. The genuine iOS PWA gaps are **7-day ITP eviction** of non-persisted data (only partly mitigated by `navigator.storage.persist()`, §4.6) and the **absence of background sync/fetch**. Go native when you need guaranteed durable local history or true background replay.
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
| Web push | Broad | **16.4+ AND installed-to-home only**; not from tabs; EU standalone PWA + push **reinstated since iOS 17.4 (Mar 2024)** after Apple's DMA reversal (settled). Declarative Web Push (18.4) simplifies the installed path. |
| Background sync / fetch | Supported | **None** — replay on foreground/`online` instead |
| Storage quota | Hundreds of MB | **Disk-proportional (tens of GB), NOT ~50 MB** (Safari 17+; read via `navigator.storage.estimate()`) — capacity is not the constraint; server stays source of truth |
| Cache persistence | Persistent | **7-day ITP eviction** of non-persisted data; mitigate with **`navigator.storage.persist()`** (more likely granted for installed PWAs); cleared with Safari history |
| Web Speech (recognition) | Supported (Chromium) | **Broken in installed PWA** (works in Safari tab) |
| Hardware (BLE/NFC/USB) | Many | Not supported; camera/mic/geo permission-dependent |

**Implication:** PWA gives excellent app-like UX on Android, a *partial* one on iOS. The Capacitor wrapper is the iOS mitigation.

---

## 7. Dependencies & cross-references

- **PRD 01 — Chat UI:** owns base chat features, streaming protocol, message actions (copy/edit/regenerate/react/delete), artifact/canvas content, model selection, desktop key handling. This PRD frames and adapts them for mobile; do not duplicate.
- **PRD 04 — Architecture / PWA / Storage:** owns service-worker/caching strategy internals, IndexedDB schema, sync engine, offline reconciliation, backend source-of-truth contract, and the AI-data-disclosure/consent mechanism (used by §6.2 Guideline 5.1.2). This PRD states UX requirements against those systems.
- **PRD 05 — Metrics:** owns RUM/analytics instrumentation that backs §8 success metrics (mobile CWV, retention, install rate, mobile TTFT).
- **Tech baseline:** Next.js App Router frontend + FastAPI/Fly SSE backend; responsive web; Tailwind/component library reused into Capacitor later.

---

## 8. Success metrics

| Metric | Target / intent | Source |
|---|---|---|
| Mobile LCP (p75, field) | ≤ 2.5s | PRD 05 RUM |
| Mobile INP (p75, field) | ≤ 200ms | PRD 05 RUM |
| Mobile INP breakdown (input delay / processing / presentation) | Track the **processing-time** component — INP is the risk metric and streaming chat is its worst case | PRD 05 RUM |
| Mobile CLS (p75, field) | ≤ 0.1 | PRD 05 RUM |
| Initial route JS (compressed) | ≤ ~200 KB, CI-enforced (see §4.10) | CI / synthetic |
| % mobile sessions passing all 3 CWV | Beat the ~48% web baseline; set internal floor | PRD 05 RUM |
| Mobile TTFT (time-to-first-token) | Track + budget (coordinate w/ PRD 01/04) | PRD 05 |
| Mobile quality (TTFT, INP, stream recovery) | Track p75 field data + interrupted recovery success | PRD 05 §6.1 |
| Mobile D1 / D7 / D30 retention | Track as secondary mobile cohort signal; primary product retention = GRR/NRR + task-recurrence + Day-1 success | PRD 05 §6.1 |
| PWA install rate (Android) | Track install-prompt accept rate | PRD 05 |
| iOS Add-to-Home-Screen coachmark conversion | Track (expect low; informs Capacitor trigger #2) | PRD 05 |
| Web-push opt-in (Android) | Track (iOS expected ~16% — informs Capacitor trigger #1) | PRD 05 |
| Message-list scroll FPS (mid-tier Android) | ~60fps target, incl. during streaming | Synthetic / lab |
| Interrupted-stream recovery success rate | High; track Continue/Regenerate usage | PRD 05 |

---

## 9. Open questions & risks

1. **TOP SPIKE — virtualization + streaming + variable heights + auto-scroll.** **RESOLVED:** shipped a bespoke virtual-window hook (`lib/use-virtual-message-window.ts`, measure-and-cache); library evaluation is moot unless a perf ceiling is hit. Highest technical risk in the message list. **Recommended direction (historical):** prototype **three co-equal candidates** — **Virtua** (free, ~3 kB, built-in reverse scrolling), **`VirtuosoMessageList`** (purpose-built for AI streaming chat; commercially licensed), and **TanStack Virtual** (free, headless; reportedly now supports chat via `anchorTo: 'end'`/`followOnAppend` — to be confirmed by the spike, single recent source) — against real streaming + smart anchor-to-bottom. Decide on the acceptance tests (license cost vs effort), not on a stale maintainer quote. Pair the winner with `overscroll-behavior: contain` (§4.4) and `content-visibility: auto` (§4.5).
2. **iOS keyboard mechanism — RESOLVED direction:** the fix is **`visualViewport` JS as the primary composer path on iOS** (+ `viewport-fit=cover` + all four safe-area insets), **not** `dvh`/`interactive-widget` (`interactive-widget` is a no-op on iOS; `dvh` does not shrink under the iOS keyboard) — see §4.3. Residual risk is version variance, not mechanism: **a real-device lab across multiple iPhone/iOS versions is still required** before launch, against the §4.3 acceptance tests (composer never covered regardless of length; tapping composer never yanks scroll).
3. **Breakpoint validation.** Exact px values and the **tablet drawer push-vs-overlay** decision need prototype validation with real content.
4. **Web Share Target on iOS.** Assumed weak/absent for PWAs; **verify current status** before committing to share-to-AI on mobile web (otherwise it's a Capacitor-era feature).
5. **EU iOS 17.4+ push restriction — RESOLVED/CLOSED.** Apple reversed the removal; standalone EU Home-Screen web apps + push have been reinstated since **iOS 17.4 (March 2024)**. Well-sourced and settled — no revalidation needed.
6. **Send-vs-newline default on mobile.** Industry-standard default (Enter = newline) should be A/B validated and made configurable.
7. **Competitive teardown (Claude / Perplexity mobile).** Confirm exact drawer/tab/bottom-sheet and artifact patterns (Gemini/ChatGPT verified; these recalled).
8. **Google Play PWA policy specifics** (TWA path / current rules) — verify before Capacitor/Play submission.

---

## 10. References

**Key source URLs (from research + review):**
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
