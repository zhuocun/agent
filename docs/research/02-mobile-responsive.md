# Mobile & Cross-Platform UX and Delivery Strategy

**Workstream:** Mobile & Cross-Platform UX / delivery strategy
**Project:** Web-based AI Chat interface (desktop web + mobile web first; possible installable/native later)
**Date:** 2026-05-27
**Status:** Research phase (feeds PRDs)

> **Source confidence legend**
> - **[Verified]** — directly supported by a cited 2025–2026 source fetched/searched during this research.
> - **[Recalled]** — drawn from general engineering/UX knowledge, not re-verified against a fetched source. Treat as a strong default but validate during the spec/prototyping phase.
> Uncertainties are flagged inline and consolidated in the "Open questions & uncertainties" section.

---

## 1. Executive summary

For an AI chat product that must be excellent on desktop web and mobile web (mobile-web-first), the strongest 2025–2026 strategy is:

1. **Build one responsive web app** with a fluid single codebase, layered with **adaptive breakpoint rules** that swap the *layout shell* (multi-pane on desktop -> single-pane + drawer on mobile) rather than maintaining separate apps. **[Verified — see §2]**
2. **Add a PWA layer** (manifest, service worker, offline shell, install prompt, web push) to make the mobile-web experience feel app-like. **[Verified — see §6]**
3. **Defer native** until there is a clear need (App Store presence, reliable push on iOS, deep device integration). When that time comes, **Capacitor** is the lowest-friction path because it wraps the existing web app with near-100% code reuse. **[Verified — see §6, §11]**

The single biggest constraint shaping this strategy is **iOS PWA limitations** (web push only when installed-to-home-screen, ~50 MB storage cap, 7-day cache eviction, no background sync, no auto-install prompt). **[Verified — see §6.4]**

---

## 2. Responsive vs adaptive layout strategy

### 2.1 Fluid (responsive) vs adaptive — definitions

- **Fluid/responsive layout** uses relative units (%, `fr`, `rem`, viewport units) so elements expand/contract proportionally as the viewport changes. **[Verified]** (weweb.io)
- **Adaptive layout** uses several distinct fixed layouts for specific screen-size ranges, serving the most appropriate one per device class (mobile / tablet / desktop). **[Verified]** (weweb.io)

**Recommended approach for a chat app: a hybrid.** Use a *fluid* approach within each pane (messages reflow, composer grows), but make *adaptive* decisions about the **layout shell** (how many panes are visible and how navigation is exposed) at defined breakpoints. This mirrors how MUI frames drawer behavior: temporary/overlay drawers for mobile, persistent/dismissible for tablet, permanent for desktop. **[Verified]** (kombai.com, designmonks.co)

### 2.2 The pane model

| Surface | Panes | Navigation | Notes |
|---|---|---|---|
| **Desktop (>= ~1024px)** | Sidebar (conversation list) + Chat + optional Artifact/Canvas panel | Permanent sidebar, always visible | 2-pane default; artifact panel becomes a 3rd pane when an artifact/code/citation view is open. **[Recalled]** matches ChatGPT/Claude/Gemini desktop. |
| **Tablet (~768–1023px)** | Chat full-width + collapsible sidebar | Persistent/dismissible drawer; artifact panel becomes an overlay or replaces chat | Often the trickiest breakpoint — decide whether sidebar pushes or overlays. **[Verified]** (designmonks.co) |
| **Mobile (< ~768px)** | Single pane (chat only) | Temporary overlay drawer (hamburger) for conversation list; artifact opens full-screen or as a bottom sheet | On mobile primary nav collapses behind a hamburger/menu revealing a full-screen drawer or bottom sheet. **[Verified]** (justinmind.com) |

### 2.3 How the leading AI apps do it **[Verified, partial]**

- **Gemini (Aug 2025 Android redesign):** top-left chat icon replaced by a **hamburger that opens a navigation drawer** with a "Search for chats" field, a "New chat" shortcut, recent Gems, pinned conversations first, then a scrolling history list. Google deliberately mirrored ChatGPT's mobile layout and **bottom-sheet tool drawer** to reduce switching costs. (android.gadgethacks.com)
- **ChatGPT:** popularized the **bottom-sheet tool/attachment drawer** and a sidebar-as-drawer pattern on mobile; large central shortcut buttons on the home screen. **[Verified, indirect]** (android.gadgethacks.com)
- **Claude / Perplexity:** **[Recalled]** follow the same convergent pattern — single-pane chat on mobile with a left drawer for history; Perplexity adds a bottom-ish tab/segmented model for discover/library on its native app. Not directly verified in this pass; confirm during competitive teardown.

**Takeaway:** the category has converged on **drawer-for-history + single-pane-chat + bottom composer + bottom-sheet for tools** on mobile. Adopting this lowers the learning curve for users migrating from incumbents. **[Verified]** (android.gadgethacks.com)

---

## 3. Mobile navigation patterns

### 3.1 Drawer (hamburger) vs bottom navigation

- **Bottom tab bars** are described as "the gold standard for mobile apps and PWAs," ideal for **3–5 main sections**, placed in thumb reach. Switching from hamburger to bottom tabs produced large engagement gains in cited cases (Redbooth: +65% DAU, +70% session time; NN/g: hidden menus reduce task completion ~21%). **[Verified]** (appmysite.com)
- **Hamburger menus** hide features, increase interaction cost, and reduce discoverability — but remain effective for **content-heavy apps with deep hierarchies or occasional actions**. **[Verified]** (uxpin.com, lollypop.design)
- **49% of users navigate one-handed with the thumb**; the bottom third (and bottom-right for right-handers) is the most reachable zone. **[Verified]** (appmysite.com)

**Recommendation for this product:** A chat app's *primary* surface is the conversation itself, and the main "navigation" is really **conversation history + new chat**. That is a list, not 3–5 peer destinations, so a **left drawer for history is appropriate** (matching the category). **[Verified reasoning, Recalled conclusion]**

If/when the product grows secondary top-level destinations (e.g., Chats / Discover / Library / Projects / Settings — as Perplexity does), introduce a **bottom tab bar** for those 3–5 destinations and keep history inside the Chats tab's drawer. Do **not** put 6+ items in a tab bar — use a Priority+/overflow pattern instead. **[Verified]** (appmysite.com, appinstitute.com)

### 3.2 Swipe gestures & back behavior **[Verified + Recalled]**

- Support **edge-swipe to open/close the drawer** and **swipe-to-go-back** consistent with platform expectations. Always provide a **tappable alternative** for every gesture (accessibility + discoverability). **[Verified]** (universaldesign.ie, codebridge.tech)
- **Back behavior:** on mobile web the hardware/gesture Back should close overlays in this order: bottom sheet -> drawer -> (if in artifact full-screen) return to chat -> (if at chat root) browser history. Use the History API to push a state when opening drawers/sheets so Back dismisses them instead of leaving the conversation. **[Recalled — verify against router/History API behavior in prototype.]**
- For PWA/standalone mode there is no browser chrome Back button, so an in-app Back affordance is mandatory on nested views. **[Recalled]**

---

## 4. Mobile message composer

This is the highest-risk area for mobile chat UX because of the on-screen keyboard.

### 4.1 Sticky bottom input + on-screen keyboard

**Current (Aug 2025) best practice has shifted away from JS observers toward CSS dynamic viewport units.** **[Verified]** (franciscomoretti.com)

- Use **`dvh` (dynamic viewport height)** for the app shell: `100dvh` reflects the visible viewport and adjusts when the keyboard shows, eliminating layout jump without JS. Example pattern: a flex column container at `h-dvh`. **[Verified]** (franciscomoretti.com)
- On Android/Chromium, add the **`interactive-widget=resizes-content`** viewport meta so content (not just the visual viewport) resizes when the keyboard appears; this works additively with `dvh`. **[Verified]** (franciscomoretti.com)
- The earlier widely-cited approach of syncing `visualViewport.height` to a CSS variable via a `resize` observer is now considered **wrong for this use case** — `dvh` handles it natively. Keep `visualViewport` only as a fallback/edge-case tool. **[Verified]** (franciscomoretti.com)
- The **VirtualKeyboard API** exposes `env(keyboard-inset-*)` CSS variables (top/bottom/height etc.); `keyboard-inset-height` can reserve space below the message list/input, returning `0px` when hidden. Chromium-only; treat as progressive enhancement. **[Verified]** (MDN, bram.us)
- **Safe-area insets:** pin the composer with `padding-bottom: calc(env(safe-area-inset-bottom) + Xpx)` so it clears the iOS home indicator / notch. **[Verified]** (dev.to/vladimirschneider)

**iOS Safari caveat:** iOS historically does not fire the same keyboard/resize signals as Android and has quirks where fixed-bottom elements get covered or float; `dvh` improves this on recent iOS but **legacy iOS needs `100vh` fallback and possibly `visualViewport` measurement**. **[Verified]** (franciscomoretti.com — "feature-test and fall back to 100vh"; medium.com/azimolabs on iOS keyboard pain). Plan device-lab testing on real iPhones.

### 4.2 Growing textarea, send vs newline, attachment & voice

- **Auto-growing textarea:** grow from 1 line up to a max (e.g., ~5–8 lines) then internal scroll; an input area that "grows gracefully with multi-line messages" is a baseline chat-UI expectation. **[Verified]** (contus.com)
- **Send vs newline:** **[Recalled — strong industry default]**
  - **Desktop:** `Enter` = send, `Shift+Enter` = newline (ChatGPT/Claude default).
  - **Mobile (touch keyboard):** `Enter`/Return = **newline**, and a dedicated **Send button** sends — because mobile users expect Return to insert a line and there is no Shift. Provide an explicit, large send button. Make this configurable in settings if feasible.
- **Attachment & voice buttons:** place an attach (+/paperclip) affordance and a mic/voice button inside or adjacent to the composer, each meeting tap-target minimums (§9). The attach affordance should open a **bottom sheet** offering Camera / Photo Library / Files (matching the category's bottom-sheet tool drawer). **[Verified pattern]** (android.gadgethacks.com)

---

## 5. Touch interactions & gestures

| Interaction | Pattern | Notes / source |
|---|---|---|
| **Long-press menu** | Long-press a message bubble to reveal a context menu (copy, edit, regenerate, react, delete) | Long-press is a common gesture to reveal context menus. **[Verified]** (devoq.medium.com, pageoneformula.com) |
| **Swipe-to-delete chats** | Swipe a conversation row in the drawer to reveal delete/archive | Swipe-to-delete should behave the same everywhere in the app; always pair with a visible alternative (kebab menu). **[Verified]** (moldstud.com, universaldesign.ie) |
| **Pull-to-refresh** | Pull down at top of history/conversation to refresh | Familiar, efficient pattern; optional for chat since content streams in. **[Verified]** (codebridge.tech) |
| **Scroll-to-bottom button** | Floating "jump to latest" FAB when user has scrolled up during streaming | Pair with smart auto-scroll (§7). **[Verified pattern]** (getstream.io) |
| **Momentum scrolling w/ streaming** | Smart auto-scroll only when already pinned to bottom; otherwise show the scroll-to-bottom button and do NOT yank the view | "smooth" auto-scroll is unwieldy at >2–3 incoming msgs/sec; "auto"/instant is safer. For token streaming, throttle scroll. **[Verified]** (getstream.io) |
| **Feedback** | Sub-100ms visual response; subtle haptics on long-press/send | ~100ms is the threshold for "direct manipulation"; use subtle vibration for long press. **[Verified]** (pageoneformula.com) |

**Streaming + scroll detail [Recalled, important]:** keep the user "anchored" — if they are within ~N px of the bottom when a new token/message arrives, auto-scroll; if they've scrolled up to read, suppress auto-scroll and surface the scroll-to-bottom affordance. This is the single most common mobile-chat annoyance to get right.

---

## 6. Delivery options compared

### 6.1 Comparison table

| Option | What it is | Code reuse | Strengths | Weaknesses | Best when |
|---|---|---|---|---|---|
| **Responsive web app** | One web app, fluid + adaptive layout | n/a (single codebase) | Fastest to ship; universal reach; no app-store gatekeeping; instant updates | No install/home-screen, no push without PWA, limited offline | MVP, broadest reach, fastest iteration **[Verified]** (weweb.io) |
| **PWA** | Web app + manifest + service worker | ~100% (same app) | Installable, offline shell, web push (with caveats), add-to-home-screen, app-like feel | iOS limits (§6.4); no app-store presence by default | Mobile-web-first product wanting app-like UX without native effort **[Verified]** (dev.to PWA-to-native) |
| **Capacitor** | Native shell wrapping the web app in a WebView + native plugin bridge | ~100% with existing web app | "Wrap existing web app fast"; keep HTML/CSS/JS + Tailwind/ShadCN; app-store presence; native plugins (camera, push, etc.); flat learning curve for web devs | WebView perf ceiling for extreme animations; smaller plugin ecosystem than RN; iOS App Store 4.2 review risk if too web-like | You already have a web/PWA and want app stores + native APIs with minimal rewrite **[Verified]** (nextnative.dev, pkgpulse.com, x.com/dulitharw) |
| **React Native / Expo** | True native UI components from JS/React | Business logic only; **UI must be rewritten** | Best native fidelity/perf; huge native module ecosystem; Expo eases dev/build flow | Full UI rewrite; no Tailwind-for-web reuse; Expo managed workflow limits custom native modules (mitigated by bare workflow) | Building mobile from scratch, or native fidelity/perf is non-negotiable **[Verified]** (nextnative.dev, pkgpulse.com) |
| **Tauri** | Lightweight Rust-backed shell (strong on desktop; mobile maturing) | High (web frontend) | Tiny bundles, secure, good for desktop + multi-platform | Mobile support less mature than Capacitor for this use case | Lightweight desktop builds / multi-platform shipping **[Verified, brief]** (x.com/dulitharw) |

### 6.2 Capacitor vs React Native — the decision that matters here **[Verified]** (nextnative.dev)

- **Code reuse:** Capacitor wins decisively for a team that already has a responsive web chat app — "keep your existing code and just add mobile features on top," ~100% reuse. React Native shares business logic but **the entire UI must be rewritten** in RN components.
- **Performance:** RN renders genuine native components (smoother for complex animations/gestures). Modern WebViews have powerful JS engines + hardware-accelerated CSS, making Capacitor's performance "excellent" for content/standard-UI apps like chat. For message lists + typing indicators, Capacitor is "typically sufficient."
- **Native modules:** RN's bridge is better for heavy continuous hardware (BLE/AR). Capacitor's plugins are adequate for camera/GPS/notifications and retain Cordova compatibility. Both sufficient for chat.
- **Learning curve:** Capacitor ~flat for web devs; RN moderate (new component library + styling).
- **Conclusion (source's and ours):** **Capacitor is the pragmatic native path** for this product.

### 6.3 PWA capabilities by platform

| Capability | Android (Chrome) | iOS (Safari) |
|---|---|---|
| Install / add-to-home-screen | `beforeinstallprompt` auto-prompt supported | **Manual only** via Share -> "Add to Home Screen"; no `beforeinstallprompt` **[Verified]** (magicbell.com) |
| Web push | Supported broadly | **iOS 16.4+ only, AND only when installed to home screen**; not from Safari tabs; **not available in EU on iOS 17.4+** (PWAs open as Safari tabs there) **[Verified]** (magicbell.com) |
| Background sync / periodic sync / background fetch | Supported | **None supported** — can't sync/upload/update when closed **[Verified]** (magicbell.com) |
| Storage quota | Hundreds of MB | **~50 MB cap** **[Verified]** (magicbell.com) |
| Cache persistence | Persistent | **7-day eviction** if app unused for a week; cleared with Safari history **[Verified]** (magicbell.com) |
| Hardware (BLE/NFC/USB/sensors) | Many supported | Not supported; camera/mic/geolocation permission-dependent **[Verified]** (magicbell.com) |

### 6.4 iOS PWA limitations — the key risk **[Verified]** (magicbell.com, brainhub.eu, mobiloud.com)

- Web push requires **iOS 16.4+** and **home-screen installation**; **~16% web-push opt-in** vs 40–70% native, worsened by manual install friction. **[Verified]**
- **~50 MB storage**, **7-day cache eviction**, **no background execution** — so do not rely on PWA caching for durable conversation history offline on iOS; treat the server as source of truth and the cache as a best-effort shell. **[Verified]**
- **No auto install prompt** on iOS — must educate users with a custom "Add to Home Screen" coachmark. **[Verified]**
- **Speech Recognition (Web Speech API) does NOT work in an installed iOS PWA** (works in Safari browser tab) — material for a voice feature. **[Verified]** (progressier.com)

**Implication:** PWA delivers excellent app-like UX on Android but only a *partial* one on iOS. For reliable iOS push, durable offline, and App Store presence, a **Capacitor wrapper later** is the mitigation.

---

## 7. Offline & flaky-network behavior **[Verified]** (logrocket.com, pixelfreestudio.com, developersvoice.com)

- **Optimistic UI:** reflect the user's sent message immediately, perform the network request in the background, and reconcile/retry on failure. Users should never wait on a flaky API.
- **Local store:** use **IndexedDB** (e.g., via Dexie.js) for messages, chat metadata, drafts, and an **unsent-actions queue** in separate tables. 2025 IndexedDB has faster indexing/querying and (some browsers) full-text search.
- **Sync queue:** queue operations with metadata (type, payload, timestamp, status); preserve **ordering for dependent changes**; use **retry with exponential backoff**.
- **Draft persistence:** persist composer drafts per-conversation to IndexedDB so an interrupted message survives reload/navigation (WhatsApp-style). Register **Background Sync** to replay queued sends when back online — **but remember Background Sync is unavailable on iOS** (§6.3), so also replay on app foreground/online events.
- **Caching conversations:** cache the **app shell** + recent conversations for instant load; on iOS treat cache as ephemeral (7-day rule) and re-fetch from server. **[Verified]**

**Streaming-specific [Recalled]:** if a streaming response is interrupted (network drop mid-stream), mark the partial assistant message as incomplete and offer a one-tap **"Continue/Regenerate"**; persist partial tokens so a reconnect can resume or replace cleanly.

---

## 8. Mobile performance **[Verified + Recalled]**

### 8.1 Core Web Vitals targets (2025) **[Verified]** (web.dev, corewebvitals.io)

| Metric | Target | Note |
|---|---|---|
| LCP | <= 2.5s | Hardest to pass; only ~62% of mobile pages achieve good LCP. |
| INP | <= 200ms | Replaced FID; critical for a tap-heavy chat composer. |
| CLS | <= 0.1 | Layout shift is a real risk with keyboard + streaming content (mitigate via `dvh`, reserved space). |

Only ~48% of mobile pages pass all three CWV — set internal budgets and monitor RUM. **[Verified]** (corewebvitals.io)

### 8.2 Long message lists — virtualization **[Verified]** (getstream.io, stevekinney.com, medium)

- **Virtualize/window** long conversations so only visible messages are in the DOM; reduces memory + render time and stays performant even with thousands of messages.
- Recommended libraries: **TanStack Virtual** (most popular, flexible) and **React Virtuoso** (handles dynamic item heights, reverse/infinite scroll, sticky headers — well-suited to chat). **[Verified]**
- **Watch-out [Recalled]:** virtualization + streaming + variable bubble heights + auto-scroll is genuinely hard. Virtuoso is purpose-built for this; budget prototype time. Measure-and-cache heights to avoid jumpiness.

### 8.3 Bundle, images, streaming, battery **[Verified targets + Recalled tactics]**

- **Bundle size:** code-split routes/panels, lazy-load the artifact/canvas panel, markdown/code-highlighting, and heavy model-output renderers. Keep initial JS minimal to hit LCP/INP. **[Recalled; aligns with web.dev guidance]** (web.dev "minimize long tasks, reduce DOM size")
- **Images:** compress, lazy-load, use responsive `srcset`/`sizes`, reserve dimensions to protect CLS. **[Verified]** (ateamsoftsolutions.com)
- **Streaming smoothness:** batch token updates (e.g., requestAnimationFrame / coalesce per frame) rather than re-rendering per token; throttle auto-scroll; avoid layout thrash. **[Recalled]**
- **Battery:** streaming + frequent re-render + animations can drain battery; coalesce DOM writes, pause non-visible work, avoid busy timers. Future CWV may even include battery/animation-smoothness signals. **[Verified, forward-looking]** (ateamsoftsolutions.com)

---

## 9. Mobile-specific input

- **Voice / speech-to-text:** **Web Speech API** (`SpeechRecognition`) transcribes speech in-browser; supports **on-device recognition** for privacy/perf. **Caveats:** not supported in Firefox, and **does not work in an installed iOS PWA** (only in Safari tab). For reliable cross-platform voice, consider a server-side STT fallback or, later, a native plugin via Capacitor. **[Verified]** (MDN Web Speech API, progressier.com)
- **Camera / photo attach:** simplest baseline is `<input type="file" accept="image/*" capture="environment">` to invoke the camera, plus a photo-library/files path. Camera/mic are permission-dependent on iOS. A Capacitor build later gives a more robust native camera/file picker. **[Verified context]** (magicbell.com)
- **Share-target integration:** PWA **Web Share Target API** lets the installed app appear in the OS share sheet to receive shared text/links/images (e.g., "share this article to the AI to summarize"). **Android-supported; iOS support is weak/absent for PWAs** — full share-target reliability is a native (Capacitor) capability. **[Recalled — Web Share Target is well-documented as Chromium-first; verify current iOS status before committing.]**

---

## 10. Push notifications & re-engagement

- **Android (Chrome PWA):** web push works broadly; reliable re-engagement channel. **[Verified]** (magicbell.com)
- **iOS:** web push only on **16.4+** and only when **installed to home screen**; **no data-only/background-update notifications**; push listeners may not fire reliably after device restart; unexpected unsubscribes occur; **not available in EU on 17.4+**. Net: **only ~16% web-push opt-in** vs 40–70% native, and most iOS users never reach the prompt because they never installed. **[Verified]** (magicbell.com, brainhub.eu)
- **Re-engagement implication:** do not bank re-engagement on iOS web push. If push-driven retention is a core KPI, that is a primary trigger to ship a **native (Capacitor) iOS build** for proper APNs notifications. **[Verified reasoning]**

---

## 11. App store considerations (if going native later) **[Verified]** (iossubmissionguide.com, mobiloud.com, openforge.io)

- **Guideline 4.2 (minimum functionality):** Apple rejects apps that are "not sufficiently different from a mobile web browsing experience" — a thin WebView wrapper ("web clipping") is a classic rejection. **[Verified]**
- **To pass review,** add genuinely native value: push notifications, robust offline handling, widgets, Siri shortcuts, share extensions, native navigation/device integration. Capacitor supports adding these. Expect possible rejection-resubmission cycles (days–weeks each). **[Verified]**
- **Guideline 5.1.2 (AI / privacy, 2025):** if the app shares personal data with third parties **including third-party AI systems**, you must **explicitly disclose and get clear user permission before transmitting**. Directly relevant to an AI chat app — design consent UX accordingly. **[Verified]** (openforge.io)
- **Google Play** is generally more lenient toward web-wrapped/PWA apps (Trusted Web Activity / Play-listed PWA paths). **[Recalled — verify current Play policy.]**

---

## 12. Accessibility on mobile **[Verified]** (w3.org WCAG2Mobile-22, corpowid.ai, audioeye.com)

- **Tap target size:** WCAG 2.2 (SC 2.5.8 Target Size Minimum) requires **>= 24x24 CSS px** *or* adequate spacing; Apple/Google recommend **44pt (iOS) / 48dp (Android)**. Use 44–48px as the design default, with >= 8px spacing between targets. **[Verified]** (w3.org, pageoneformula.com)
- **Screen readers:** support **VoiceOver (iOS)** and **TalkBack (Android)**; they use swipe-to-navigate + double-tap-to-activate. Provide semantic structure, ARIA roles/labels on composer, send, attach, message actions; ensure streaming messages announce updates appropriately (e.g., polite live region, not spammy). **[Verified]** (corpowid.ai)
- **Dynamic type / text resizing:** respect **iOS Dynamic Type** and **Android `sp`** scaling; use relative units (`rem`) and avoid fixed pixel text so user font-size preferences are honored. **[Verified]** (corpowid.ai)
- **Contrast:** meet WCAG contrast ratios (4.5:1 body text); also aids outdoor/glare readability. **[Verified]** (audioeye.com)
- **Gestures:** every gesture (swipe-to-delete, long-press menu) must have a **non-gesture alternative** for motor-impaired users. **[Verified]** (universaldesign.ie)
- **Reduced motion:** honor `prefers-reduced-motion` for streaming animations/transitions. **[Recalled]**

---

## 13. Recommended cross-platform strategy (MVP vs later)

### 13.1 MVP — Responsive web app + PWA layer

**Ship one responsive web app, progressively enhanced into a PWA.** Rationale: fastest to market, single codebase, universal reach, instant updates, and it satisfies the "mobile-web-first" mandate while giving Android users a near-native installed experience. **[Verified]** (weweb.io, dev.to PWA-to-native)

Concretely, the MVP includes:
- Fluid layout + adaptive shell (§2 pane model).
- Mobile composer done right: `dvh` + `interactive-widget=resizes-content` + safe-area insets; explicit Send button; auto-grow textarea (§4).
- Virtualized message list (Virtuoso/TanStack Virtual) + smart auto-scroll + scroll-to-bottom button (§5, §8).
- Optimistic send + IndexedDB drafts/queue + retry with backoff (§7).
- PWA manifest + service worker (app-shell cache) + web push **on Android** + custom iOS "Add to Home Screen" coachmark (§6).
- Accessibility baselines (44–48px targets, screen-reader labels, dynamic type, contrast) (§12).
- Voice via Web Speech API as a **progressive enhancement** (with the iOS-PWA caveat surfaced).

### 13.2 Later — Capacitor native wrapper (when triggered)

**Add a Capacitor wrapper** to ship to the App Store / Play Store with native push (APNs), reliable offline, share extensions, and camera — reusing ~100% of the web/PWA codebase. **[Verified]** (nextnative.dev)

**Triggers to go native:**
1. iOS push-driven re-engagement becomes a core KPI (web push on iOS is too weak). **[Verified]**
2. App-store presence/discoverability is required for the business.
3. Need durable offline / large local storage beyond iOS PWA's ~50 MB / 7-day limits. **[Verified]**
4. Need native share-target, deeper camera/file integration, or device APIs. **[Verified/Recalled]**

**Tradeoffs of going native:** App Store 4.2 review risk (must add native value beyond a web wrapper) and 5.1.2 AI-data-disclosure obligations; ongoing native build/release pipeline overhead. **[Verified]** (iossubmissionguide.com, openforge.io)

**Why not React Native?** It would require **rewriting the entire UI** with no meaningful performance benefit for a chat app, defeating the single-codebase advantage. Choose RN only if native fidelity becomes non-negotiable. **[Verified]** (nextnative.dev)

**Why not Tauri (for mobile)?** Mobile maturity lags Capacitor; better suited to a future *desktop* installable build. **[Verified, brief]**

### 13.3 Recommended responsive breakpoints & layout rules

> **[Recalled defaults, aligned with verified guidance]** — validate exact px values with real content + device lab. Browserstack/UXPin note 2025 breakpoints are device-class ranges, not fixed magic numbers.

| Breakpoint | Range | Layout rule |
|---|---|---|
| **Mobile (S/M)** | `< 768px` | Single pane: chat only. History = temporary **overlay drawer** (hamburger, top-left). Tools/attach = **bottom sheet**. Artifact opens **full-screen** or bottom sheet. Composer pinned bottom with safe-area + `dvh`. |
| **Tablet** | `768–1023px` | Chat full-width with **dismissible/persistent drawer** for history (push or overlay — decide via prototype). Artifact opens as **overlay** or replaces chat. |
| **Desktop (S)** | `1024–1439px` | **2-pane:** permanent sidebar + chat. Artifact panel slides in as a 3rd column (chat narrows) when invoked. |
| **Desktop (L)** | `>= 1440px` | **3-pane comfortable:** sidebar + chat + artifact panel coexist; max content width on the chat column for readability. |

**Cross-cutting layout rules:**
- Use `dvh`/`svh`/`lvh` (not raw `vh`) for full-height surfaces; `100vh` only as legacy iOS fallback. **[Verified]**
- Reserve space (avoid CLS) for streaming content, images (`srcset`+dimensions), and the composer. **[Verified]**
- One source of truth for the layout shell (container queries or a breakpoint hook) so panes/drawer derive from the same state.
- Chat reading column capped (~`70–80ch`) on wide screens for legibility. **[Recalled]**
- Tap targets 44–48px; thumb-zone placement for primary actions. **[Verified]**

---

## 14. Open questions & uncertainties

1. **Competitive teardown of Claude & Perplexity mobile** was not directly verified this pass (Gemini/ChatGPT were). Confirm their exact drawer/tab/bottom-sheet patterns and artifact handling. **[Recalled -> verify]**
2. **Web Share Target current iOS status** — assumed weak/Chromium-first; confirm before committing to share-to-AI on mobile web. **[Recalled -> verify]**
3. **Exact breakpoint px values** and tablet drawer behavior (push vs overlay) need prototype validation with real content. **[Recalled]**
4. **iOS keyboard edge cases** (composer float/cover on specific iOS versions) require a real-device lab; `dvh` improves but does not fully guarantee. **[Verified risk; needs device testing]**
5. **Virtualization + streaming + variable heights + auto-scroll** interaction is the top technical risk in the message list; needs a spike. **[Recalled]**
6. **Google Play PWA policy specifics** (TWA path, current rules) not re-verified. **[Recalled -> verify]**
7. **Send-vs-newline on mobile** default is industry-standard but should be A/B validated and made configurable. **[Recalled]**
8. **EU iOS PWA push restriction** (17.4+) — confirm current 2026 status, as Apple's EU policy has been in flux. **[Verified as of cited sources; revalidate]**

---

## 15. Sources

**Layout / responsive**
- How to Build a Responsive Web App in 2026 — https://www.weweb.io/blog/how-to-build-a-responsive-web-app-guide
- Streamlined layout design (Justinmind) — https://www.justinmind.com/ui-design/layout-website-mobile-apps
- React MUI Drawer responsive sidebar (Kombai) — https://kombai.com/mui/drawer/
- Side Drawer UI Design (DesignMonks) — https://www.designmonks.co/blog/side-drawer-ui
- Breakpoints for Responsive Web Design in 2025 (BrowserStack) — https://www.browserstack.com/guide/responsive-design-breakpoints
- Responsive Design Best Practices (UXPin) — https://www.uxpin.com/studio/blog/best-practices-examples-of-excellent-responsive-design/
- Ultimate Chat App Design Guide (Contus) — https://www.contus.com/blog/chat-ui-implemtation/

**Leading AI apps / navigation**
- Gemini Android UI overhaul (Gadget Hacks) — https://android.gadgethacks.com/news/google-gemini-android-app-gets-major-ui-overhaul/
- Bottom navigation bar 2025 guide (AppMySite) — https://blog.appmysite.com/bottom-navigation-bar-in-mobile-apps-heres-all-you-need-to-know/
- Mobile Navigation Patterns Pros/Cons (UXPin) — https://www.uxpin.com/studio/blog/mobile-navigation-patterns-pros-and-cons/
- End of Hamburger Menus (Simanta Parida) — https://www.simantaparida.com/blog/end-of-hamburger-menus-mobile-navigation
- Hamburger Menu Design (Lollypop) — https://lollypop.design/blog/2025/december/hamburger-menu-design/
- Navigation types for no-code apps (AppInstitute) — https://appinstitute.com/navigation-types-no-code-mobile-apps/

**Composer / keyboard**
- Fix mobile keyboard overlap with dvh (Francisco Moretti) — https://www.franciscomoretti.com/blog/fix-mobile-keyboard-overlap-with-visualviewport
- VirtualKeyboard API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/VirtualKeyboard_API
- Prevent content hidden under virtual keyboard (Bram.us) — https://www.bram.us/2021/09/13/prevent-items-from-being-hidden-underneath-the-virtualkeyboard-by-means-of-the-virtualkeyboard-api/
- The virtual keyboard API (Ishadeed) — https://ishadeed.com/article/virtual-keyboard-api/
- iOS keyboard behavior (AzimoLabs/Medium) — https://medium.com/azimolabs/how-to-handle-keyboard-behavior-in-ios-apps-3098a8c5411a
- Stick element to bottom of viewport on mobile (DEV) — https://dev.to/vladimirschneider/how-stick-element-to-bottom-of-viewport-on-mobile-1pg6

**Touch / gestures**
- Implementing Touch-Friendly Elements (Page One Formula) — https://pageoneformula.com/implementing-touch-friendly-elements/
- Designing Touch Responsive Interfaces (MoldStud) — https://moldstud.com/articles/p-designing-touch-responsive-interfaces-for-mobile-devices-best-practices-tips
- Impact of Gestures on Mobile UX (Codebridge) — https://www.codebridge.tech/articles/the-impact-of-gestures-on-mobile-user-experience
- Designing for Touch (Devoq/Medium) — https://devoq.medium.com/designing-for-touch-mobile-ui-ux-best-practices-c0c71aa615ee
- Use simple mobile gestures (Centre for Excellence in Universal Design) — https://universaldesign.ie/communications-digital/web-and-mobile-accessibility/web-accessibility-techniques/developers-introduction-and-index/design-accessible-navigation/use-simple-mobile-gestures-for-interaction

**Virtualization / streaming scroll**
- VirtualizedMessageList (GetStream) — https://getstream.io/chat/docs/sdk/react/components/core-components/virtualized_list/
- Windowing and Virtualization (Steve Kinney) — https://stevekinney.com/courses/react-performance/windowing-and-virtualization
- Streaming chat scroll to bottom with React (Dave Lage) — https://davelage.com/posts/chat-scroll-react/
- Virtualization in React (Frontend Highlights/Medium) — https://medium.com/@ignatovich.dm/virtualization-in-react-improving-performance-for-large-lists-3df0800022ef

**Offline / sync**
- Offline-first frontend apps in 2025 (LogRocket) — https://blog.logrocket.com/offline-first-frontend-apps-2025-indexeddb-sqlite/
- State Management for Offline-First (PixelFreeStudio) — https://blog.pixelfreestudio.com/state-management-for-offline-first-web-applications/
- Offline-First Sync Patterns (Developers Voice) — https://developersvoice.com/blog/mobile/offline-first-sync-patterns/
- Using IndexedDB for Offline-First (DEV/hexshift) — https://dev.to/hexshift/using-indexeddb-for-offline-first-web-applications-33o0
- Advanced PWA features (Rishi Kumar Chawda) — https://rishikc.com/articles/advanced-pwa-features-offline-push-background-sync/

**Performance / CWV**
- Web Vitals (web.dev) — https://web.dev/articles/vitals
- Core Web Vitals explained 2026 — https://www.corewebvitals.io/core-web-vitals
- Core Web Vitals optimization guide 2025 (aTeam) — https://www.ateamsoftsolutions.com/core-web-vitals-optimization-guide-2025-showing-lcp-inp-cls-metrics-and-performance-improvement-strategies-for-web-applications/

**Voice / camera / share**
- Web Speech API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- Using the Web Speech API (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API
- Speech Recognition PWA capability (Progressier) — https://progressier.com/pwa-capabilities/speech-recognition

**PWA / iOS limits / delivery**
- PWA iOS Limitations & Safari Support (MagicBell) — https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide
- PWA on iOS current status (Brainhub) — https://brainhub.eu/library/pwa-on-ios
- Do PWAs work on iOS 2026 (MobiLoud) — https://www.mobiloud.com/blog/progressive-web-apps-ios
- Using Push Notifications in PWAs (MagicBell) — https://www.magicbell.com/blog/using-push-notifications-in-pwas
- From PWA to Native App (DEV) — https://dev.to/okoye_ndidiamaka_5e3b7d30/from-pwa-to-native-app-how-to-turn-your-progressive-web-app-into-a-full-fledged-mobile-experience-200i

**Native frameworks**
- Capacitor vs React Native 2025 (NextNative) — https://nextnative.dev/blog/capacitor-vs-react-native
- React Native vs Expo vs Capacitor 2026 (PkgPulse) — https://www.pkgpulse.com/guides/react-native-vs-expo-vs-capacitor-cross-platform-mobile-2026
- React Native vs Tauri vs Capacitor 2025 (dulitharw, X) — https://x.com/dulitharw/status/1945559061329760458

**App store**
- Guideline 4.2 Minimum Functionality — https://iossubmissionguide.com/guideline-4-2-minimum-functionality/
- App Store Review Guidelines: Webview wrapper (MobiLoud) — https://www.mobiloud.com/blog/app-store-review-guidelines-webview-wrapper
- Publishing a PWA to App Store / Play 2026 (MobiLoud) — https://www.mobiloud.com/blog/publishing-pwa-app-store
- App Store Review Guidelines 2025: AI App Rules (OpenForge) — https://openforge.io/app-store-review-guidelines-2025-essential-ai-app-rules/

**Accessibility**
- WCAG2Mobile-22 (W3C) — https://www.w3.org/TR/wcag2mobile-22/
- Mobile App Accessibility Guide 2026 (Corpowid) — https://corpowid.ai/blog/mobile-application-accessibility-practical-humancentered-guide-android-ios
- WCAG 2.2 Mobile App Accessibility (AdaTray) — https://www.adatray.com/blog/wcag-2-2-mobile-app-accessibility
- WCAG 2.2 Explained (AudioEye) — https://www.audioeye.com/post/wcag-22/
