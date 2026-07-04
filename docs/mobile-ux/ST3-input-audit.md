# ST3 — Mobile input-zoom & keyboard-scroll audit

**Scope:** every `<input>`, `<textarea>`, `contenteditable`, and `<select>` under
`web/src/components/**`.

**Why:** iOS Safari auto-zooms the page when a focused text field has a computed
`font-size < 16px`. The fix is to render fields at ≥16px on mobile. The repo
convention is Tailwind `text-base md:text-sm` — 16px below the `md` breakpoint
(768px, i.e. all phones), 14px on desktop. Font-size reference (Tailwind v4
defaults, unchanged in `web/src/app/globals.css` `@theme`): `text-sm` = 14px,
`text-base` = 16px, `text-lg` = 18px, `text-[1.0625rem]` = 17px. Only
`--text-2xs` (11px) is customized.

**Method:** static read of the class strings on every control (read-only; no code
changed). Mobile size = the value that applies with **no** `md:` prefix active.

---

## Findings — fields below 16px on mobile

Three `<select>` controls render at **14px** (`text-sm` with no `md:` override),
so they are below the 16px threshold on phones:

| # | File | Line | Control | Class (mobile size) |
| - | ---- | ---- | ------- | ------------------- |
| 1 | `web/src/components/chat/byok-form.tsx` | 248 | Provider `<select>` | `… text-sm …` → **14px** |
| 2 | `web/src/components/chat/settings-dialog.tsx` | 576 | Project picker `<select>` (`data-testid="project-settings-select"`) | `… text-sm …` → **14px** |
| 3 | `web/src/components/chat/command-palette.tsx` | 92 | `FILTER_SELECT_CLASS`, applied to the **Model** (623), **Project** (644) and **Tag** (726) selects | `… text-sm …` → **14px** |

No `<input>`, `<textarea>`, or `contenteditable` field is below 16px on mobile.

> **Note on `<select>` and zoom.** iOS Safari's focus-zoom is most reliably
> triggered by text-entry fields (`<input type=text/email/number/search/…>` and
> `<textarea>`), because focusing them starts inline editing. Focusing a
> `<select>` opens the native picker wheel rather than an inline caret, and on
> recent iOS the page does **not** always zoom for a `<select>` alone. The three
> rows above are still listed because the audit criterion is a hard
> `font-size ≥ 16px` on every `<select>`, and these are the only controls that
> miss it. To bring them in line with the rest of the surface, change `text-sm`
> → `text-base md:text-sm` (and drop any fixed `h-9` in favor of the taller
> mobile row used elsewhere if touch-target parity is also wanted).

---

## Compliant fields (≥16px on mobile) — verified

**Already-known baselines (re-confirmed):**

- Composer textarea — `web/src/components/chat/composer.tsx:1292` — `text-[1.0625rem]` (17px) → `md:text-[0.9375rem]`.
- User-message edit textarea — `web/src/components/chat/user-message.tsx:219` — `text-[1.0625rem]` (17px).
- Sidebar rename input — `web/src/components/chat/sidebar.tsx:577` — `text-base md:text-sm`.
- Sidebar search input — `web/src/components/chat/sidebar.tsx:1578` — `text-base md:text-sm`.

**The rest of the requested surfaces:**

| File | Control(s) | Line(s) | Mobile size |
| ---- | ---------- | ------- | ----------- |
| `settings-dialog.tsx` | Budget-cap `input[type=number]` | 417 | `text-base md:text-sm` ✅ |
| `settings-dialog.tsx` | Conversation-cap `input[type=number]` | 496 | `text-base md:text-sm` ✅ |
| `settings-dialog.tsx` | Project-instructions `textarea` | 710 | `text-base md:text-sm` ✅ |
| `settings-dialog.tsx` | Project-cap `input[type=number]` | 769 | `text-base md:text-sm` ✅ |
| `settings-dialog.tsx` | Custom-instructions `textarea` | 1417 | `text-base md:text-sm` ✅ |
| `byok-form.tsx` | API-key `input[type=password]` | 276 | `text-base md:text-sm` ✅ |
| `auth-dialog.tsx` | Email `input` | 184 | `text-base md:text-sm` ✅ |
| `auth-dialog.tsx` | Password `input` | 207 | `text-base md:text-sm` ✅ |
| `memory-dialog.tsx` | Add-fact `textarea` | 191 | `text-base md:text-sm` ✅ |
| `memory-dialog.tsx` | Edit-fact `textarea` | 240 | `text-base md:text-sm` ✅ |
| `template-library-dialog.tsx` | Title / body / description add `input`+`textarea` | 190, 200, 211 | `text-base md:text-sm` ✅ |
| `template-library-dialog.tsx` | Title / body / description edit `input`+`textarea` | 260, 270, 279 | `text-base md:text-sm` ✅ |
| `share-dialog.tsx` | Public-link `input` (readonly) | 207 | `text-base md:text-sm` ✅ |
| `command-palette.tsx` | Main search `input` | 590 | `text-lg` (18px) ✅ |
| `command-palette.tsx` | Cost min/max `input[type=number]` (`FILTER_INPUT_CLASS`) | 88, 673, 688 | `text-base md:text-sm` ✅ |
| `command-palette.tsx` | Date from/to `input[type=date]` (`FILTER_DATE_INPUT_CLASS`) | 90, 704, 715 | `text-base md:text-sm` ✅ |
| `sidebar.tsx` | Project-name `input` | 2370 | `text-base md:text-sm` ✅ |
| `sidebar.tsx` | Tag-name `input` | 2466 | `text-base md:text-sm` ✅ |

**`spend-analytics-panel.tsx`:** contains **no** form controls — it is a
display-only panel (`text-sm`/`text-base` on `<p>`/`<span>` only). Nothing to
fix.

**`contenteditable`:** no real editable element exists anywhere in
`components/**`. The only `contenteditable` tokens are inside `closest(...)`
selector strings in `assistant-message.tsx:277` and `user-message.tsx:98`
(click-to-activate guards), not attributes on rendered nodes.

---

## Keyboard-scroll check — focused field vs. the soft keyboard

iOS's soft keyboard does **not** shrink `dvh`, so a bottom-pinned sheet slides
*under* the keyboard unless it is lifted. Two mechanisms cover this:

1. **Sheet lift.** `web/src/components/ui/dialog.tsx:92-101` reads
   `useVisualViewport().keyboardInset` and, on mobile, sets
   `style={{ bottom: keyboardInset, maxHeight: calc(min(90dvh, --dialog-max-h) - keyboardInset) }}`.
   The whole sheet is pushed above the keyboard and its cap trimmed to match.
   The command palette reimplements the same lift for its custom sheet at
   `command-palette.tsx:351-360` (`bottom: keyboardInset`, `maxHeight: calc(80dvh - keyboardInset)`).
2. **Internal scroll container.** With the sheet capped above the keyboard, a
   `overflow-y-auto` body lets the browser's native focus-scroll bring the
   focused field into the visible region.

| Dialog | Lift | Scroll container | Focused field stays above keyboard? |
| ------ | ---- | ---------------- | ----------------------------------- |
| `settings-dialog.tsx` | ✅ (DialogContent) | ✅ body `overflow-y-auto` at 1048 & 1186 | ✅ |
| `memory-dialog.tsx` | ✅ | ✅ body `overflow-y-auto` at 158 | ✅ |
| `template-library-dialog.tsx` | ✅ | ✅ body `overflow-y-auto` at 176 | ✅ |
| `byok-form.tsx` (mounted in Settings, `settings-dialog.tsx:1323`) | ✅ | ✅ inside Settings scroll body | ✅ |
| `command-palette.tsx` | ✅ (own lift 351) | ✅ body `overflow-y-auto` at 612 | ✅ |
| `auth-dialog.tsx` | ✅ | ⚠️ **none** — `DialogContent className="sm:max-w-md"` (159), no `overflow-y-auto`; default `overflow: visible` | Portrait: ✅ (email/password sit near the top, above the keyboard). ⚠️ landscape / very short viewport: no scroll fallback, so if the lifted `maxHeight` is shorter than the form the lower field/submit can overflow the sheet. |
| `share-dialog.tsx` | ✅ | ⚠️ **none** — `DialogContent className="sm:max-w-md"` (177) | ✅ single readonly link input sits near the top; low risk. |

### Dialogs where a focused field could sit under the keyboard

- **None** in the strict sense — every listed dialog is lifted above the
  keyboard by the shared `DialogContent`/palette inset logic.
- **Low-risk caveat:** `auth-dialog.tsx` and `share-dialog.tsx` have **no
  dedicated internal `overflow-y-auto` scroll region**. They rely entirely on
  the whole-sheet lift plus short content. In portrait this keeps their fields
  visible, but on a short/landscape viewport the trimmed `maxHeight` can be
  smaller than the content and, with the default `overflow: visible`, the lower
  parts (auth password/submit) can spill past the sheet with no scroll to
  recover. Adding a `flex flex-col overflow-hidden` shell + `overflow-y-auto`
  body (the pattern the other dialogs already use) would remove the caveat.

---

## Summary

- **3 controls < 16px on mobile**, all `<select>` at `text-sm` (14px):
  `byok-form.tsx:248`, `settings-dialog.tsx:576`, and the shared
  `FILTER_SELECT_CLASS` (`command-palette.tsx:92`) used by 3 palette selects.
- **All text `<input>`/`<textarea>` are ≥16px on mobile.** No real
  `contenteditable` exists. `spend-analytics-panel.tsx` has no fields.
- **Keyboard scroll:** no dialog places a focused field under the keyboard;
  `auth-dialog.tsx` and `share-dialog.tsx` lack an internal scroll container and
  lean on the sheet lift + short content (low-risk in portrait only).
