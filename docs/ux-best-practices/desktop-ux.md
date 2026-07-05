# UX Best Practices — Desktop

**Owner:** Product/UX (Best-Practices canon)
**Status:** Draft for build
**Date:** 2026-07-05
**Scope:** Desktop pointer/keyboard surface of the transparent, multi-model AI chat product. Best-practice guidance + gap callouts, grounded in the 2026-07-05 research pass (R1–R5).
**Companion:** [mobile-ux.md](./mobile-ux.md) — identical taxonomy, touch/PWA surface.
**Related canon:** [PRD 01 Core Chat](../prd/01-core-chat-experience.md) · [PRD 02 AI Capabilities](../prd/02-ai-capabilities.md) · [PRD 03 Mobile](../prd/03-mobile-cross-platform.md) · [PRD 06 Design System](../prd/06-design-system-visual-spec.md) · [PRD 07 Transparency](../prd/07-transparency-contract.md) · [PRD 08 Error/Limit](../prd/08-error-and-limit-states.md) · [Design principles](../design/00-principles.md).

> **How to read.** Each section states the 2026 best practice (external, cited by `C#`), then the repo's stance: ✅ covered (link canon, don't restate) · ◑ partial · ✗ gap · ➕ opportunity. Items are ordered gaps-first. `[verify-at-build]` marks facts to re-check at build. This doc is guidance, not an implementation contract — the PRDs own the spec.

---

## 1. Purpose, scope & how to read

**Best practice.** Desktop surfaces for AI chat products should optimize for keyboard efficiency, information density on wide viewports, and hover-enhanced discoverability — without making hover the sole path to any action. [C46][C48]

**Repo stance.**

- **Treat this doc as the desktop companion to [mobile-ux.md](./mobile-ux.md).** Shared semantics (streaming, transparency, agentic) must read identically in both; desktop-only accelerators live in §13.
- **Link to PRDs for values; use this doc for rationale and review checklists.** — ✅ see [README](./README.md) canonical position.
- **When a desktop accelerator exists (shortcut, right-click), mirror it in a visible menu.** — ✅ partial; shortcuts ship, right-click context menu does not (§13 D4).

---

## 2. Chat surface — composer, rendering & streaming

**Best practice.** A desktop chat composer should bind Enter to send and Shift+Enter to newline; stream tokens with rAF batching and main-thread yielding; never wrap streamed text in a live region; and cap reading measure on wide screens. [C37][C38][C35][C65]

**Repo stance.**

- **Bind Enter to send and Shift+Enter to newline on desktop; auto-grow the textarea to a max height, then scroll.** — ✅ [PRD 01 §4.3](../prd/01-core-chat-experience.md).
- **Morph Send into Stop in the same slot during generation; style Stop neutrally, never destructive-red.** — ✅ [Design patterns](../design/02-patterns.md); [anti-patterns](../design/03-anti-patterns.md).
- **Buffer streamed tokens in a ref and flush once per `requestAnimationFrame`; yield via `scheduler.yield()` with MessageChannel fallback.** — ✅ [PRD 01 §5.4](../prd/01-core-chat-experience.md); helper in `web/src/lib/scheduler-yield.ts`. [C38][C39][C40]
- **Do not wrap the streaming message body in `aria-live`; announce discrete status transitions via a separate polite region.** — ✅ `live-region.tsx` + `chat-thread.tsx`. [C34][C35]
- **Auto-follow the stream only when the user is at/near the bottom; otherwise show a "Jump to latest" affordance.** — ✅ [PRD 01 §5.1](../prd/01-core-chat-experience.md).
- **Cap the message column at ~70–80ch on wide viewports.** — ✅ [PRD 03 §5.3](../prd/03-mobile-cross-platform.md); [anti-patterns D](../design/03-anti-patterns.md).
- **Render streaming-safe markdown with allowlist sanitization (`rehype-harden`-class); syntax-highlight code progressively with copy-of-raw-source.** — ✅ [PRD 01 §4.4](../prd/01-core-chat-experience.md). [C65]
- **Surface inline mode toggles (web search, reasoning effort) in the composer toolbar, not hidden menus.** — ✅ `model-mode-picker.tsx`. [C69]
- **Ship paste-image and drag-and-drop attachment with a drop overlay when attachments are enabled.** — ◑ paperclip picker ships; paste/drag-drop not shipped. [C31]
- **Lead with answer-first layout where appropriate (TL;DR, then expandable detail).** — ◑ P1 experiment per research; peers ship by default. [C71]

**Platform note (Desktop).** Hover-reveal message action rows and sidebar row controls are acceptable enhancements when focus-visible parity exists for keyboard users.

---

## 3. Message actions, branching & sharing

**Best practice.** Message actions should be hover-revealed on desktop with focus-visible parity; support copy-as-markdown, regenerate-with-model-choice, edit-last-user-turn, thumbs feedback, and copy-on-branch without in-thread version trees at MVP. [C67]

**Repo stance.**

- **Reveal message actions on hover; ensure every action is keyboard-reachable with visible focus rings.** — ✅ [Design patterns D](../design/02-patterns.md).
- **Offer Copy (clean markdown), Regenerate (with tier menu), Edit-last-user-message, and thumbs up/down on every assistant turn.** — ✅ [PRD 01 §4.6](../prd/01-core-chat-experience.md).
- **Show per-message model/tier attribution at rest without hover.** — ✅ `attribution-row.tsx`; [PRD 07 §6.1](../prd/07-transparency-contract.md).
- **Render a visible substitution callout naming requested tier, served model, and reason — not only a "Rerouted" pill.** — ✗ gap vs [PRD 07 §6.1](../prd/07-transparency-contract.md); detail currently `aria-label`-only. [C26]
- **Provide "Branch in new chat" (copy-on-branch); defer in-thread alternate-response trees.** — ✅ [PRD 01 §4.6](../prd/01-core-chat-experience.md). [C67]
- **Generate unlisted, revocable share links; public shares show model attribution but strip cost and memory.** — ✅ [PRD 01 §4.10](../prd/01-core-chat-experience.md).
- **Offer copy-as-markdown and download-as-`.md` for conversations.** — ✅ shipped.

---

## 4. Conversation management & navigation

**Best practice.** Conversation history should live in a persistent sidebar with search, time grouping, pin/archive/delete, and a named navigation landmark; full-text search with transparency filters is the competitive baseline. [C36]

**Repo stance.**

- **Render a persistent sidebar (≥768px) with New Chat, reverse-chron list grouped by time, rename, delete-with-confirm, and pin.** — ✅ `sidebar.tsx`; [PRD 01 §4.5](../prd/01-core-chat-experience.md).
- **Expose sidebar search and `Cmd/Ctrl+K` palette search with title + content matches.** — ✅ `command-palette.tsx`.
- **Upgrade to Postgres FTS with filter chips (model, tier, cost, date, tag, project).** — ◑ substring search ships; FTS+filters net-new.
- **Expose the history sidebar as a labeled `<nav>` landmark.** — ✅ `sidebar.tsx` `aria-label="Sidebar"`. [C36]
- **Support archive, tags, and bulk multi-select (checkbox-on-hover on desktop).** — ◑ pin ships; archive/tags/bulk partial.
- **Auto-title from first exchange; allow user rename override.** — ✅ [PRD 01 §4.5](../prd/01-core-chat-experience.md).

**Platform note (Desktop).** Row controls may hide until hover; keyboard users must reach them via focus-visible or overflow menu.

---

## 5. Agentic & tool-use UX

**Best practice.** Agentic UIs should show decomposed plans before fan-out, gate high-risk tools with HITL approval cards that include cost estimates, render tool lifecycle states distinctly, coalesce settled tool runs, and expose Stop plus live run-cost during long fan-outs. [C1][C2][C4][C15]

**Repo stance.**

- **Render plan-approval as a numbered step list, not raw JSON.** — ✅ `tool-part.tsx` `PlanApprovalDetail`. [C1]
- **Show estimated cost + per-run cap inside the approval card.** — ✗ parsed but dropped in `tool-part.tsx`; gap vs [PRD 02 FR-26g](../prd/02-ai-capabilities.md). [C4][C5]
- **Support edit-then-approve on gated tools, not approve/deny only.** — ◑ approve/deny ships; edit path absent. [C2]
- **Render tool states (pending, running, awaiting-approval, succeeded, failed, cancelled) with distinct icons and labels.** — ✅ `tool-part.tsx`. [C6]
- **Auto-collapse settled tool runs; keep running and awaiting-approval expanded.** — ✅ `tool-part.tsx`, `tool-group-panel.tsx`. [C6]
- **Show per-worker rows in a dedicated activity panel with role and status.** — ✅ `subagent-panel.tsx`. [C7][C8]
- **Render a live per-run cost meter as `run_cost` SSE frames arrive.** — ✗ parsed in `stream-client.ts` but not rendered. [C11]
- **Attribute each subagent's served model when substitution occurs inside a fan-out.** — ✗ persisted but not displayed per worker. [C7]
- **Expose Stop during runs; retain partial output with a "Stopped" marker.** — ✅ `StoppedChip` in `assistant-message.tsx`. [C15]
- **Do not build a cross-session agent dashboard — orchestration is chat-anchored by design.** — ✅ intentional per [agentic plan](../plans/01-agentic-mode.md). [C14]

---

## 6. Grounding, web search & citations

**Best practice.** Grounded answers should use inline `[n]` markers mapped to source cards; desktop may add hover previews on markers; never render model-generated URLs as clickable sources. [C18][C19][C20]

**Repo stance.**

- **Bind inline `[n]` markers to structured source objects by stable ID; render source cards (favicon, title, domain, snippet).** — ◑ source-card list ships; inline `[n]` chips partial. [PRD 01 §4.11](../prd/01-core-chat-experience.md)
- **On desktop, reveal a hover preview (title + domain + snippet) on citation markers; open immediately on keyboard focus.** — ➕ opportunity. [C18][C22]
- **Clicking `[n]` scrolls to and highlights the matching source card.** — ✅ `sources-panel.tsx` `revealSource`.
- **Show "Answered without live sources" when search resolves zero usable sources.** — ✅ `assistant-message.tsx` `UngroundedMarker`.
- **Sanitize links to http(s) only; render non-http schemes as inert text.** — ✅ `sources-panel.tsx`.
- **Keep the source list collapsed at rest post-stream ("N sources").** — ✅ progressive disclosure.

**Platform note (Desktop).** Source cards may render in a right rail on wide screens; stack below the answer on narrow breakpoints.

---

## 7. Model selection & the transparency contract

**Best practice.** Model pickers should use plain-language tiers, show Auto's resolved route post-turn, surface data-policy badges, and never silently downgrade — substitution must name requested, served, and reason. [C23][C24][C26][C27]

**Repo stance.**

- **Place tier/model picker in the composer toolbar, reachable before send.** — ✅ `model-mode-picker.tsx`. [C23]
- **Present tiers as effort scale with concrete model as secondary meta.** — ✅ `tier-picker.tsx`. [C24]
- **Show served tier on every assistant message without hover; link to Spend hub for per-message cost (not inline in thread).** — ✅ Option B / D41 per [PRD 07 §6.1](../prd/07-transparency-contract.md).
- **Render substitution callout with requested tier, served model, and reason visible — not pill-only.** — ✗ gap; see §3.
- **Auto-open reasoning panel while streaming; collapse to "Thought for Xs" on complete; render nothing when no trace emitted.** — ✅ `reasoning-panel.tsx`. [C27][C28]
- **Label BYOK turns "billed to your key"; usage meter reflects BYOK branch.** — ✅ `attribution-row.tsx`, `usage-meter.tsx`.

---

## 8. Onboarding, guest, BYOK & settings

**Best practice.** Anonymous-first products should let guests chat immediately, surface upgrade at value moments (not upfront walls), never echo BYOK secrets, and organize settings in a grouped hub with privacy defaults prominent. [C42]

**Repo stance.**

- **Bootstrap anonymous session on first visit; upgrade guest→signed-in in place without losing history.** — ✅ `chat-thread.tsx` bootstrap flow.
- **Show welcome greeting with 3–4 prompt suggestion buttons (prefill composer, do not auto-send).** — ✅ `welcome-screen.tsx`.
- **Render persistent AI-interaction disclosure at first interaction (EU AI Act Art. 50(1)).** — ✗ no rendered disclosure string found in `web/src`. [C42][C43]
- **Never echo BYOK keys; use `type=password`, masked fingerprint, encrypted-server-side cue.** — ✅ `byok-form.tsx`.
- **Organize settings in a tabbed hub (General, Activity, Memory, Templates, Models, Shortcuts) with two-column layout on desktop.** — ✅ `settings-dialog.tsx`.
- **Default training opt-in to off; state plainly in settings copy.** — ✅ per [PRD 05](../prd/05-roadmap-monetization-metrics.md).

---

## 9. Billing, usage meters & limit states

**Best practice.** Usage meters should escalate tone before hard failure; limit errors should render inline with structured `actions[]` (Upgrade, Add credits, BYOK); offer plan comparison before Stripe checkout. [C26]

**Repo stance.**

- **Escalate usage meter at 80%/95%/100% thresholds; speak in USD when spend cap binds.** — ✅ `usage-meter.tsx`.
- **Render limit/quota errors inline in the thread with actionable buttons from `error.actions[]`.** — ✗ `ApiError.actions` carried but only surfaced via toast, not in-thread block. [PRD 08 §9](../prd/08-error-and-limit-states.md)
- **Show longitudinal spend in a dedicated analytics panel (Settings → Activity).** — ✅ `spend-analytics-panel.tsx`.
- **Offer hosted Stripe Checkout for Pro + credit packs; Customer Portal for management.** — ✅ settings billing section.
- **Show plan comparison before checkout, not redirect-only.** — ◑ checkout launches; comparison surface partial.

---

## 10. Accessibility

**Best practice.** Target WCAG 2.2 AA including 2.4.11 (focus not obscured), 2.5.7 (drag alternatives), 2.5.8 (24×24px target floor); use a single polite status region for streaming; trap focus in modals and restore on close. [C30][C31][C32][C34][C36]

**Repo stance.**

- **Use one `role="status"` polite atomic region for "Generating"/"Response ready"/"Stopped" — never the streamed body.** — ◑ "Stopped" may not be announced; verify. [C34][C35]
- **Ship keyboard-shortcuts dialog with focus trap and focus return to invoker.** — ✅ `shortcuts-dialog.tsx`. [C36]
- **Expose landmarks: `<nav>` sidebar, `<main>` thread, labeled header.** — ✅ `app-shell.tsx`, `sidebar.tsx`.
- **Meet 24×24 CSS px minimum target size on desktop (WCAG 2.5.8); gate 44px floor on `@media (hover:none)` only.** — ✅ `buttonVariants` touch floor gated. [C30]
- **Ensure focus is not fully obscured by sticky glass chrome (2.4.11).** — ◑ audit `scroll-margin` on focus targets.
- **Honor `prefers-reduced-motion`, `prefers-reduced-transparency`, `prefers-contrast: more`, `forced-colors`.** — ✅ `globals.css` parallel surfaces. [C32]
- **Give every icon-only control a descriptive accessible name.** — ✅ per [PRD 06 §5.1](../prd/06-design-system-visual-spec.md).

**Platform note (Desktop).** Focus ring must meet 2.4.13 (≥2px perimeter, 3:1 contrast); audit `--focus-ring` token.

---

## 11. Performance

**Best practice.** Protect INP (≤200ms p75); batch streaming updates per rAF; virtualize long threads; bound cold-start bootstrap with timeout + retry. [C37][C38][C41]

**Repo stance.**

- **Flush streamed tokens once per rAF; never per-token React state updates.** — ✅ [PRD 01 §5.4](../prd/01-core-chat-experience.md). [C38][C39]
- **Virtualize message list past ~80 messages with overscan; complement with `content-visibility: auto`.** — ✅ `message-list.tsx`, `globals.css`. [C41]
- **Show pre-first-token skeleton within ~150ms.** — ✅ typing indicator per [PRD 06 §5.2](../prd/06-design-system-visual-spec.md).
- **Bound bootstrap fetch with `BOOTSTRAP_TIMEOUT_MS`; surface retry on stall.** — ✅ per [AGENTS.md](../../AGENTS.md).
- **Budget INP ≤200ms, LCP ≤2.5s, CLS ≤0.1 at p75.** — ➕ add to perf runbook. [C37]

---

## 12. Trust, privacy & safety

**Best practice.** Disclose AI interaction clearly at first use; frame no-train defaults plainly; surface substitution and grounding honesty; handle errors with outcome-first copy and recovery actions. [C42][C45]

**Repo stance.**

- **Ship persistent AI-interaction disclosure (Art. 50(1)) — clear, distinguishable, accessibility-conformant.** — ✗ gap; firm P0 from 2 Aug 2026. [C42][C43]
- **State no-train default plainly; show per-route data policy in model directory.** — ✅ `settings-dialog.tsx`, `model-directory-dialog.tsx`.
- **Never silently downgrade model or block content — always surface reason + recourse.** — ◑ mechanism exists; callout content gap (§3, §7).
- **Mark ungrounded search turns honestly.** — ✅ exceeds most competitors.
- **Lead error messages with outcome; offer 2–3 recovery actions; preserve partial output.** — ✅ [PRD 08](../prd/08-error-and-limit-states.md). [C26]
- **Add a general uncertainty cue near the composer ("AI can make mistakes — verify important info") complementing per-turn attribution.** — ➕ opportunity. [C26]
- **Design ahead for C2PA/content-credentials on future synthetic media.** — ➕ P2. [C45]

---

## 13. Platform surface — desktop pointer & keyboard

**Best practice.** Desktop AI chat should offer keyboard shortcuts, a command palette, hover-enhanced density, multi-pane compare, and mouse-precision affordances — every accelerator mirrored in visible UI. [C46][C48][C51]

This section is **canonical for desktop-specific guidance** (no prior desktop best-practice doc exists). Findings from the 2026-07-05 platform-split research:

| # | Surface | Best-practice guidance | Repo status |
| --- | --- | --- | --- |
| D1 | **Keyboard shortcuts & discoverability** | Use ⌘/Ctrl as primary modifier; respect browser-reserved combos; expose shortcuts via dialog + menu hints; allow remapping with guard for composer invariants. | ✅ Registry + reserved-combo guard + `shortcuts-dialog.tsx` + key-caps. [C46][C47] |
| D2 | **Command palette** | ⌘/Ctrl+K global toggle plus visible trigger; focus input on open, restore focus to opener on close; group commands; confirm destructive actions. | ◑ Palette ships; verify visible trigger + focus return + destructive confirm. [C48][C49][C50] |
| D3 | **Hover / focus states** | Hover is enhancement, not sole affordance; visible focus meeting 2.4.13; focused element not fully obscured by sticky chrome (2.4.11). | ✅ `focus-visible:shadow-[var(--focus-ring)]`; ◑ audit contrast/obscuring. [C30][C32] |
| D4 | **Right-click context menus** | Fine as power-user accelerator; mirror every item in kebab/overflow menu; use ARIA menu semantics. | ○ No `onContextMenu` in-tree. [C48] |
| D5 | **Drag-and-drop** | WCAG 2.5.7: every drag operation needs single-pointer alternative; design before attachments land. | ○ No DnD today. [C31] |
| D6 | **Multi-pane / compare layouts** | Canonical ~70/30 supporting pane; independently scrollable; collapse to sheet at compact width. | ✅ `compare-view.tsx` 2-up grid. [C51] |
| D7 | **Wide-viewport density** | Densify type/spacing on desktop via `md:`; cap reading column ~70–80ch. | ✅ ST5 type ramp + PRD 03 §5.3. |
| D8 | **Window-resize behavior** | Single source of truth for shell (breakpoint hook + container queries); no reload on resize. | ✅ PRD 03 §4.1/§5.3. |
| D9 | **Mouse-precision affordances** | Desktop may use denser targets (24px WCAG floor); gate 44px touch floor on `hover:none` only. | ✅ `buttonVariants` invariant. [C30] |
| D10 | **Tooltips** | Brief (<75 chars), action-oriented; not sole carrier of essential info; keyboard-focus triggerable; WCAG 1.4.13 dismissable. | ✅ `ui/tooltip.tsx`; ◑ verify keyboard + 1.4.13. [C46] |

**Cross-platform seam.** Every shortcut, right-click action, and drag operation must have a visible, single-pointer, keyboard-operable equivalent (WCAG 2.5.7). This is the same principle as mobile's "every gesture has a tap alternative" — state once, cross-reference [mobile-ux.md §13](./mobile-ux.md#13-platform-surface--mobile-touch--pwa).

---

## 14. Appendix — Actionable checklist

Each item is a single assertable statement. `[P0]/[P1]/[P2]` priority; `(§N)` back-reference.

### §2 Chat surface
- [ ] [P0] Enter sends and Shift+Enter inserts newline on desktop; textarea auto-grows then scrolls. (§2)
- [ ] [P0] Streamed tokens flush once per `requestAnimationFrame`, never per-token `setState`; long loops yield via `scheduler.yield()` with MessageChannel fallback. (§2, §11) [C38][C39]
- [ ] [P0] Streamed message body is NOT wrapped in `aria-live`; discrete status uses separate polite region. (§2, §10) [C34][C35]
- [ ] [P0] Markdown sanitized with allowlist hardening before render. (§2) [C65]
- [ ] [P0] Auto-scroll follows stream only when user is near bottom; "Jump to latest" shown otherwise. (§2)
- [ ] [P1] Paste-image and drag-and-drop attachment with drop overlay when tier supports attachments. (§2) [C31]
- [ ] [P1] Reading column capped at ~70–80ch on wide viewports. (§2)

### §3 Message actions
- [ ] [P0] Message actions hover-revealed with focus-visible parity for keyboard. (§3)
- [ ] [P0] Copy, Regenerate, Edit-last, thumbs feedback on every assistant turn. (§3)
- [ ] [P0] Substitution callout shows requested tier, served model, and reason visibly — not pill-only. (§3) [C26]
- [ ] [P1] Branch-in-new-chat copies thread without mutating source. (§3)

### §4 Conversation management
- [ ] [P0] Persistent sidebar at ≥768px with search, time grouping, rename, delete-with-confirm. (§4)
- [ ] [P0] Sidebar exposed as labeled `<nav>` landmark. (§4) [C36]
- [ ] [P1] Full-text search with transparency filter chips. (§4)

### §5 Agentic & tools
- [ ] [P0] Plan-approval card shows estimated cost + per-run cap. (§5) [C4][C5]
- [ ] [P1] Gated tool calls support edit-then-approve. (§5) [C2]
- [ ] [P0] Live per-run cost meter updates during fan-out. (§5) [C11]
- [ ] [P0] Tool lifecycle states render with distinct icons and labels. (§5) [C6]
- [ ] [P1] Per-subagent substitution attribution when worker rerouted. (§5)

### §6 Citations
- [ ] [P0] Inline `[n]` markers map to source cards by stable ID. (§6)
- [ ] [P1] Desktop hover preview on citation markers; keyboard focus opens immediately. (§6) [C18]
- [ ] [P0] Ungrounded marker when search returns zero usable sources. (§6)

### §7 Transparency
- [ ] [P0] Served tier visible on every assistant message without hover. (§7)
- [ ] [P0] Per-message "View spend" links to Spend hub; no inline cost in thread. (§7)
- [ ] [P0] Reasoning panel auto-opens while streaming, collapses on complete, absent when no trace. (§7) [C27]

### §8 Onboarding & settings
- [ ] [P0] Persistent AI-interaction disclosure at first interaction. (§8, §12) [C42]
- [ ] [P0] BYOK key never echoed; password input + masked fingerprint. (§8)
- [ ] [P0] Anonymous guest can send first message without auth wall. (§8)

### §9 Billing & limits
- [ ] [P0] Limit errors render inline with `actions[]` buttons (Upgrade, Add credits, BYOK). (§9)
- [ ] [P1] Usage meter escalates tone at 80%/95%/100%. (§9)
- [ ] [P1] Plan comparison before Stripe checkout. (§9)

### §10 Accessibility
- [ ] [P0] Announce "Stopped" through polite region when stream stopped. (§10) [C34]
- [ ] [P0] Shortcuts dialog traps focus and restores to invoker on close. (§10) [C36]
- [ ] [P0] All interactive targets ≥24×24 CSS px or meet spacing exception. (§10) [C30]
- [ ] [P1] Focus never fully obscured by sticky chrome (2.4.11). (§10)
- [ ] [P0] `prefers-reduced-motion` path for every animation. (§10)

### §11 Performance
- [ ] [P0] Message list virtualized past threshold; `content-visibility` on off-screen rows. (§11) [C41]
- [ ] [P0] Bootstrap timeout surfaces retry, not infinite spinner. (§11)
- [ ] [P1] INP budget ≤200ms p75 documented in perf runbook. (§11) [C37]

### §12 Trust
- [ ] [P0] AI-interaction disclosure clear, distinguishable, accessibility-conformant. (§12) [C42]
- [ ] [P0] No silent model downgrade — substitution always visible with reason. (§12)
- [ ] [P1] General uncertainty cue near composer ("verify important info"). (§12)

### §13 Platform (desktop)
- [ ] [P0] Every shortcut has a visible menu equivalent. (§13) [C46]
- [ ] [P0] Command palette has visible trigger and restores focus on close. (§13) [C48]
- [ ] [P1] Right-click context menu mirrors kebab actions when implemented. (§13)
- [ ] [P0] Any future drag-and-drop has single-pointer alternative (2.5.7). (§13) [C31]
- [ ] [P0] Compare view renders 2-up on desktop with independent scroll. (§13) [C51]
- [ ] [P1] Tooltips keyboard-focusable and WCAG 1.4.13 dismissable. (§13) [C46]

---

## Appendix — Citation keys (desktop)

External sources cited by `C#` key. Access date **2026-07-05** unless `[verify-at-build]`.

| Key | Source |
| --- | --- |
| C1–C17 | Agentic/HITL/tool UX — see [research memo](../research/2026-07-05/02-agentic-tool-ui-ux.md) §5 |
| C18–C22 | Citations/grounding — ibid. |
| C23–C29 | Model picker/transparency — ibid. |
| C30–C36 | WCAG 2.2 / ARIA APG — [cross-cutting memo](../research/2026-07-05/cross-cutting-ux-best-practices.md) |
| C37–C41 | Performance — ibid. |
| C42–C45 | Trust/legal — ibid. |
| C46–C50 | Desktop platform — [platform-split memo](../research/2026-07-05/ux-best-practices-platform-split.md) |
| C51 | Android canonical layouts (70/30) |
| C65–C71 | Core chat — [2026-05-27 research](../research/2026-05-27/01-core-chat-ux.md) `[verify-at-build]` |
