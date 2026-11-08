# Domain terms, English and short forms

## 既有术语与英文 — natural terms and purposeful English

Reach for the word that already exists in natural Chinese; a coinage fails the substitution test in **具体、稳定的词汇** in `SKILL.md`.

- **Needless English** (the more common mistake) — default to Chinese; most "engineer English" has a settled Chinese form, and English stays only when there is *no* natural Chinese equivalent: bare acronyms this field's own Chinese writing leaves in English (software `LLM` `API` `SPA` `CFG` `FSM` `MCP`; medicine `CT` `MRI` `PCR`; finance `IPO` `ETF` `ROE`) — the inventory belongs to the settled domain, so read it off that field, not off this list; a term the field's own Chinese writing keeps in English; a product name or trademark, an author name, a URL, or quoted English; or a literal code identifier / enum (kept verbatim under **Fidelity — protected spans** in `SKILL.md`).
- **Over-correcting** — don't strip genuine settled terms. A borrowed origin does not disqualify one. Currency decides, not etymology. And "looks technical" ≠ settled — a borrowed metaphor merely dressed as a term only *looks* established and still fails **修辞与措辞分量**; use a plain word.
- **Settledness is audience-relative** — a calque that is fixed vocabulary *inside* a field is not a coinage for that field's readers, and is opaque outside it. Keep the term where the reader owns it, expand it where they do not.

When a Chinese technical text keeps English terms, keep them stable and purposeful. Let English carry fixed names, acronyms, APIs, product names, and identifiers; let Chinese carry explanation, judgment, and action.

- **Needless English:** ✗ hatch 出一个对象 · 非法 transition → ✓ 生成一个对象 · 非法的状态转移 · ✗ 这个 capability 还不稳定 → ✓ 这个能力还不稳定
- **Coining / hard-translating:** ✗ 越界旗 → ✓ 越界标记
- **Settled terms:** `幂等` (idempotent), `回滚` (rollback), `死锁` (deadlock), `复盘` (from 围棋) are real, not coinages.
- **Borrowed metaphors:** `闸口` for a checkpoint, `接缝` for an integration boundary, `魔法整数` for "magic number" → 检查点 / 对接处 / 未说明的常量.
- **Audience:** `爆炸半径` is settled in 混沌工程 and SRE writing and correct there; for a general engineering or business audience write `影响范围`. The same test decides `对赌协议`、`举证责任倒置`、`双盲`.

## Settled short forms

Some short forms are the term rather than a compression of one, so **完整词形** does not expand them. Test one you have not met: can it stand on first mention as the head of its own sentence in a text where the long form never appears, and does it take compounds as a head? Both yes, write the short form. Either no, write the full form. The trap is the clip that only trails its own long form in the same passage, or survives only as a modifier. `提测`、`自测`、`拉齐`、`放量` are internal-process register; use the full form facing outward. `回归` alone is ambiguous with 逻辑回归 wherever machine learning is in scope.

- **Settled short forms:** `压测`、`灰度`、`埋点`、`扩缩容`、`联调`、`打标`、`兜底`; compounds as a head: `全链路压测` / `压测平台` / `压测报告`.
- **Internal-process register:** ✓ 这个需求周三提测，提测前大家先自测一遍 *(team chat)* · facing outward: ✓ 该功能将于周三提交测试
- **Clips that only trail a long form or survive as a modifier:** `冒烟` and `回归` look settled but are this, so write `冒烟测试` and `回归测试` on first mention — and `重录`、`手维护` are the same shape, which is why they are defects.

## Checks

- [ ] Every English token left in the text is a bare acronym this domain's own Chinese writing leaves in English, a term that field keeps in English, a product name or trademark, an author name, a URL, quoted English, or a code identifier; genuine settled terms are not over-translated.
- [ ] A term settled for this audience stays; one settled only inside a narrower field is expanded.
- [ ] A short form is kept only where it heads its own sentence on first mention and heads its own compounds, faces inward if it is internal-process register, and is not ambiguous in the field in scope.
