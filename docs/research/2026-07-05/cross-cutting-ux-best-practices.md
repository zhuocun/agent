# Findings Memo — Cross-cutting UX Best Practices (Accessibility, Performance, Trust/Privacy/Safety)

**Worker:** R2 (cross-cutting UX best practices).
**Date:** 2026-07-05.
**Status:** Research findings only — no docs edited (nothing under `docs/ux-best-practices/` touched).
**Scope:** (a) Accessibility (WCAG 2.2 AA, streaming live-region model, keyboard nav & shortcuts dialog, focus management, landmarks, contrast tokens, reduced motion, SR behavior for tool/agentic parts); (b) Performance (INP protection, rAF token-batching + `scheduler.yield()`, list virtualization, skeleton/loading, perceived-latency, cold-start bounding); (c) Trust/privacy/safety (EU AI Act Art. 50(1) AI-interaction disclosure, no-train framing, content provenance, hallucination/uncertainty cues, safe error handling).
**Grounded in:** PRD 06 §3.1/§3.4/§3.5/§5, PRD 08 §9, `docs/design/00-principles.md`, `docs/design/01-foundations.md`, `docs/research/2026-05-27/00-synthesis.md` §4, and `web/src/app/globals.css` (plus a ground-truth read of the shipped `web/src` implementation).

> **How to read this.** Three sections, same structure as R1: **§1 Best practices** (authoritative external guidance), **§2 Repo coverage** (what the repo already does, verified against source, and where it diverges), **§3 Gaps & recommendations** (prioritized, on-wedge, cheap-first). Accessibility is our stated differentiation wedge (synthesis §1 W1), so it leads.

---

## 1. Best practices (authoritative)

### (a) Accessibility

**A1 — WCAG 2.2 AA is the target; six new A/AA criteria matter for a chat surface.** WCAG 2.2 adds nine criteria and removes 4.1.1 Parsing. The AA/A additions that bind a streaming chat UI:
- **2.4.11 Focus Not Obscured (Minimum) — AA.** A keyboard-focused component must not be *entirely* hidden by author content (sticky headers, the floating composer/chrome, cookie/consent layers). Practically: `scroll-margin` on focus targets and ensuring focus is never parked behind the glass chrome strips. [W3C new-in-22; W3C Understanding 2.4.11]
- **2.5.7 Dragging Movements — AA.** Any drag interaction needs a single-pointer (tap/click) alternative unless dragging is essential. Relevant to sidebar swipe actions, swipe-to-dismiss sheets, and any reorder/bulk-select gesture. [W3C Understanding 2.5.7 (F108)]
- **2.5.8 Target Size (Minimum) — AA.** Pointer targets ≥ **24×24 CSS px** (bounding box incl. spacing), with an explicit *Spacing* exception (a 24px-diameter circle centered on each undersized target must not intersect a neighbor). Note this is the *floor*; the product's own 44–48px mobile target rule (PRD 06 §5.2) is stricter and satisfies it. [W3C Understanding 2.5.8; Vispero]
- **3.3.8 Accessible Authentication (Minimum) — AA.** Don't block paste into auth fields; support password managers; no cognitive-function test without an alternative. Applies to the sign-up/sign-in wall (`auth-dialog.tsx`). [WCAG 2.2 checklist]
- **3.2.6 Consistent Help — A** and **3.3.7 Redundant Entry — A.** Help/entry-points ordered consistently; don't re-ask for info already provided in a session. [Vispero; W3C]

The product currently declares "WCAG 2.1 AA (stretch 2.2 AA where cheap)" (PRD 06 §2). Most of the 2.2 delta *is* cheap here and should be treated as in-scope, not stretch.

**A2 — Streaming live-region announce model (the highest-value fix, per synthesis §1 W1).** Authoritative model:
- Use a **single, separate polite status region** (`role="status"`, which carries implicit `aria-live="polite"` **and** `aria-atomic="true"`) for discrete generation-status transitions. [W3C ARIA22; MDN Live regions]
- **The streamed message body must NOT be a live region.** Live regions announce *every* mutation; wrapping token-by-token streamed text causes continuous re-announcement/re-reading on NVDA/JAWS and is a documented anti-pattern ("use live regions sparingly," they "become distracting"). The completed body stays navigable but is not auto-announced. [MDN Live regions; OpenA11y rule-live-1]
- Announce **discrete transitions only**: "Generating", success-path "Response ready" (**once**), "Stopped". Start the region **empty** and inject text after it is in the DOM (AT won't announce content present before the region is parsed). [MDN; W3C ARIA22]
- Reserve `role="alert"` (implicit `aria-live="assertive"` + atomic) for content that needs immediate attention (blocking errors), not routine warnings — warnings use `role="status"`. Avoid combining `role="alert"` with an explicit `aria-live` (double-speak on iOS VoiceOver). [MDN; PRD 08 §9]

**A3 — Keyboard navigation, a shortcuts dialog, focus management, landmarks (the two cheap "beat-the-leader" ACs).**
- Ship an accessible **keyboard-shortcuts dialog**: focus-trapped, SR-navigable, restores focus to the invoking control on close. Modal dialogs follow the APG dialog pattern (trap focus, `Esc` closes, return focus). [WAI-ARIA APG dialog pattern]
- Expose **landmark regions** so SR users jump directly: `<nav>` for history/sidebar (labeled), `<main>` for the thread, `<header>` for chrome. Named landmarks are the fastest SR navigation path. [WAI-ARIA APG landmarks]
- All **icon-only controls need accessible names** (PRD 06 §5.1/§7.5); icons decorative-only are `aria-hidden`.

**A4 — Screen-reader behavior for tool/agentic parts.** Reasoning panels, tool calls, and sub-agent parts are *progressive-disclosure* surfaces: render them as labeled, collapsible regions (button + `aria-expanded`), not as live regions that announce every intermediate tool token. Announce only meaningful state changes ("Ran web search", "Sub-agent(s) failed and were omitted") through the same polite status region, consistent with PRD 08 §5.4's inline degrade prose. Decorative color/emoji on project rows must be `aria-hidden` and never the sole identifier (PRD 06 §5.10).

**A5 — Contrast tokens, reduced motion, and the environment-preference family.** Body text ≥ **4.5:1**, large text/UI ≥ **3:1** (WCAG 1.4.3/1.4.11). State must never be color-alone (WCAG 1.4.1) — pair glyph/text with color (the JSON-validity chip and read-aloud state already do this per PRD 06 §5.4/§5.1). Honor `prefers-reduced-motion`, `prefers-reduced-transparency`, `prefers-contrast: more`, and `forced-colors` as first-class *designed* paths, not blanket kill-switches — each animated affordance needs a deliberate static alternate. [Apple HIG Motion; W3C; foundations §Motion]

### (b) Performance

**P1 — INP is the binding Core Web Vital; protect it.** 2026 thresholds (unchanged, p75 field data): **LCP ≤ 2.5s, INP ≤ 200ms, CLS ≤ 0.1**. INP is the hardest to pass and the most relevant to a keystroke-heavy composer + streaming surface. Any task > **50ms** is a "long task." [web.dev Web Vitals; corewebvitals.io]

**P2 — rAF token-batching + `scheduler.yield()` is the named streaming mechanism (synthesis §4, cross-cutting #4).** Buffer streamed tokens in a ref and flush **once per `requestAnimationFrame`** (never per-token React state updates), and **yield to the main thread** during long synchronous handlers so input/paint can interleave. Prefer `scheduler.yield()` — its continuation is *prioritized* ahead of other queued tasks, so work resumes promptly without starving input; fall back to a `MessageChannel` macrotask (more reliable than `setTimeout(0)`, which browsers clamp to ~4ms). Yield roughly every 50ms in long loops. `scheduler.yield()` shipped stable in Chrome 129 (Sep 2024); Safari lacks it → the fallback is mandatory. [Chrome for Developers; web.dev Optimize long tasks; MDN Prioritized Task Scheduling API]

**P3 — List virtualization for long threads.** Long chats accumulate hundreds of rich markdown bubbles; render only the visible window + overscan to keep scroll/INP healthy. Complement (not replace) with CSS `content-visibility: auto` + `contain-intrinsic-size` for off-screen rows so the browser skips their layout/paint. Virtualized message lists must preserve SR access and stable scroll-anchoring. [web.dev; MDN content-visibility]

**P4 — Skeleton/loading, perceived latency.** Show a pre-first-token skeleton/typing indicator quickly (PRD 06 §5.2: within 150ms) so the wait reads as "working," not "broken." Skeletons should approximate final layout to avoid CLS. Optimistic send (echo the user turn instantly) and streaming itself are the primary perceived-latency levers. Reduced-motion collapses shimmer to a static block.

**P5 — Cold-start bounding.** A serverless/scale-to-zero backend can cold-boot 5–20s; the client must **bound** the first-paint bootstrap fetch with a timeout that surfaces a retry rather than an unbounded spinner (`BOOTSTRAP_TIMEOUT_MS`, AGENTS.md "Debugging in production" #1), and keep a warm machine (`min_machines_running=1`).

### (c) Trust / privacy / safety

**T1 — AI-interaction disclosure is a firm legal obligation (EU AI Act Art. 50(1)).** From **2 Aug 2026**, providers of AI systems "intended to interact directly with natural persons" must design them so users **are informed they are interacting with an AI system**, unless obvious to a reasonably well-informed, observant, circumspect person. Chatbots/AI assistants are explicitly in-scope; the "obviousness" exemption is narrow and context-specific (draft Guidelines cite dev-only code assistants and game NPCs as exempt — a general consumer chat product should **not** rely on it). Art. 50(5): the disclosure must be **clear and distinguishable, at the latest at the first interaction**, and **conform to accessibility requirements**. Build the disclosure hook as unconditional P0 (synthesis §3). [aiact-info.eu Art. 50; Sidley; Mishcon; W3C]

**T2 — No-train framing is a *live* differentiator, not parity (synthesis §2).** Incumbents now train on consumer chats by default (opt-out); a no-train-by-default consumer/prosumer posture is genuinely ahead of incumbent *consumer defaults*. Framing rules: state the default plainly ("your conversations are never used to train models unless you turn this on"); surface per-route data policy (`trainingDefault: never|opt_in|opt_out|unknown`, retention, residency); don't over-claim gateway ZDR as a baseline (it's Pro/Enterprise-only and metered — rest the wedge on provider DPAs/API no-train modes).

**T3 — Content provenance (Art. 50(2), narrow for P0 text).** When/if the product emits synthetic **media**, Art. 50(2) requires machine-readable marking so content is detectable as AI-generated (the C2PA / Content Credentials family is the emerging standard), plus a visible "AI-generated" affordance announced to SRs. For a P0 text-relay-with-attribution product this is narrow, but the provenance badge should be designed to attach to any future media-gen and be retained on public share while cost/tokens are stripped (PRD 06 §5.4 P2; PRD 07 §6.4). The Art. 50(2) *date* is unresolved and a legal call (synthesis §3) — do not let engineering decide it.

**T4 — Hallucination / uncertainty cues and honest attribution.** Transparency is product chrome here: always show served model/tier/provider without hover; render forced substitutions as a calm `substitution-callout` (never error-red); mark structured-output validity in text+glyph; surface citations/sources so claims are checkable. A general "AI can make mistakes — verify important info" cue is standard practice and complements Art. 50(1) disclosure. Never silently downgrade the model or silently edit/block content — always surface a visible reason and recourse (PRD 08 §5.4/§5.6.1).

**T5 — Safe handling of errors (PRD 08).** Lead with the outcome before the cause; keep counts/reset in structured `meta` (i18n/live countdown), not baked into copy; offer 2–3 actions; never blame the user for provider failures; preserve partial output; warnings use `role="status"`, blocking errors `role="alert"`; all recovery actions keyboard-operable; offline/queued status visible and announced. [PRD 08 §6/§9]

---

## 2. Repo coverage (verified against `web/src`)

**Strong / matches best practice:**
- **Live-region model (A2): fully correct.** `web/src/components/chat/live-region.tsx` renders a single `role="status" aria-live="polite" aria-atomic="true" sr-only` region; `chat-thread.tsx` drives it with discrete strings ("Generating response", "Response ready") — the streamed body is *not* wrapped in a live region. It even handles the identical-message re-announce edge (zero-width-space toggle). This is exactly the authoritative pattern.
- **`scheduler.yield()` (P2): correct and defensive.** `web/src/lib/scheduler-yield.ts` prefers `scheduler.yield()`, falls back to `MessageChannel`, then `setTimeout(0)`, SSR-safe, and swallows detached-document rejections — matches the Chrome/MDN reference pattern.
- **Virtualization + content-visibility (P3): shipped.** `message-list.tsx` + `use-virtual-message-window` virtualize past 80 messages (overscan, role-specific size estimates); `globals.css` adds `.chat-message-row { content-visibility: auto; contain-intrinsic-size … }` with per-role fallbacks and a print-mode override.
- **Reduced-motion & environment prefs (A5): exemplary.** `globals.css` implements a *designed parallel surface* for `prefers-reduced-motion` (per-affordance static alternates, explicitly rejecting the universal `animation:none` kill-switch), plus `prefers-reduced-transparency`, `prefers-contrast: more` (zeros welcome/hero atmosphere; densifies glass), and `forced-colors` (restores real borders). Contrast tokens are semantic OKLCH with a low-chroma ceiling and a dedicated `--destructive-text` split so error copy clears AA on both canvases.
- **Landmarks (A3): present.** `<nav aria-label="Sidebar">` (`sidebar.tsx`), `<main>` (`app-shell.tsx`, status/share views), `<aside>` for the rail, `aria-label` on icon-only menu triggers.
- **Shortcuts dialog (A3): shipped** (`shortcuts-dialog.tsx`, rebindable rows, hosted both standalone and in Settings) with a command palette (`command-palette.tsx`).
- **State-not-by-color-alone (A5) + calm substitution (T4):** JSON-validity chip and read-aloud state read in text+glyph (PRD 06 §5.4/§5.1); `substitution-callout` token is distinct from `destructive`.
- **No-train framing (T2): shipped, privacy-first.** `UserPreferences.trainingOptIn` defaults **false**; settings copy "Your conversations are never used to train models unless this is on"; `model-directory-dialog.tsx` renders per-route training policy; `types.ts` carries `trainingDefault`/`dataResidency`.
- **Safe error handling (T5): shipped** per PRD 08 (`degraded-status-banner.tsx`, structured `meta`, `platform-status-view.tsx`, moderation transparency/appeal).

**Partial / worth confirming:**
- **"Stopped" status announcement (A2):** PRD 06 §3.5 lists "Stopped" as one of the discrete transitions the polite region should announce, but the shipped `setLiveMessage(...)` calls I found only cover "Generating response" and "Response ready" — a Stopped turn renders a visual `StoppedChip` (`assistant-message.tsx`) but may not push a live announcement. Verify and, if absent, announce "Stopped" once through the same region.
- **WCAG 2.2 target size (A1):** mobile primary controls are speced ≥44px (PRD 06 §5.2, exceeds the 24px AA floor), but there is no systematic audit that *all* interactive targets (e.g. small footer-action icons, chips) meet 24×24 or the spacing exception. Worth an automated size sweep.
- **Focus Not Obscured (A1):** the floating glass header/composer chrome overlays the scroll region; confirm that keyboard focus on the first/last message and composer controls is never fully hidden behind the chrome strips (needs `scroll-margin`/`scroll-padding` verification).

**Apparent gaps:**
- **Persistent AI-interaction disclosure (T1):** PRD 06 §5.8 specs a "Persistent AI-interaction disclosure" and synthesis §3 calls the Art. 50(1) hook a firm P0, but a text search of `web/src` (welcome screen, composer, header) found **no rendered "you're interacting with an AI" / "AI can make mistakes" disclosure string**. This looks unshipped. (Caveat: I searched common phrasings; a differently-worded surface could exist — confirm before acting.)
- **Content provenance badge (T3):** P2 by roadmap (PRD 06 §5.4), not shipped — expected, but the marking-standard field + visible affordance should be designed now so it can attach to any future media-gen.

---

## 3. Gaps & recommendations (prioritized)

**P0 — correctness / on-wedge / cheap:**
1. **Ship the persistent AI-interaction disclosure (T1).** A clear, distinguishable, accessible disclosure present at first interaction (e.g., a quiet one-line note on the welcome/empty state and/or a persistent, unobtrusive chrome affordance). Legal floor for EU users from 2 Aug 2026; also reinforces the transparency wedge. Design it accessibility-conformant (Art. 50(5)).
2. **Announce "Stopped" through the polite region (A2).** Close the one missing discrete transition so the announce model matches PRD 06 §3.5 exactly.
3. **Treat WCAG 2.2 AA as in-scope, not stretch (A1).** Add ACs for 2.4.11 (focus never fully obscured by chrome), 2.5.7 (single-pointer alternative for every swipe/drag action), 2.5.8 (24×24 min or spacing exception on all targets), 3.3.8 (paste/password-manager-friendly auth). Most are cheap given existing 44px mobile targets and reduced-motion discipline.
4. **Keep the rAF-batch + `scheduler.yield()` mechanism as the enforced streaming contract (P2)** behind the 60fps/INP target, and add an INP budget (p75 ≤ 200ms) to the perf runbook. The helper already exists; ensure the token renderer flushes per-rAF (not per-token state) everywhere.

**P1 — strengthen:**
5. **Add a general uncertainty cue (T4)** ("AI can make mistakes — verify important info") near the composer/first turn, complementing per-turn attribution and substitution callouts.
6. **Automated a11y sweeps in CI:** axe-class checks (already an AC in PRD 06 §7.4) plus a target-size measurement pass and a landmark/focus-order snapshot, so 2.2 conformance doesn't regress.
7. **Cold-start UX (P5):** confirm `BOOTSTRAP_TIMEOUT_MS` surfaces a retry (not an infinite spinner) and that skeletons approximate final layout to hold CLS ≤ 0.1.

**P2 — design-ahead:**
8. **Provenance (T3):** design the C2PA/Content-Credentials-backed "AI-generated" badge + structured marking field now (retained on share, cost/tokens stripped), ready to attach when media-gen ships. Route the Art. 50(2) *date* to legal (synthesis §3), not engineering.

---

## Sources (accessed 2026-07-05)

- W3C WAI — *What's New in WCAG 2.2* — https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/
- W3C — *Understanding SC 2.5.7 Dragging Movements* — https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements
- W3C — *Understanding SC 2.5.8 Target Size (Minimum)* (via new-in-22) and Vispero, *New Success Criteria in WCAG 2.2* — https://vispero.com/resources/new-success-criteria-in-wcag22/
- W3C — *ARIA22: Using role=status to present status messages* — https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA22.html
- MDN — *ARIA live regions* — https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions
- WAI-ARIA Authoring Practices Guide (APG) — dialog (modal) and landmark patterns — https://www.w3.org/WAI/ARIA/apg/
- web.dev — *Web Vitals* (LCP/INP/CLS thresholds) — https://web.dev/articles/vitals
- web.dev — *Optimize long tasks* — https://web.dev/articles/optimize-long-tasks
- Chrome for Developers — *Use scheduler.yield() to break up long tasks* — https://developer.chrome.com/blog/use-scheduler-yield
- MDN — *Prioritized Task Scheduling API* — https://developer.mozilla.org/en-US/docs/Web/API/Prioritized_Task_Scheduling_API
- MDN — *content-visibility* — https://developer.mozilla.org/en-US/docs/Web/CSS/content-visibility
- EU AI Act, Article 50 (transparency obligations) — https://www.aiact-info.eu/regulation/AIACT/article/50/transparency-obligations-for-providers-and-deployers-of-certain-ai-systems
- Sidley Data Matters — *EU AI Act Transparency Obligations: Preparing for Compliance by 2 August 2026* — https://datamatters.sidley.com/2026/06/24/eu-ai-act-transparency-obligations-preparing-for-compliance-by-2-august-2026/
- Mishcon de Reya — *AI Act transparency obligations: Code of Practice and draft Guidelines* — https://www.mishcon.com/news/ai-act-transparency-obligations-code-of-practice-and-draft-guidelines
- C2PA / Content Credentials — content provenance / machine-readable marking (Art. 50(2) alignment) — https://c2pa.org/
