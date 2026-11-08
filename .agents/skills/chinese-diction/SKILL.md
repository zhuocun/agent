---
name: chinese-diction
description: >-
  Write and polish natural Chinese: every chat reply you write to the user in Chinese, however short, and any request, in any language, to write Chinese, translate into Chinese, polish Chinese wording, remove translationese, make Chinese sound more idiomatic, or choose better Chinese diction, in any human-facing prose — documents, reports, chat messages, announcements, notices, UI strings, marketing copy, contracts, or casual and creative writing. Fits word choice, phrasing, and sentence construction to the target register — professional, casual, or creative — and does not change document structure or section order. Do not use for the non-Chinese text of a translation out of Chinese, or for writing or editing agent-instruction files such as SKILL.md, prompts, workflows, or tool-routing docs.
---

# Chinese Diction

A **methodology, not a lookup table:** judge *any* phrasing by these principles. It works at the level of **diction, phrasing, and register** — word choice and sentence texture, not document structure or section order — in whatever register the text is meant for. Once active, it governs every later piece of Chinese prose you write, translate, or polish for a human reader, your own chat replies to the user included, across every later task in the session, including after a compaction or a resume, until the user explicitly turns it off; it never applies to agent-instruction files.

Priority order, highest first: **fidelity, preserved meaning, Chinese sentence structure, register fit, wording.** Fidelity outranks every wording rule: where a token is both a literal identifier and an English word with a settled Chinese form, it stays verbatim. Preserved meaning: polishing or translating keeps every claim the source makes, its advantages, tradeoffs and limitations included, and invents none; it weakens a claim only where **确定性与义务** finds its force unwarranted, never a stated limitation. Where two wording rules disagree, the one that restores information to the reader outranks the one that removes a word: expand the clipped form (**完整词形**) before trimming the figure (**修辞与措辞分量**), and keep concreteness that adds precision (**语域**) over plainness applied by habit.

It does not decide what a text says, its overall length, its structure or its format; where another instruction fixes those, follow it and apply this skill inside it. On word choice, phrasing, sentence construction, punctuation and register, the user's explicit instruction or standing preference and a style guide or glossary the destination sets take precedence over this skill except on **Fidelity — protected spans** and on a sentence its genre binds, such as one tying a legal consequence to its condition; a general writing rule not written for Chinese does not.

## Reference files

Read each file in full when its condition first holds, before applying its rules, and again after a compaction before applying them next:

- `references/terminology.md` (**既有术语与英文**): when the source or your draft contains a Latin-letter word or acronym, or draws on a specialized field such as software, medicine, finance or law.
- `references/claims.md`: when the text makes claims a reader will act on — technical, business, policy, medical, financial, academic.
- `references/obligation-texts.md`: when the text is a contract, policy, safety notice or regulatory text, or a procedure such as instructions, a runbook or a recipe.
- `references/requested-prose.md`: when the text is requested prose rather than a message to the user — an article, story, report, marketing copy, slogan or other piece of writing, delivered as a file or inline, including text you polish or translate.
- `references/display-text.md`: when the text fills a display slot — a button, menu item, table header, form label, empty state or other UI string.
- `references/translation-and-locale.md`: when you translate into Chinese, when the settled locale or script is other than mainland simplified, or when you convert between simplified and traditional.

## The core instinct

Write to these principles from the first draft. First settle five variables — from the user's message when writing, from the whole text and the user's message when polishing or translating; where nothing in front of you decides a setting, use its bracketed default, and ask the user only where a setting changes the wording and that default would not fit the text. When polishing, read the whole text before changing a word, then revise against the **用词** and **句式** sections without over-correcting (**语域**).

- **Register** — professional / casual / creative. [professional]
- **Medium and genre** — what the text is (chat message, notice, article, UI string, slide, email, contract, spoken script) and what it is for (inform, instruct, oblige, warn, persuade). [running prose, to inform]
- **Locale and script** — mainland / Taiwan / Hong Kong / Singapore, and simplified / traditional. [mainland simplified]
- **Relationship** — upward / downward / peer / outward to a client or the public. [peer]
- **Domain** — the field whose settled vocabulary governs. [none assumed]

With those settled, write the way a careful native writer writes in that register: **plainly and precisely, with nothing reaching to impress** — where plain means measured exposition in professional prose, conversational ease in casual prose, controlled imagery in creative writing. Before keeping any phrase, ask whether it is (a) English grammar in disguise, (b) an invented, hard-translated, or needlessly English word, (c) vividness the text's purpose doesn't need, (d) off-register — drifting from the target in either direction, or (e) reaching for more force than the claim warrants. If any, rewrite to the form the register calls for.

The one test that resolves most cases: **when two phrasings say the same thing, use the plainer, more measured one.** Prefer verbs with clear objects over abstract nouns. Plainer means clearer, not shorter.

Write Chinese punctuation fullwidth (，。：；、——……), with the quotation marks of the settled locale: “” for mainland and Singapore, 「」 for Taiwan and Hong Kong. Use halfwidth marks only inside identifiers, URLs, numbers and times (`20.5`、`9:00`) and quoted English, or as the surrounding non-Chinese sentence's own punctuation around a cited Chinese phrase. Between Chinese and Latin letters or digits, follow the destination's spacing convention where it sets one and the source's otherwise, apply it consistently, and keep each term's spelling consistent.

## Fidelity — protected spans

Some spans are **correctness, not wording**. The test: if altering the span could change what the text asserts, it is not wording. In software that means identifiers, enums, field/API names, code symbols, numbers, citations, author names, URLs; in other domains it means a statute or clause number (`《劳动合同法》第三十九条`), a drug name and its dose (`阿托伐他汀 20 mg`), a quoted figure with its unit, a trademark.

Copy them byte-for-byte; never translate, "tidy", **or** convert them between simplified and traditional. A 简繁 pass over the prose stops at every one of them. Translation into Chinese is the one bounded exception, set out in the translation file under **Reference files** (`Article 39` → `第三十九条`).

## 用词 — Word choice and register

### 具体、稳定的词汇 — vocabulary tests

Use abstraction only when it names a stable, reusable concept. A useful term points to one thing, keeps the same meaning throughout the text, and reduces repetition after being defined. Prefer established domain or technical terms; define any nonstandard term at first use in plain language, then reuse its exact name and meaning.

Reject shorthand that merely hides necessary information. If a phrase leaves the reader to infer the subject, condition, action, or result, expand it. Name the actual object (表、字段、参数、规则) and the actual action (读取、比较、存储、拒绝) instead of using a vague label. Do not ban abstract words mechanically; keep them when their reference is already clear and stable.

Apply three tests:

- **Reference:** Can the target reader identify exactly what the term denotes? Name the mechanism, not the mood.
- **Stability:** Does the term mean the same thing everywhere? Beware count-based shorthand (`三类异常`、`第四轴`); refer to members by name instead. Never let one name denote two different concepts, and never rotate names for one concept: pick one Chinese name for a recurring concept and reuse it across headings, tables, and cross-references.
- **Compression:** Does it shorten already-defined repetition rather than conceal unstated information? A productive suffix (`面`/`态`/`位`/`键`) makes coining feel free, but each coinage still owes a definition. To spot a coinage, replace the term with a plain description of what it denotes: if the text loses no information, the term was a coinage; name the thing plainly instead.

If any test fails, restore whatever concrete actor or object, condition, action, or result the target reader needs to understand the claim. Restore it only from the source text, its stated context, or facts the user supplied. Where none of these supplies it, keep the general wording and flag the gap to the user. Never supply an actor, condition, mechanism, or result the source does not state.

### 修辞与措辞分量 — earned vividness

**In communication with the user, do not use metaphor (including simile) or personification.** State the intended meaning directly.

Requested prose, inline or not, follows the requested-prose file under **Reference files** instead; surrounding explanations and progress updates remain communication. ✓ 走廊尽头的灯像一只睁着的眼，盯着我 *(suspense fiction)*

Verbatim source quotations keep their wording; proper names, identifiers and established technical terms keep their referents and domain meanings. Judge the meaning in context, not a word's origin. A literal adverb such as `物理上` ("physically") is not a metaphor.

Cut vividness, drama and violent wording used only for force or flavor, and words with the wrong connotations.

### 语域 — fit and consistency

Judge drift against the register, medium and relationship settled up front. There are **two opposite failures**, and over-correcting one produces the other; for a professional target, aim for the steady middle.

For a professional target, cut narrative openers, casual pronoun + 得, telegraphic fragments, over-strong adverbs (`根本`/`全靠`), dramatic time-moments (`那一刻`/`落下`) — **but** keep concrete, earned phrasing, and never reach for bookish filler (`悉数`/`须臾`/`业已`). When the target is casual, natural speech rhythm and interjections are correct, not defects — the failure there is stiffness leaking in (`进行沟通` where `聊一聊` belongs). When the target is creative, hold the piece's own voice steady. Whatever the target, *unintended* drift between registers within one text is the failure. Quoted speech, a marked aside, and a deliberate collision in creative prose each hold a register of their own on purpose — set them off as quotation or aside, and keep the surrounding text steady. **完整词形** measures against the target register, never against a shorter one.

- **Casual target:** ✗ 关于周末聚餐一事，请各位于明日前予以回复 → ✓ 咱们周末聚餐，大家明天之前回复一下哈
- **Quoted speech:** ✓ 他把报告推了回来，说：“这些数据我不认可。”之后我们重做了口径 · **marked aside:** ✓ 本季度营收同比增长 12%（说实话，这个数比我们预想的好），主要来自新客户 · **deliberate collision in requested creative writing:** ✓ 那年夏天，我和窗外的蝉达成了“战略合作”：它负责叫，我负责睡不着

### 确定性与义务 — measured claims and warranted force

Force or certainty the claim doesn't warrant reads as strident; default away from `只能` / `必须` / `一定` / `永远` / `完全` / `绝对` / `任何` / `一旦…就` / `根本`; prefer `通常` / `往往` / `多数` / `倾向于` / `可` / `需`. Keep an absolute only when the claim genuinely is absolute. In casual or creative prose an intensifier is often voice rather than a claim — judge it only where it asserts something.

Bound a strong claim rather than softening it away: pair a confident claim with scope, condition, evidence, or limitation, and with numbers include the measurement basis when it matters.

The opposite failure is over-hedging into mush: stacking softeners (`可能…也许…或许…`) or weakening the verb itself buries the claim. State the cause→effect flatly and quarantine each honest uncertainty into one measured quantifier on the part it qualifies, never two softeners on one part.

**Politeness:** distance is not hedging; politeness written upward or to a client does not spend the one-qualifier budget. **Deontic force:** a genre that imposes obligation — contract, policy, safety notice, regulatory text — keeps `应` / `不得` / `严禁`, within the limits the obligation file under **Reference files** sets.

- **Politeness, upward or to a client:** ✓ 是否方便本周内给我们一个初步意见 · ✓ 我们这边先核对一下数据，再给您答复
- **Deontic force:** ✓ 严禁在设备通电时拆卸外壳
- **Casual or creative voice:** ✓ 这也太好用了吧

### 完整词形 — complete forms in their medium

Trimming a word or phrase below its natural Chinese form to save characters reads as incomplete shorthand, not concision, which cuts redundant sentences and never a word's characters. Write the whole form; expand a phrase that sounds like a telegram or a variable name when read aloud.

*Bound by medium.* Casual chat has its own full forms, and so does a display slot (**Reference files**). Run this check over running prose in the settled medium; the read-aloud test judges a sentence, not a label. A settled industry short form is the term itself, not a clip; the terminology file under **Reference files** gives the test.

- ✗ 无需重录 → ✓ 无需重复录入
- **Casual chat:** ✓ 收到 · ✓ 在忙，晚点回复 · **button:** ✓ 另存为

## 句式 — Sentence construction

### 中文修饰与连接 — Chinese sentence structure

Chinese must carry Chinese sentence structure, not transliterated English structure. Tells: coordinate pre-modifiers run together without `、`, a packed pre-modifier, one stacking three or more of actor, place, time and manner around its verb, `被…所…`, connector pile-ups (`由于…因此…并且`), nominalized verbs (`进行…的处理`), parallelism forced for symmetry, subject drift mid-sentence.

The tell is not how many pre-modifiers a noun carries — a chain of compact coordinate modifiers is native Chinese. Separate run-together coordinates with `、` and tighten each to a bare predicate, or unstack a packed pre-modifier into a main clause. One or two adjuncts inside a modifier are fine.

- ✗ 一个在类型层无法产出非法结果的受约束的接口 → ✓ 一个受约束的、在类型层无法产出非法结果的接口

### 对比、拆句与衔接 — sentence-craft moves

- **`不是 A，而是 B` can be natural.** Keep it when A/B are comparable and the contrast is the point. Rewrite to `是 B，而非 A` only when it improves flow and does not invert emphasis; **front clause B**.
- **Split overloaded sentences.** Give a sentence that bundles definition, justification and instruction one sentence for each, unless its genre binds them, as in a clause tying a legal consequence to its condition. ✓ 甲方应于收到发票之日起三十日内付款；逾期的，按未付金额每日万分之五计付违约金
- **Weld related clauses with native paired connectives.** When two clauses are one causal or contrastive thought the reader would otherwise parse as separate facts, join them with `之所以…是因为…` / `与其…不如…`.

## Self-check

- [ ] Each reference file whose condition held was read in full before its rules were applied, and again after any compaction, and its own checks pass.
- [ ] **Fidelity — protected spans** are byte-for-byte unchanged, through any 简繁 conversion; punctuation, quotation marks, spacing and term spelling follow **The core instinct**.
- [ ] **Preserved meaning:** in polishing or translating, every claim of the source, its advantages, tradeoffs and limitations included, survives, weakened only where **确定性与义务** finds its force unwarranted and never a stated limitation; none was invented.
- [ ] **具体、稳定的词汇:** every nonstandard term, coinages included, passes the three tests, or was restored only from the source, its stated context or the user's facts, or was kept and flagged to the user.
- [ ] **修辞与措辞分量:** no metaphor, simile or personification in communication with the user; verbatim source quotations keep their wording, and names, identifiers and established terms their referents and domain meanings; nothing used only for force or flavor; connotations fit.
- [ ] **语域:** register, medium and relationship match what was settled and hold steady outside set-off quotation, asides and deliberate creative collisions.
- [ ] **确定性与义务:** no unwarranted absolute, and obligation genres keep `应` / `不得` / `严禁`; strong claims bounded; at most one softener on any part; politeness upward or to a client not counted as hedging.
- [ ] **完整词形:** no clipped words in running prose.
- [ ] **中文修饰与连接:** no tell remains. **对比、拆句与衔接:** contrast keeps its emphasis; a sentence bundling definition, justification and instruction is split unless its genre binds them, as in a clause tying a legal consequence to its condition; one-thought clauses take a native paired connective.
- [ ] Re-read cold: no sentence needed a second pass to parse.
