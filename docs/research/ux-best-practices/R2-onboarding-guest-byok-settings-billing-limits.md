# R2 — UX Best-Practices Findings: Onboarding · Guest → Signup · BYOK · Settings · Billing · Limit-States

**Worker:** R2 (research only — no code/doc under `docs/ux-best-practices/` was edited).
**Scope:** first-run/onboarding · anonymous-first (guest) usage + the guest→signup upgrade moment · BYOK key entry · settings/preferences organization · billing (Stripe checkout, plan comparison, credits/metered usage, usage meters, upsell timing) · rate-limit/quota/upgrade-prompt states.
**Grounding read:** `docs/prd/00-product-overview.md`, `docs/prd/05-roadmap-monetization-metrics.md`, `docs/prd/08-error-and-limit-states.md`, `docs/research/2026-05-27/05-roadmap-monetization-compliance.md`; components `auth-dialog.tsx`, `byok-form.tsx`, `settings-dialog.tsx`, `usage-meter.tsx`, `spend-analytics-panel.tsx` (+ adjacent `welcome-screen.tsx`, `assistant-message.tsx` error surface, `apiClient.ts` error envelope).
**Structure:** same three sections as R1 — **§A Best practices**, **§B Repo coverage per practice**, **§C Gaps & recommendations**.

Coverage legend (used in §B): ✅ Covered · 🟡 Partial · ❌ Missing.

---

## §A — Best practices

### A1. First-run / onboarding
- **Time-to-first-value over tours.** For AI chat, the empty state *is* the onboarding: a focused composer, a one-line invitation, and 3–6 seed prompts beat multi-step wizards. AI activation is measured by "reached a first successful, valued response," not "finished the tour."
- **Day-1 success checklist.** The strongest retention lever in 2026 AI data is a first-week success checklist (first streamed reply → saw model/cost attribution → opened usage → touched a control), tracked as a funnel rather than shown as a nag. AI-native retention runs ~half of SaaS (~40% GRR / 48% NRR), and "AI-tourist" churn is severe, so first-run must land a real win fast.
- **No premature commitment.** Don't gate the first message behind signup, tour completion, or key entry. Reveal power controls (tiers, BYOK, projects) progressively.
- **Set expectations honestly + disclose AI.** Surface an unobtrusive "you're talking to an AI / can make mistakes" line. This doubles as the EU AI Act Art. 50(1) interaction-disclosure gate (firm **2 Aug 2026**) and generic US good-practice (CA SB 243 posture) — a P0 launch gate, cheap to keep.
- **Accessibility from paint one.** Labeled controls, focus lands in the composer, seed prompts keyboard-reachable, `prefers-reduced-motion` respected on any entrance choreography.

### A2. Anonymous-first (guest) usage & the guest → signup upgrade moment
- **Anonymous-first, value-before-account.** Let guests chat immediately; persist their session so nothing is lost. Convert at *value moments* (save history, add a key, hit a cap, unlock a model), never with an upfront wall.
- **In-place upgrade, no data loss.** Guest→account should be an *upgrade of the same session* (carry chats/prefs forward), not a fresh signup that abandons the guest's work. One dialog hosting both sign-in and create-account with an in-place toggle reduces friction.
- **Contextual, honest gating.** When a feature genuinely needs an account (key storage, billing), explain *why* at the point of need and route straight to auth — don't dead-end on disabled chrome.
- **Guest limits are transparent, staged.** Warn before the wall; if a guest is downgraded to a weaker model, say so (a *substitution callout*, not silence — "never silently downgrade"); at the hard wall, convert with the current thread preserved.
- **Friendly auth validation.** Client-side email/format/length checks, non-enumerating error copy ("Incorrect email or password", not "no such user"), a show/hide toggle on password, and rate-limit-aware messaging.

### A3. BYOK key entry (security cues, validation, never-echo-secret)
- **Never echo the secret.** Enter as a masked field; after save, show only a masked fingerprint (e.g. `sk-…abcd`), never the full key again. Avoid a plaintext reveal toggle for stored secrets.
- **Anti-leak input hardening.** `type=password`, `autocomplete=off`, `autocorrect/spellcheck off`, no logging, no telemetry of the value — prevents autofill/dictionary/keyboard-cache leakage.
- **Explicit trust cues.** State where the key goes and doesn't: "stored encrypted server-side, never sent to other providers," and how billing changes ("charges bill to your key," "removing reverts to platform credits").
- **Validate the key, don't just store it.** Best practice is a test/validation round-trip (or a clear post-save invalid state → BYOK_KEY_INVALID) so a bad paste fails loudly, plus a masked "saved / not usable" status and easy replace/remove with confirmation.
- **Right audience & gate.** BYOK is power-user territory — keep it progressively disclosed and restricted to authenticated accounts (guests must link first).

### A4. Settings / preferences organization
- **Grouped, shallow hierarchy.** Cluster into a few labeled domains (Account/Billing, Chat, Privacy & data, power-user extras) rather than one flat scroll; collapse advanced/rarely-used sections.
- **Platform-idiomatic navigation.** iOS-style grouped drill-down on mobile; a tab/rail on desktop — with roving-tabindex keyboard nav, `role=tab/tabpanel`, and focus return.
- **Privacy-first defaults, legible.** Training opt-in OFF by default and framed as such; one-click export + delete; retention control with plain-language consequences; optional no-telemetry.
- **Deep-linkable + reset-on-open discipline** so a contextual entry (e.g. "manage key", "view spend") lands on the right pane, and transient edit state doesn't leak across opens.

### A5. Billing (Stripe checkout, plan comparison, credits/metered usage, meters, upsell timing)
- **Redirect to hosted Stripe Checkout / Billing Portal** for PCI-safe payment + subscription management; keep the app as a thin launcher with clear busy/error states and idempotent server webhooks as source of truth.
- **Plan comparison at the decision point.** Before checkout, show what Pro unlocks vs. free (models, caps, overage behavior) — a compact comparison, not just an "Upgrade" button. 2026 buyers expect to see the *metered/credit* mechanics (caps + transparent USD overage), because the market has repriced to credits (Copilot/Anthropic/Cursor/T3).
- **Legible usage meters.** Show remaining budget in the user's real unit (USD spend or messages), a fill bar, and staged thresholds (info ~80% → warning ~95% → blocking 100%); label the cost basis and never freeze counts/reset times into static strings (compose from structured `meta`).
- **Upsell timing = at the moment of constrained value, not random.** The highest-converting upgrade prompt is attached to the limit/warning the user just hit ("80% of budget — top spender is X → Upgrade / Buy credits / BYOK"), with 2–3 actions max. Feature-gating lifts conversion vs. pure freemium.
- **BYOK is exempt & honest.** Don't upsell platform credits for provider-billed (BYOK) failures; show BYOK spend as informational.

### A6. Rate-limit / quota / upgrade-prompt states
- **Typed, structured, actionable envelope.** One error taxonomy with `code/severity/title/body/actions[]/retry_after/meta`; counts and reset times live in structured fields and render as a **live countdown** ("Resets in 2h 14m"), localizable, clearing the disabled state at zero.
- **Explain the limit before the hard block**, and lead with outcome ("Message couldn't finish") not cause; preserve partial output; offer 2–3 recovery/conversion actions inline (Upgrade / Add credits / BYOK / Sign up) *at the block*.
- **Account-aware actions.** Guest → Sign up (preserve thread); Free → Upgrade/BYOK/wait; Pro → Add credits/switch cheaper tier; BYOK → fix provider key (no platform upsell).
- **Substitution ≠ error.** Model downgrade/fallback is a calm transparency callout (info/warning), never a red error banner.
- **Accessibility.** `role=status` for warnings, `role=alert` only when immediate; live countdown announced politely; all recovery actions keyboard-operable; ≥44px targets on mobile.

---

## §B — Repo coverage per practice

### B1. First-run / onboarding
| Practice | Status | Evidence |
|---|---|---|
| Empty-state as onboarding (greeting + seed prompts, focused composer) | ✅ | `welcome-screen.tsx` — `buildGreeting`, bootstrap `suggestions` with fallback `PROMPTS`, `compact` mode dedupes when history exists. |
| Progressive BYOK invite (not a wall) | ✅ | `welcome-screen.tsx:116-126` "Connect your API key" banner → `onConnect` (opens settings/BYOK); suppressed in compact / when unwired. |
| Reduced-motion + a11y on entrance | ✅ | `animate-welcome-enter/exit` are class hooks neutralized under `prefers-reduced-motion`; suggestion list is `<ul aria-label="Suggested prompts">`, keyboard-reachable pills, 44px mobile targets (`py-3`). |
| Multi-step tour avoided | ✅ (by design) | No wizard; single hero + pills. |
| Day-1 success checklist / activation funnel surface | ❌ | No first-run checklist UI; PRD 05 §6.1 names it the top retention lever. Only PWA `install-coachmark.tsx` exists (install nudge, not activation). |
| AI-interaction disclosure at first run | 🟡→❌ | The composer disclosure line was **removed** (`8c84d57` "Remove AI disclosure line below composer (#245)"); no equivalent "you're talking to an AI" line found in `composer.tsx`/`welcome-screen.tsx`. PRD 05 §7.5 treats Art. 50(1) disclosure as a **P0 launch gate**. (May survive in a legal footer/settings — not found in the chat surface.) |

### B2. Anonymous-first (guest) usage & guest → signup
| Practice | Status | Evidence |
|---|---|---|
| Anonymous-first sessions, chat before account | ✅ | Custom signed-cookie anonymous sessions (PRD 00 §8/D9); guest can chat; `isAnonymousAccount` branches throughout. |
| In-place, no-data-loss upgrade | ✅ | `auth-dialog.tsx` uses `postAuthUpgrade` for signup (session upgrade) vs `postAuthLogin`; single dialog with in-place `signin`/`signup` toggle (`switchMode`), `onSuccess` re-runs bootstrap. |
| Contextual gating routes to auth (no dead ends) | ✅ | `byok-form.tsx:201-221` anonymous branch → "Sign in to add a key" (`onRequestSignIn`); `settings-dialog.tsx:1235-1242` guest "Sign in to upgrade" instead of disabled checkout. |
| Friendly, non-enumerating auth validation | ✅ | `auth-dialog.tsx:35-69` `isValidEmail`, 429 copy, `INVALID_CREDENTIALS`→"Incorrect email or password", `EMAIL_TAKEN`, `ALREADY_UPGRADED`, 8-char rule; show/hide via `Eye/EyeOff` with label that avoids colliding with the field. |
| Guest hard-limit → convert, preserve thread | ❌ (FE surface) | Backend has `PLATFORM_GUEST_LIMIT` (PRD 08 §5.4), but the in-thread error surface (`assistant-message.tsx`) renders no Sign-up CTA for it (see B6). |
| Guest model-downgrade shown as substitution callout | ❌ (FE surface) | `PLATFORM_GUEST_DOWNGRADE` (PRD 08 §5.4/§5.7) not found rendered in FE; no guest-downgrade callout wired. |

### B3. BYOK key entry
| Practice | Status | Evidence |
|---|---|---|
| Never echo secret; masked fingerprint after save | ✅ | `byok-form.tsx` input is `type="password"`; stored key shown only as `currentKey.maskedKey` (`:303-310`); no plaintext reveal toggle (only a Clear button `:278-289`). |
| Input hardening | ✅ | `autoComplete="off" autoCorrect="off" spellCheck={false}` on the key field (`:269-271`); font-mono for legibility of what's typed without revealing stored value. |
| Trust cues (where key goes / billing effect) | ✅ | "Stored encrypted server-side; never sent to other providers." (`:372-374`); save/remove toasts explain billing switch (`:159-163`, `:185-189`); active-key line "Billed to your … key" (`:300-302`). |
| Saved-but-unusable state + replace/remove w/ confirm | ✅ | `keyUsable`/`ByokKeyStatus.usable` → "saved but not currently usable"; Replace / Remove with `confirmingDelete` guard (`:295-363`). |
| Guest gate | ✅ | Anonymous branch blocks storage, routes to sign-in (`:201-221`). |
| Provider select accessible/sized | ✅ | Labeled `<select>` 44px (`h-11`, `:238-255`). |
| Pre-save validation / test-key round-trip | 🟡 | No "Test key" affordance; validity is discovered only on `putByok` → error toast via `handleReportError` (maps `BYOK_KEY_INVALID`). No inline empty-vs-format validation beyond `trim().length===0` disabling Save. |

### B4. Settings / preferences organization
| Practice | Status | Evidence |
|---|---|---|
| Grouped, shallow hierarchy w/ collapsibles | ✅ | `settings-dialog.tsx` — tabs grouped into `SETTINGS_TAB_GROUPS` (Workspace/Knowledge/Reference); General panel `GroupHeading` clusters (Account & plan / Workspace / Privacy & data); BYOK, Project defaults, Advanced privacy, Custom instructions are `Collapsible` (progressive disclosure). |
| Mobile drill-down + desktop tab strip | ✅ | iOS-style grouped `nav` with `ChevronRight` rows + back button on mobile (`:1045-1095`); desktop `role="tablist"` rail (`:1098-1178`). |
| Keyboard nav / ARIA | ✅ | Roving tabindex, Arrow/Home/End handling (`:1136-1161`), `role=tab/tabpanel`, `aria-selected`, `tabPanelLabelProps`. |
| Deep-link + reset-on-open | ✅ | `initialTab` deep-link; open-transition snap (`:967-974`); folded panels mounted only while active so fetch/edit lifecycle resets on switch. |
| Privacy-first defaults, legible | ✅ | Training opt-in framed off-by-default ("never used to train … unless this is on", `:1509-1510`); Export/Delete rows (`:1549-1581`); retention picker with plain-language descriptions (`:311-319`); temporary-by-default + telemetry toggles. |
| Selection haptics / touch sizing | ✅ | `haptic("selection")` in `selectTab`; `[@media(hover:none)]:min-h-11` on segmented controls. |

### B5. Billing (checkout, comparison, credits/meter, upsell timing)
| Practice | Status | Evidence |
|---|---|---|
| Hosted Stripe Checkout + Portal launcher w/ busy/error | ✅ | `settings-dialog.tsx` `openCheckout`/`openPortal` → `createBillingCheckout`/`createBillingPortal` then `window.location.assign`; `billingBusy` states + `billingError` ("Billing could not be started."). |
| Capability-gated CTAs (no dead buttons) | ✅ | `proCheckoutAvailable`/`creditCheckoutAvailable`/`portalAvailable` gate the buttons; guests get "Sign in to upgrade" (`:1231-1287`). |
| Legible usage meter (USD/msg + bar + thresholds) | ✅ | `usage-meter.tsx` — `getUsagePresentation` computes spend-USD vs integer meter, `role=progressbar` with `aria-valuetext`, warning/critical/exhausted tones (0.8/0.95), BYOK "billed to key" pill; thresholds match PRD 08 §7. |
| Longitudinal spend analytics + export | ✅ | `spend-analytics-panel.tsx` — 7/30/90d ranges, daily bars, by-model, by-conversation, CSV+JSON export, cumulative-meter vs surviving-messages basis labeled. |
| Budget caps (monthly + per-conversation) | ✅ | `BudgetEditor` + `PerConversationBudgetEditor` (settings), enforced-cap disclosure when platform cap is tighter. |
| Plan comparison / "what Pro unlocks" before checkout | ❌ | Only a plan **badge** (`billing.planLabel`) + bare "Upgrade to Pro" button; no feature/price/caps comparison surface. (Consistent with the deliberate "no price in main chat UI" decisions `#232/#234/#241`, but no comparison exists even in Settings.) |
| Upsell attached to the constrained moment | 🟡 | Usage meter shows warning/critical tones and `UsageDetails` helper copy nudges "Bring your own key"/"Sign in", but **no Upgrade/Buy-credits CTA is attached to the meter or its warning**; the only checkout entry point is the Account section buttons. |

### B6. Rate-limit / quota / upgrade-prompt states
| Practice | Status | Evidence |
|---|---|---|
| Typed structured envelope in FE | ✅ | `apiClient.ts:83-114` `ApiError` carries `code/severity/title/body/actions[]/retryAfterMs/meta`. |
| 429 cooldown w/ live countdown + clear-at-zero | ✅ | `assistant-message.tsx:598-696` derives a deadline from `retryAfterMs`, ticks `secondsLeft`, disables Retry ("Try again in Ns"), announces via `sr-only role=status`. |
| Lead-with-outcome, calm styling (not red) | ✅ | Default title "Message couldn't finish"; destructive red reserved for `severity==="fatal"`, else warning role (`:587-594`). |
| SAFETY_BLOCKED transparent + request-review | ✅ | `:627-751` surfaces source/reason, Request review → `postModerationAppeal`, confirmation copy. |
| PROVIDER error → status link | ✅ | `PROVIDER_UPSTREAM` → "Check status" → `/status` (`:630-710`). |
| **`actions[]` (Upgrade / BYOK / Add credits / Sign up) rendered at the block** | ❌ | `error.actions[]` exists on `ApiError` but is **only rendered by `toast.tsx`** (`actions.map`), not by the in-thread error surface. The primary limit surfaces — `PLATFORM_BUDGET_EXCEEDED`, `PLATFORM_GUEST_LIMIT`, `PLATFORM_TIER_GATED` — show no inline conversion CTA. (Grep: `.actions` render only in `ui/toast.tsx`.) |
| Absolute reset time (`meta.reset_at`) countdown | 🟡 | Only relative `retryAfterMs` is consumed; `meta.reset_at` (PRD 08 §6.7) is not rendered as an absolute "Resets at" countdown. |
| Substitution ≠ error (guest downgrade callout) | ❌ | `PLATFORM_GUEST_DOWNGRADE` callout not wired in FE (see B2). |

---

## §C — Gaps & recommendations (prioritized)

**P0 — conversion + compliance load-bearing**

1. **Render `error.actions[]` inline at the limit (the missing upsell moment).** The backend already emits Upgrade / Add credits / BYOK / Sign-up actions on `PLATFORM_BUDGET_EXCEEDED`, `PLATFORM_GUEST_LIMIT`, `PLATFORM_TIER_GATED` (PRD 08 §3/§5.4), and `ApiError` already carries them — but `assistant-message.tsx` renders none of them (only `ui/toast.tsx` does). This is the single highest-leverage conversion gap: the upgrade prompt is absent exactly where intent peaks. *Fix:* map `error.actions[]` → account-aware buttons in the in-thread error surface (Sign up for guests, Upgrade/Buy credits/BYOK for free/pro), 2–3 max, preserving the thread. (A5/A6 best practice; PRD 08 §11 AC 4 "Guest limit → sign up → same chat preserved".)
2. **Restore an AI-interaction disclosure line.** The composer disclosure was removed (`#245`); PRD 05 §7.5 makes Art. 50(1) disclosure a **firm P0 EU launch gate (2 Aug 2026)** plus US good-practice. *Fix:* re-add an unobtrusive, dismissible "you're chatting with an AI" line (composer or first-run), or confirm it lives in a persistent legal footer. Flag for product/legal before EU launch.
3. **Wire the guest model-downgrade substitution callout (`PLATFORM_GUEST_DOWNGRADE`).** "Never silently downgrade" is the core wedge (PRD 00 §7, PRD 08 §5.4/§11 AC 5a); the FE currently shows nothing when a guest is moved to a weaker model. *Fix:* render the info-severity substitution callout naming the served model + "Sign up to keep the better model."

**P1 — funnel + decision quality**

4. **Add a plan-comparison surface before checkout.** Today it's a bare "Upgrade to Pro" with only a plan badge. *Fix:* a compact Free-vs-Pro comparison (models, caps, transparent USD overage, BYOK $0-markup) at the upgrade decision — the metered/credit mechanics are what 2026 buyers expect to see (research 05 Theme A). Keep it in Settings/checkout entry, consistent with the "no prices in main chat" decisions.
5. **Attach an upsell CTA to the usage meter's warning/critical states.** The meter tones and helper copy exist (`usage-meter.tsx`, `UsageDetails`) but carry no Upgrade/Buy-credits action at 80/95%. *Fix:* surface a deep-linked "View usage / Upgrade / Add credits" affordance on the warning banner (PRD 08 §5.4 `PLATFORM_BUDGET_WARNING` deep-link intent). This is the "warn before the wall" conversion moment.
6. **Add a first-week activation checklist surface.** PRD 05 §6.1 names the Day-1 success checklist the top retention lever; only a PWA install coachmark exists. *Fix:* a lightweight, dismissible checklist (first reply → saw attribution → opened usage → tried a control), instrumented as a funnel, not a nag.

**P2 — polish + robustness**

7. **BYOK "Test key" validation round-trip.** Validity is only discovered on save via provider error. *Fix:* optional test-connection button + inline invalid state, so a bad paste fails loudly before it's relied on (A3).
8. **Consume `meta.reset_at` for an absolute reset countdown** on budget/rate-limit states (not just relative `retryAfterMs`), for cross-session-correct "Resets at" copy (PRD 08 §6.7).
9. **Localize composed limit copy.** `assistant-message.tsx` composes some English strings directly; PRD 08 §3/§6 require count/reset copy composed from structured `meta` for i18n (P0 i18n baseline). Audit the error surface for hard-coded counts/reset text.

**Net read:** the *account/settings-side* of these journeys is strong and idiomatic — anonymous-first with in-place upgrade, hardened never-echo BYOK, a well-grouped progressively-disclosed settings hub, hosted Stripe checkout, legible meters, and longitudinal spend. The **weak seam is the conversion + transparency moment inside the thread**: the backend already produces actionable, typed limit envelopes and substitution codes, but the in-thread surface drops the `actions[]`, the guest-downgrade callout, and (post-#245) the AI disclosure. Closing P0 items 1–3 turns already-shipped backend capability into the visible upgrade/transparency moments the wedge promises, with no new data model.
