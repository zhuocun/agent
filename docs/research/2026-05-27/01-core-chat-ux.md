# Research & PRD Review — Core Chat Experience, Design System, Error/Limit States

**Author:** Product/UX Research
**Date:** 2026-05-27
**Scope:** PRD 01 (Core Chat), PRD 06 (Design System), PRD 08 (Error & Limit States); framing from PRD 00.
**Method:** Fresh online pass (May 2026) + critical PRD review. Sources at bottom with access dates (all accessed 2026-05-27).

---

## 1. Summary

- **The PRDs are unusually strong and current.** They already absorbed the big 2025–2026 corrections most teams get wrong: branching is shipped/standard (not "retreated from"), reasoning panels are auto-open/auto-collapse-with-summary, slash commands are an underserved power-user need, memory is a free baseline (so the wedge is the *transparency layer*), and metered pricing is the 2026 reality. Few factual errors remain.
- **Streamdown is now the de-facto standard and has hardened/modularized** since the PRD's snapshot. The PRD's "adapt a Streamdown-style renderer" is correct, but the spec under-specifies the *security* posture (`rehype-harden`) and the **token-batching/INP mechanism**, which is the actual lever for the §7 "60fps / smooth stream" target. This is the single most valuable PRD strengthening available.
- **Accessibility is the most defensible wedge and the research strongly validates it.** A March 2026 screen-reader teardown of Claude.ai documents *exactly* the gaps the PRD targets: no completion announcement, live regions that re-read partial text token-by-token, an inaccessible keyboard-shortcuts dialog, and sidebar landmark gaps. The PRD covers the first two but should add the last two as explicit acceptance criteria.
- **Answer-first / progressive-disclosure layout went from "nice idea" to incumbent default.** Gemini's May 2026 "Neural Expressive" redesign leads with highlighted key info + expandable detail. The PRD lists this as a P1 renderer experiment (§4.4) — research says elevate it toward P0/early-P1 because it is now an expectation, not a differentiator.
- **Branching converged to a clear pattern the PRD already matches.** ChatGPT "Branch in new chat" is live; Gemini began rolling explicit branching at I/O 2026; AI Elements ships first-class `MessageBranch*` navigation components. The PRD's "copy-on-branch P1, in-thread trees P2" call is correct and now better-supported than when written.
- **Reasoning display is fragmenting in a way the PRD partly misses.** In 2026 the majors auto-route *whether to think at all* ("Thinking on Instant"), so a Thinking trace sometimes appears and sometimes doesn't on the same model/tier. The PRD's "no reasoning → no panel" rule handles this, but the **reasoning-effort toggle (§4.2 P1)** now coexists with provider auto-decisions — worth a note so the toggle isn't presented as fully deterministic.
- **AI SDK 6 (GA) now ships HITL tool-approval and branch components natively**, directly de-risking PRD 01 §4.1 (HITL) and §4.6 (branch). Reference these concretely rather than "design now."
- **Error/limit taxonomy (PRD 08) is best-in-class for a lean MVP** — typed payload, severity ladder, substitution-is-not-an-error. Main gaps: guest-gate model-downgrade transparency, `retry_after` countdown UX, and reconciling the canonical-payload example's hard-coded "50/50" with PRD 08's own "state the limit" copy rule.

---

## 2. New ideas & developments (online research)

### Theme A — Streaming-safe markdown rendering (the perceived-quality lever)

- **Streamdown is now a hardened, modular standard (v1.x, 5.2k★, last release Mar 2026).** It is a drop-in `react-markdown` replacement: GFM, Shiki code highlighting with **copy + download**, KaTeX math, **interactive Mermaid**, CJK support, and crucially **`rehype-harden` security hardening** and **memoized incremental rendering**. Unterminated-block parsing is handled via a `remend`-style pass. (Sources: streamdown.ai; github.com/vercel/streamdown — 2026-05-27.)
  - *Implication for us:* Adopt Streamdown (or its hardening approach) directly; PRD 01 §4.4/§5.4 should name `rehype-harden`-class sanitization as the mechanism for its §4.4 "[P0 security]" requirement, and adopt its memoization model. Mermaid (PRD P1) and code-download (PRD P1) are already in the library — re-confirm phase split is by *choice*, not effort.
- **Token-batching/INP is now a documented, named technique.** The 2026 consensus pattern for high-frequency streaming in React: buffer deltas in a mutable ref and **flush on a `requestAnimationFrame` cadence**, plus `scheduler.yield()` to keep the main thread responsive and protect INP. Naive per-token `setState` is the known anti-pattern. (Sources: sitepoint.com streaming-backends-react; tigerabrodi.blog performant AI markdown renderer; web.dev/MDN scheduler.yield via search — 2026-05-27.)
  - *Implication for us:* PRD 00 already cites "`scheduler.yield()` + rAF token-batching" but **PRD 01 §5.4 performance target does not** — it states "60fps" without the mechanism. Add the rAF-flush + `scheduler.yield()` pattern as the implementation note backing the §7 smoothness metric.
- **O(n) incremental parsing matters at long-thread scale.** New renderers explicitly moved from O(n²) re-parse-everything to O(n) incremental parsing per chunk. (Source: dev.to "From O(n²) to O(n)" — 2026-05-27.)
  - *Implication for us:* Reinforces PRD §5.4 "virtualize very long threads"; pair virtualization with incremental (not full re-parse) markdown to hit the mobile 60fps target.

### Theme B — Reasoning / "thinking" panel display

- **2026 majors auto-route *whether* to reason.** "ChatGPT Thinking on Instant" and GPT-5.5's standard/extended split mean the model may think briefly and **not show a trace**, or think hard and show one — on the *same* selected tier. A reasoning-effort control (low/medium/high; Light/Standard/Extended/Heavy) now sits in the composer on several products. (Sources: bleepingcomputer.com thinking-time toggle; OpenAI Help Center GPT-5.3/5.4/5.5; tomsguide.com — 2026-05-27.)
  - *Implication for us:* PRD 01 §4.2's "render only when emitted / no empty panel" rule is exactly right for this world. But the §4.2 **P1 reasoning-effort toggle** should be framed as a *request/hint* that the provider may override (auto-routing), not a guaranteed switch — otherwise it conflicts with the auto-decision and with the §4.6/§5.2 "Thought for Xs" display when no trace is returned.
- **AI Elements `Reasoning` component formalizes the exact UX the PRD specifies** (auto-open while streaming, auto-collapse on finish). (Source: elements.ai-sdk.dev/components/reasoning — 2026-05-27.)
  - *Implication for us:* PRD §5.2 state table maps 1:1 to a shipped component — low build risk; reference it.

### Theme C — Message actions, branching, editing

- **ChatGPT restricted edit/retry to the most-recent message only (2026), but shipped "Branch in new chat."** Widely read as a GPT-5.3/5.4 model constraint, not a product retreat. (Sources: aiproductivity.ai restricts-message-editing; aiqnahub.com retry-button-removed — 2026-05-27.)
  - *Implication for us:* Directly **confirms** PRD 01 §4.6 + §8 narrative (edit-last for data-model simplicity; copy-on-branch P1). No change needed — the PRD's corrected narrative is now the consensus read.
- **Gemini began rolling explicit chat branching (I/O 2026 / Android teardown); AI Elements ships `MessageBranch*` navigation.** Explicit fork-without-losing-original is now table stakes; in-thread *trees* remain rare. (Sources: webpronews.com Gemini branching; techcrunch.com I/O 2026; elements.ai-sdk.dev/components/message — 2026-05-27.)
  - *Implication for us:* Validates copy-on-branch P1 / trees P2. When building branch UI, `MessageBranch*` gives a ready navigation pattern even for the copy model.

### Theme D — Composer ergonomics, slash commands, prompt libraries

- **Native slash commands remain absent from mainstream *consumer* chat; users bolt on Slashprompt/extensions** (save once, type `/` in any chat, variables + folders + local-first). (Sources: slashprompt.app; aidigitalbox.com Claude commands guide — 2026-05-27.)
  - *Implication for us:* **Confirms** PRD §4.3's reframing of slash commands as a committed P1 differentiator and underserved need. The "variables + folders + local-first prompt library" shape is the bar to clear.
- **Attachments (paste, drag-drop, chips) are now "standard interactive components," not differentiators.** (Sources: uxpin.com chat UI design; medium.com/alexander-lukashov AI chat UI libraries 2026 — 2026-05-27.)
  - *Implication for us:* Supports deferring attach to P1 *for the text-core MVP*, but flags reputational risk: a launch with no attach affordance reads as incomplete to users who expect it everywhere. Keep P1 fast-follow tight; ensure empty-state/onboarding copy sets the text-only expectation.
- **Voice/multimodal input is the 2026 composer frontier** (98% STT accuracy, voice-first keyboards). PRD correctly defers TTS/dictation to P1.
  - *Implication for us:* No P0 change; note that dictation is increasingly *expected* on mobile-web — keep it early-P1.

### Theme E — Conversation management & organization

- **Projects/folders converged: ChatGPT Projects most mature; Claude Projects (Pro); Gemini testing Projects + Notebooks (2026); still no native folder tree in ChatGPT.** Pins + full-text search are baseline everywhere. (Sources: nexasphere.io organize 2026; androidauthority.com Gemini Projects; mindstudio.ai Gemini Notebooks — 2026-05-27.)
  - *Implication for us:* **Confirms** PRD's P0 (history/search/rename/delete) + P1 (pin/archive) + P2 (Projects) staging. Note: incumbents put **per-project custom instructions** in Projects — relevant when our P2 org-layer is specced (our §4.8 custom-instructions should be designed to later scope per-project).
- **Retrieval-over-history ("search past chats" as a tool) is gated behind paid plans even where memory is free.** (Consistent across organize-2026 sources.)
  - *Implication for us:* **Confirms** PRD §4.5 P1 framing of retrieval-over-history as the gated higher-value capability.

### Theme F — Accessibility in AI chat (the measured-gap wedge)

- **March 2026 Claude.ai screen-reader teardown documents concrete gaps:** (1) **no announcement when generation completes** — users manually re-check every turn; (2) **live regions re-read partial text token-by-token** during streaming (NVDA/JAWS), the fix being to *suppress* live updates during stream and announce only the completed answer; (3) **Keyboard Shortcuts dialog is fully inaccessible** (focus never enters); (4) **sidebar lacks landmarks**, forcing top-of-page traversal; (5) missing shortcuts for input focus / new chat / delete chat. (Source: dev.to/wiscer screen-reader-experience-analysis-on-claudeai, 2026-03-04 — 2026-05-27.)
  - *Implication for us:* This is gold for the a11y wedge and partially *contradicts the naive `aria-live="polite"` approach in PRD §5.7*. Polite live regions on the streaming node cause the exact token-by-token re-reading the teardown flags. **Recommended announce model: do NOT put the streaming text node itself in an aria-live region; announce discrete status transitions ("Generating", "Response ready") via a separate polite status region, and make the completed message body navigable but not auto-announced.** Add the inaccessible-shortcuts-dialog and sidebar-landmark gaps as explicit P0 acceptance criteria — they are cheap and directly beat the measured leader.
- **AI models themselves miss 43% of a11y issues (keyboard nav, dynamic content, cognitive load)** — i.e., you cannot fully automate this; manual SR testing is required. (Source: accessibility-test.org Oct 2025 — 2026-05-27.)
  - *Implication for us:* Supports PRD §7's "automated axe + manual screen-reader smoke" — keep the manual leg; don't trust automated-only.

### Theme G — Error & limit-state UX

- **Rate-limit reality in 2026:** providers expose `retry-after`; "rate limit" is overloaded (RPM vs input-TPM vs output-TPM vs spend), and consumer products show rolling reset windows ("resets in 5h"). Best practice is to name *which* limit and *when* it resets. (Sources: platform.claude.com rate-limits; blog.laozhang.ai identify-the-limit-owner; ai-toolbox.co ChatGPT limits 2026 — 2026-05-27.)
  - *Implication for us:* **Strengthens** PRD 08 §5.4 + §6 copy rules. Add a concrete `retry_after_ms` → **live countdown** UX requirement (the payload already carries the field; the UX of *showing* it is unspecified).
- **Guest/anonymous gating is now nuanced: guests get a few messages on a good model, then auto-downgrade to a mini model, then hit a sign-up wall** (e.g., 10 messages then mini; no history/voice). (Sources: ai.zenken.co.jp ChatGPT without login; aifreeforever.com — 2026-05-27.)
  - *Implication for us:* PRD 08 has `PLATFORM_GUEST_LIMIT` but **not a guest *model-downgrade* state**. For a transparency-first product this is a notable surface: a guest silently moved to a weaker model violates our wedge. Recommend a guest-downgrade callout reusing the §5.4 substitution-callout (PRD 06 §5.4 / PRD 07).
- **Design-system trend:** error/limit states increasingly modeled as **tokens + typed states** (calm UI, transparent AI), not ad-hoc red banners. (Sources: uxpin.com UX/UI trends 2026; elements.envato.com calm interfaces — 2026-05-27.)
  - *Implication for us:* **Confirms** PRD 06 §3.1 trust/error roles and PRD 08 severity-ladder approach.

### Theme H — Design-system / visual trends (2026)

- **Token-first design systems are now infrastructure for AI-generated UI**; theming is becoming a *runtime* capability (theme server / token API; auto-contrast checks per theme variant); "calm UI / transparent AI / reduced cognitive load" is the headline 2026 trend. (Sources: oneminutebranding.com design tokens 2026; medium AI design systems tokens; uxpin.com trends; elements.envato.com — 2026-05-27.)
  - *Implication for us:* **Strongly confirms** PRD 06's token-first, semantic-role, "transparency is chrome" approach. Two additions worth considering: (a) **auto-contrast verification per theme variant** as an acceptance criterion (PRD 06 §7), since light/dark/system parity is already required; (b) the "calm UI" trend supports PRD 06 §8 Q2's "collapsed cost with visible summary" recommendation — keep transparency present but not noisy.
- **Gemini "Neural Expressive" (May 2026): answer-first formatting (key info highlighted up top, expandable detail below) is now an incumbent default**, plus haptics/motion. (Source: techcrunch.com I/O 2026 — 2026-05-27.)
  - *Implication for us:* Elevate PRD 01 §4.4 "answer-first / progressive disclosure" from a P1 experiment toward an early-P1/P0 layout convention; it is now an expectation. (Distinct from the reasoning panel.)

---

## 3. PRD review findings

| # | Tag | PRD §ref | Finding | Recommended action |
|---|---|---|---|---|
| 1 | [risk] | 01 §5.7; 08 §9 | **`aria-live="polite"` on the streaming answer is the documented cause of token-by-token re-reading** (the exact Claude.ai bug a March-2026 teardown flags). PRD 08 §9 ("announce once when generation ends") is correct, but PRD 01 §5.7 says the streaming answer "is announced appropriately (e.g., `aria-live="polite"`)", which invites the wrong implementation. | Reconcile: the **streamed text node must NOT be a live region.** Announce discrete status transitions via a separate polite status region; the completed body is navigable, announced once. Make PRD 01 §5.7 defer to PRD 08 §9's "announce once" model and state the anti-pattern explicitly. |
| 2 | [gap] | 01 §5.7; 06 §7 | Two measured leader gaps are **not** in our acceptance criteria: **(a) inaccessible keyboard-shortcuts dialog** (focus never enters) and **(b) sidebar lacks landmarks**. These are the cheapest, most concrete ways to "beat the leaders." | Add explicit ACs: shortcuts dialog (§4.9) traps/receives focus and is SR-navigable; sidebar/history exposes landmark roles for direct navigation. |
| 3 | [gap] | 01 §5.4; 07-metric link in §7 | §5.4 sets a "60fps / no layout shift" target but **omits the mechanism** (rAF token-batching + `scheduler.yield()`) that PRD 00 already names. Target without mechanism is not buildable-from-spec. | Add the rAF-flush-from-ref + `scheduler.yield()` batching pattern and "incremental (not full re-parse) markdown" as the implementation note under §5.4 performance. |
| 4 | [gap] | 01 §4.4 [P0 security]; §5.4 | Sanitization is required but the **mechanism is unnamed**; 2026 standard is `rehype-harden`-class allowlist hardening (shipped in Streamdown). | Name `rehype-harden`-class hardening as the satisfying mechanism; note Streamdown bundles it. |
| 5 | [scope] | 01 §4.4 (answer-first P1) | Answer-first / progressive-disclosure is listed as a low-priority P1 *experiment*, but Gemini's May-2026 redesign made it an **incumbent default**. It risks reading as "behind" if deferred. | Elevate to early-P1 (or P0 prompt/layout convention); validate with dev persona as planned, but treat as expectation not differentiator. |
| 6 | [inconsistency] | 01 §4.2 (P1 reasoning-effort toggle) | The toggle is specified as if deterministic, but 2026 providers **auto-route whether to think** ("Thinking on Instant"); a "high effort" request can still yield no visible trace, conflicting with the §5.2 "Thought for Xs" expectation. | Frame the effort toggle as a *hint the provider may override*; keep "no trace → no panel" (already correct). Cross-ref PRD 02 for the auto-route interaction. |
| 7 | [gap] | 08 §5.4 `PLATFORM_GUEST_LIMIT`; §7 | 2026 guest flows **silently downgrade the model** before the hard sign-up wall. A transparency-first product must not silently downgrade a guest. No guest-downgrade state exists. | Add a guest model-downgrade surface that reuses the substitution-callout (PRD 06 §5.4 / PRD 07), distinct from the hard `PLATFORM_GUEST_LIMIT` block. |
| 8 | [gap] | 08 §3 payload; §5.4; §6 | `retry_after_ms` is in the payload but there is **no UX spec for showing a live countdown / reset time** ("resets in 6h"), which is the 2026 best-practice and matches §6 rule 2. The §3 example hard-codes "Resets in 6h" in `body`, conflicting with treating reset as structured data. | Spec a countdown/reset-time UI driven by `retry_after_ms` (or a `reset_at`), and keep reset time out of free-text `body` so it stays live/localizable. |
| 9 | [inconsistency] | 08 §3 example vs §6 rule 2 | The canonical example bakes "50/50 free messages" and "Resets in 6h" into `body` strings; §6 rule 2 demands counts be stated, but as *free text* these can't be localized or kept live (i18n baseline is P0 per PRD 00). | Move counts/reset into `meta` (e.g., `used`, `limit`, `reset_at`) and compose copy from them; keep `body` as fallback. |
| 10 | [gap] | 06 §7 acceptance | Light/dark/system parity is required (§7.7) but there is **no per-variant auto-contrast check**, now a 2026 token-system best practice and cheap given the contrast roles in §3.1. | Add "automated contrast check passes for every theme variant" to §7. |
| 11 | [scope] | 01 §4.3 (attach P1) / 06 §5.6 | Deferring attachments to P1 is defensible for a text-core MVP, but attach is now a *baseline expectation* everywhere; a no-attach launch carries reputational risk with the dev persona. | Keep P1, but tighten the fast-follow; ensure onboarding/empty-state copy (§4.7) sets the "text-only at launch" expectation so it reads as intentional, not missing. |
| 12 | [error-minor] | 01 §9 References | The reasoning-component reference points to `shadcn.io/ai/reasoning` and `elements.ai-sdk.dev`; the canonical 2026 home is **AI Elements (`elements.ai-sdk.dev`) on AI SDK 6**, which now also ships `MessageBranch*` (branching) and **HITL tool-approval** hooks — directly relevant to §4.1/§4.6. | Update references to AI Elements/AI SDK 6 as primary; note `MessageBranch*` and `needsApproval`/Execution-Approval hooks de-risk §4.1 HITL and §4.6 branch (move from "design now" to "wire the shipped primitive"). |
| 13 | [strength-confirmed] | 01 §4.6/§8; 00 D10 | The corrected branching narrative (incumbents *shipped* branching; only arbitrary-old-message editing was restricted) is **now consensus** (ChatGPT "Branch in new chat" live; Gemini rolling branching). | No change — note as validated; safe to lock D10. |
| 14 | [strength-confirmed] | 01 §4.3 slash commands; 00 P1 | Native consumer slash commands still absent; users bolt on Slashprompt. The "committed P1 differentiator" call is validated. | No change — validated. The "variables + folders + local-first" prompt-library shape is the bar. |
| 15 | [gap] | 08 §13 Q3 | Open question on Continue-vs-Regenerate exposure is unresolved; 2026 products lean to a **primary "Continue" with secondary regenerate** for interrupted streams (matches §8 `interrupted` state). | Recommend resolving toward primary Continue + secondary Regenerate for `interrupted`; keep both for `stopped`. (See Recommendations.) |
| 16 | [gap] | 01 §4.5 search AC | Search is P0 but full-text-vs-title is left to PRD 04 (§8 Q8). Incumbents now ship **full-text search as baseline** (incl. Gemini); title-only would read as weak. | Strengthen the §4.5 AC target to full-text as the expectation (fallback only if index truly can't); flag to PRD 04 as a higher-priority dependency. |

---

## 4. Recommendations (prioritized)

**P0 (do before/at MVP build — cheap, high-leverage, on-wedge):**
1. **Fix the streaming a11y announce model (Finding 1).** Do not make the streamed text node a live region. Status-only polite region + announce-once-on-complete. This is the difference between "a11y wedge" and "shipped the same bug as Claude."
2. **Add the two measured-leader a11y ACs (Finding 2):** accessible shortcuts dialog + sidebar landmarks. Trivial cost, directly beats the leader our PRD cites.
3. **Name the renderer mechanisms (Findings 3, 4):** rAF token-batching + `scheduler.yield()` + incremental parse + `rehype-harden`-class sanitization, all in PRD 01 §5.4. Make the §7 smoothness/security targets buildable-from-spec. Adopt Streamdown.
4. **Add a guest model-downgrade transparency surface (Finding 7).** A silent guest downgrade is an own-goal for a transparency-first product.
5. **Per-variant auto-contrast acceptance (Finding 10)** in PRD 06 §7.
6. **Reconcile the error payload i18n (Findings 8, 9):** counts/reset into `meta`, add `retry_after`/`reset_at` countdown UX.

**P1 (fast-follow / strengthen as features land):**
7. **Elevate answer-first layout (Finding 5)** to early-P1 default; validate with dev persona.
8. **Wire shipped AI SDK 6 primitives (Finding 12):** `MessageBranch*` for copy-on-branch, Execution-Approval hooks for HITL tool parts.
9. **Reframe reasoning-effort toggle as a hint, not a switch (Finding 6).**
10. **Slash-command prompt library:** match the Slashprompt bar (variables, folders, local-first).
11. **Tighten attach fast-follow + set text-only expectation in onboarding (Finding 11).**

**P2 (design-ahead so we don't repaint):**
12. **Custom instructions should be designed to later scope per-project** (incumbents put instructions in Projects) — shape the §4.8 data so the P2 org-layer can extend it.
13. Resolve Continue-vs-Regenerate toward primary-Continue for `interrupted` (Finding 15).

---

## 5. Open questions (need a product decision)

1. **Streaming announce cadence:** announce-once-on-complete is safest, but power SR users may want *progressive* chunk announcements (e.g., per paragraph). Do we offer a setting, or default to once-on-complete? (Leaning: once-on-complete default; revisit with SR user testing — PRD §7 manual leg.)
2. **Guest downgrade vs guest block:** do guests get *any* downgraded model after their good-model allotment (ChatGPT pattern), or do we hard-gate to sign-up immediately? Affects funnel vs cost vs transparency story. Cross-PRD with 05 (monetization) and 02 (routing).
3. **Answer-first as P0 vs P1:** is it a prompt/format convention (cheap, P0) or a renderer feature (P1)? Decide who owns it (prompt = PRD 02, layout = PRD 01).
4. **Reasoning-effort UI honesty:** if the provider auto-overrides a "high effort" request, do we surface that it was overridden (transparency wedge) or silently honor the provider? (Leaning: surface it — consistent with served-vs-requested.)
5. **Full-text search at MVP:** confirm with PRD 04 whether full-text is feasible at P0; if not, is title+recent-content acceptable given incumbents now ship full-text?
6. **Dictation timing:** mobile-web users increasingly expect voice input; is TTS/dictation early-P1 or mid-P1?

---

## 6. Sources

All accessed 2026-05-27.

**Streaming / rendering / performance**
- Streamdown — https://streamdown.ai/ and https://streamdown.ai/docs
- Streamdown (GitHub, v1.x, releases through Mar 2026) — https://github.com/vercel/streamdown
- "How To Build a Performant AI Markdown Renderer" — https://tigerabrodi.blog/how-to-build-a-performant-ai-markdown-renderer
- "From O(n²) to O(n): Building a Streaming Markdown Renderer for the AI Era" — https://dev.to/kingshuaishuai/from-on2-to-on-building-a-streaming-markdown-renderer-for-the-ai-era-3k0f
- "Streaming Backends & React: Controlling Re-render Chaos" (rAF batching, ref buffering) — https://www.sitepoint.com/streaming-backends-react-controlling-re-render-chaos/
- "React Server Components Streaming Performance Guide 2026" — https://www.sitepoint.com/react-server-components-streaming-performance-2026/
- markstream-vue (progressive Mermaid/KaTeX, no-jitter streaming) — https://github.com/Simon-He95/markstream-vue
- "Preventing Flash of Incomplete Markdown" (HN) — https://news.ycombinator.com/item?id=44182941

**Reasoning / thinking UI**
- "ChatGPT finally rolls out Thinking time toggle on mobile" — https://www.bleepingcomputer.com/news/artificial-intelligence/chatgpt-finally-rolls-out-thinking-time-toggle-on-mobile/
- OpenAI Help Center — GPT-5.3/5.4/5.5 reasoning options — https://help.openai.com/en/articles/11909943-gpt-53-and-52-in-chatgpt
- "ChatGPT Thinking on Instant Mode (2026)" — https://transferllm.com/blog/chatgpt-thinking-on-instant-mode-what-it-means-and-how-to-use-it-effectively-in-2026/ (HTTP 503 at fetch; corroborated by BleepingComputer + OpenAI Help Center above)
- AI Elements — Reasoning component — https://elements.ai-sdk.dev/components/reasoning

**Branching / message actions / composer**
- "ChatGPT Quietly Restricts Message Editing to Most Recent Prompt Only" — https://aiproductivity.ai/news/chatgpt-restricts-message-editing-retry/
- "ChatGPT Retry Button Removed in 2026" — https://www.aiqnahub.com/chatgpt-web-ui-retry-button-removed/
- "Google Gemini on Android Is Getting Chat Branching" — https://www.webpronews.com/google-gemini-on-android-is-getting-chat-branching-and-it-could-change-how-you-interact-with-ai/
- AI Elements — Message component (MessageBranch*, actions) — https://elements.ai-sdk.dev/components/message
- AI SDK 6 (GA; agents, Execution Approval / HITL) — https://vercel.com/blog/ai-sdk-6
- Slashprompt (prompt library / slash commands) — https://slashprompt.app/
- "Claude.ai Commands 2026" — https://aidigitalbox.com/2026/05/08/claude-ai-commands-guide/
- "AI chat UI libraries 2026" — https://alexander-lukashov.medium.com/the-overview-of-ui-libraries-for-ai-chat-interfaces-in-2026-146a1492114a
- "Chat UI Design 2026" (UXPin) — https://www.uxpin.com/studio/blog/chat-user-interface-design/

**Conversation management / organization**
- "How to Organize AI Conversations (2026)" — https://nexasphere.io/blog/organize-ai-conversations-chatgpt-claude-gemini-2026
- "Gemini Projects" — https://www.androidauthority.com/gemini-projects-folder-organize-3655323/
- "Gemini Notebooks vs Claude Projects / ChatGPT" — https://www.mindstudio.ai/blog/what-is-gemini-notebooks-feature
- "Organize ChatGPT Conversations (2026)" — https://www.ai-toolbox.co/chatgpt-management-and-productivity/organize-chatgpt-conversations-complete-guide-2026

**Accessibility**
- "Screen Reader Experience Analysis on claude.ai" (2026-03-04) — https://dev.to/wiscer/screen-reader-experience-analysis-on-claudeai-433a
- "AI Accessibility Testing: ChatGPT vs Claude vs Gemini (Oct 2025)" — https://accessibility-test.org/blog/qa-testing/automated-testing/ai-accessibility-testing-chatgpt-vs-claude-vs-gemini-oct-2025/
- "ARIA Live Regions" — https://finkbrot.at/en/glossary/digital-accessibility/aria-live-regions

**Error / limit states / guest**
- Claude API Rate limits — https://platform.claude.com/docs/en/api/rate-limits
- "Identify the Limit Owner Before You Retry" — https://blog.laozhang.ai/en/posts/claude-rate-exceeded-error
- "ChatGPT Limits Explained (2026)" — https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-limits-messages-tokens-rate-2026
- Troubleshoot Claude error messages — https://support.claude.com/en/articles/12466728-troubleshoot-claude-error-messages
- "ChatGPT Without Login 2026" — https://ai.zenken.co.jp/en/post/chatgpt-login-required-features/
- "Using ChatGPT free without login" — https://aifreeforever.com/blog/using-chatgpt-without-login-in

**Design system / visual trends / citations**
- "Design Tokens in 2026" — https://www.oneminutebranding.com/blog/design-tokens-2026
- "AI Design Systems: Why Tokens, Schema & Generative Rules Matter Now" — https://medium.com/@Rythmuxdesigner/ai-design-systems-why-tokens-schema-generative-rules-matter-now-ca3ab41c96d9
- "UX/UI Design Trends 2026" (UXPin) — https://www.uxpin.com/studio/blog/ui-ux-design-trends/
- "Calm interfaces, transparent AI" (Envato) — https://elements.envato.com/learn/ux-ui-design-trends
- Gemini I/O 2026 update (Neural Expressive, answer-first formatting) — https://techcrunch.com/2026/05/19/google-updates-its-gemini-app-to-take-on-chatgpt-and-claude-at-io-2026/
- Perplexity citation-forward design — https://www.unusual.ai/blog/perplexity-platform-guide-design-for-citation-forward-answers
- "How Perplexity Selects Sources in 2026" — https://authoritytech.io/blog/how-perplexity-selects-sources-algorithm-2026
- "Progressive Disclosure in AI — Pattern & Best Practices" — https://www.aiuxdesign.guide/patterns/progressive-disclosure

**Multi-model / aggregators**
- T3 Chat review 2026 — https://techfixai.com/t3-chat-ai-review/
- Poe review 2026 — https://www.toolworthy.ai/tool/poe
