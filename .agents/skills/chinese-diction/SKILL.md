---
name: chinese-diction
description: >-
  Write natural Chinese that fits its target register — professional, casual, or creative — at the word-choice, phrasing, and register level. Use for every chat reply you write to the user in Chinese, however short, and when the user, in any language, asks you to write Chinese, translate into Chinese, polish Chinese wording, remove translationese, make Chinese sound more idiomatic, or choose better Chinese diction, in any human-facing prose — documents, reports, chat messages, announcements, notices, UI strings, marketing copy, contracts, or casual and creative writing. This improves wording, phrasing, and register only, not document structure or section order. Do not use for agent-instruction files such as SKILL.md, prompts, workflows, or tool-routing docs.
---

# Chinese Diction

A **methodology, not a lookup table.** It teaches the few principles behind good Chinese prose so you can judge *any* phrasing on your own, rather than match a fixed list of fixes. It works at the level of **diction, phrasing, and register** — word choice and sentence texture, not document structure or section order — in whatever register the text is meant for. Once active, it governs every later piece of Chinese prose you write, translate, or polish for a human reader, your own chat replies to the user included, across every later task in the session, including after a compaction or a resume, until the user explicitly turns it off; it never applies to agent-instruction files.

Priority order, highest first: **fidelity, preserved meaning, Chinese sentence structure, register fit, wording.** Fidelity outranks every wording rule: where a token is both a literal identifier and an English word with a settled Chinese form, it stays verbatim — `config 文件` keeps `config` because it names an actual file, while a bare `capability` in running prose becomes `能力` under **既有术语与英文**. Where two wording rules disagree, the one that restores information to the reader outranks the one that removes a word: expand the clipped form (**完整词形**) before trimming the figure (**修辞与措辞分量**), and keep earned concreteness (**语域**) over reflexive plainness.

## The core instinct

Settle five variables first. Infer each from the text and the ask — for a chat reply to the user, from the user's own message; where nothing in front of you decides a setting, use its bracketed default, and ask the user only where a setting changes the wording and that default would not fit the text.

- **Register** — professional / casual / creative. [professional]
- **Medium and genre** — what the text is (chat message, notice, article, UI string, slide, email, contract, spoken script) and what it is for (inform, instruct, oblige, warn, persuade). [running prose, to inform]
- **Locale and script** — mainland / Taiwan / Hong Kong / Singapore, and simplified / traditional. Two axes, not one. [mainland simplified]
- **Relationship** — upward / downward / peer / outward to a client or the public. [peer]
- **Domain** — the field whose settled vocabulary governs. [none assumed]

With those settled, write the way a careful native writer writes in that register: **plainly and precisely, with nothing reaching to impress** — where plain means measured exposition in professional prose, conversational ease in casual prose, controlled imagery in creative prose. Before keeping any phrase, ask whether it is (a) English grammar in disguise, (b) an invented, hard-translated, or needlessly English word, (c) vividness the text's purpose doesn't need, (d) off-register — drifting from the target in either direction, or (e) reaching for more force than the claim warrants. If any, rewrite to the form the register calls for.

The one test that resolves most cases: **when two phrasings say the same thing, use the plainer, more measured one.** A figure of speech earns its place by adding *precision* — or, in creative prose, an effect the piece genuinely needs; an absolute word (`只能`/`必须`/`一定`) earns its place only when the claim truly is absolute. If they add mere flavor or force, cut them. Prefer verbs with clear objects over abstract nouns: say what is being identified, compressed, merged, verified, or exposed — `识别改动类型`、`压缩返回内容`、`返回搜索任务清单`、`生成验证核查清单`、`定位受影响文件` over `提升能力`、`优化体验`、`赋能增长`. Plainer means clearer, not shorter — write each word in its complete, natural form, never a clipped shorthand.

## Fidelity — protected spans

Some spans are **correctness, not wording**. The test: if altering the span could change what the text asserts, it is not wording. In software that means identifiers, enums, field/API names, code symbols, numbers, citations, author names, URLs; in other domains it means a statute or clause number (`《劳动合同法》第三十九条`), a drug name and its dose (`阿托伐他汀 20 mg`), a quoted figure with its unit, a trademark.

Copy them byte-for-byte; never translate, "tidy", **or** convert them between simplified and traditional. A 简繁 pass over the prose stops at every one of them. Translation into Chinese is the one bounded exception: render a drug's generic name and a statute's title in their official Chinese form where one exists (`atorvastatin` → `阿托伐他汀`), and write a clause number in the target citation's form without changing its value (`Article 39` → `第三十九条`). Keep identifiers, trademarks, every other number, units, doses, and URLs verbatim.

## 用词 — Word choice and register

### 具体、稳定的词汇 — vocabulary tests

#### Methodology

Use abstraction only when it names a stable, reusable concept. A useful term points to one thing, keeps the same meaning throughout the text, and reduces repetition after being defined. Prefer established domain or technical terms; define any nonstandard term at first use in plain language, then reuse its exact name and meaning.

Reject shorthand that merely hides necessary information. If a phrase leaves the reader to infer the subject, condition, action, or result, expand it. Name the actual object (`table`, `field`, `API`, `rule`) and the actual action (`read`, `compare`, `store`, `reject`) instead of using a vague label. Do not ban abstract words mechanically; keep them when their reference is already clear and stable.

Apply three tests:

- **Reference:** Can the target reader identify exactly what the term denotes? Name the mechanism, not the mood.
- **Stability:** Does the term mean the same thing everywhere? Beware count-based shorthand (`三类异常`、`第四轴`) — it binds the name to a mutable tally that silently breaks when items are added or merged; refer to members by name instead. Never let one name denote two different concepts, and never rotate names for one concept: pick one Chinese name for a recurring concept and reuse it across headings, tables, and cross-references, never swapping synonyms for literary variety.
- **Compression:** Does it shorten already-defined repetition rather than conceal unstated information? A productive suffix (`面`/`态`/`位`/`键`) makes coining feel free, but each coinage still owes a definition.

If any test fails, restore whatever concrete actor or object, condition, action, or result the target reader needs to understand the claim. Restore it only from the source text, its stated context, or facts the user supplied. Where none of these supplies it, keep the general wording and flag the gap to the user. Never supply an actor, condition, mechanism, or result the source does not state.

**Terms may compress what has already been defined; they must never hide what has not been stated.**

#### Examples

- **Reference:** `上下文不足`、`影响范围评估不足`、`组件信息依赖 UI 打标`、`返回内容过长` over vague phrasing like `效果不好`、`提效不明显`、`当前存在一些问题`. ✗ 该员工需在试用期内达成既定目标 → ✓ 该员工需在试用期内完成客户回访、提交月度报表并参加入职培训 *(where the source names these)*
- **Stability:** ✗ 本学期重点考核前两个维度 → ✓ 本学期重点考核课堂参与和作业完成情况.
- **Compression:** ✗ 该字段落入失败面 → ✓ 此字段属于失败场景的处理范围

### 既有术语与英文 — natural terms and purposeful English

#### Methodology

Reach for the word that already exists in natural Chinese. Four ways it goes wrong:

- **Coining / hard-translating** — a coinage borrows a shape that looks like a term and asks the reader to supply the meaning; name the thing plainly instead. The test: replace the term with a plain description of what it denotes — if the text loses no information, the term was a coinage. The productive suffixes (`面`/`态`/`位`/`键`) are where this shape appears most.
- **Needless English** (the more common mistake) — default to Chinese; most "engineer English" has a settled Chinese form, and English stays only when there is *no* natural Chinese equivalent: bare acronyms this field's own Chinese writing leaves in English (software `LLM` `API` `SPA` `CFG` `FSM` `MCP`; medicine `CT` `MRI` `PCR`; finance `IPO` `ETF` `ROE`) — the inventory belongs to the settled domain, so read it off that field, not off this list; a term genuinely canonical as English in the field (`agent`); a product name or trademark, an author name, a URL, or quoted English; or a literal code identifier / enum (kept verbatim under **Fidelity — protected spans**).
- **Over-correcting** — don't strip genuine settled terms. A borrowed origin does not disqualify one. Currency decides, not etymology. And "looks technical" ≠ settled — a borrowed metaphor merely dressed as a term only *looks* established and still fails **修辞与措辞分量**; use a plain word.
- **Settledness is audience-relative** — a calque that is fixed vocabulary *inside* a field is not a coinage for that field's readers, and is opaque outside it. Keep the term where the reader owns it, expand it where they do not.

When a Chinese technical text keeps English terms, keep them stable and purposeful. Let English carry fixed names, acronyms, APIs, product names, and identifiers; let Chinese carry explanation, judgment, and action. Between Chinese and Latin letters or digits, follow the destination's spacing convention where it sets one and the source's otherwise, apply it consistently, and keep each term's spelling consistent.

#### Examples

- **Coining / hard-translating:** ✗ 越界旗 → ✓ 越界标记
- **Needless English:** ✗ hatch 出一个对象 · 非法 transition → ✓ 生成一个对象 · 非法的状态转移
- **Settled terms:** `幂等` (idempotent), `回滚` (rollback), `死锁` (deadlock) are real, not coinages; `复盘` comes from 围棋 and is now the unglossed word for a review in first-party documentation and industry guidance.
- **Borrowed metaphors:** `闸口` for a checkpoint, `接缝` for an integration boundary, `魔法整数` for "magic number" → 关口 / 对接处 / 未说明的常量.
- **Audience:** `爆炸半径` is settled in 混沌工程 and SRE writing and correct there; for a general engineering or business audience write `影响范围`. The same test decides `对赌协议`、`举证责任倒置`、`双盲`.

### 修辞与措辞分量 — earned vividness

#### Methodology

Reaching for vividness the meaning doesn't need is the most common failure in "clever" drafts. Several sub-forms, one principle: cut any figure that adds only flavor.

A metaphor borrowed from another field names nothing; state the mechanism and its bound. A literal adverb is not a metaphor: 物理上 = "physically" is literal — keep it.

The same instinct disposes of drama, violent verbs, and wrong-connotation words. In creative registers the bar moves, not the principle: imagery that produces the intended effect is earned; the empty or reflexive figure — and the wrong-connotation word — fails in every register. Persuasive genres get the same carve-out under the same bound: marketing copy and a pitch may reach for a figure, but it must still name something the reader can check.

#### Examples

- **Personification** — ✗ 会自证、会模拟的活对象 → ✓ 能自我校验和模拟的实体
- **Branded label** (a plain idea dressed as a coined term) — ✗ 新基座的原语 → ✓ 新系统的基本构件
- **Noun-as-metaphor** — ✗ 这轮降息是市场的强心针 → ✓ 这轮降息在短期内提振了市场信心
- **Slogan / hyperbole** — ✗ 回滚到最后一毫秒 → ✓ 操作前均可回滚
- **Business/strategy slogans** — ✗ 全面提升 AI 编码效率、赋能业务高质量增长 → ✓ 降低组件选择和场景匹配成本、提高上下文完整性、减少影响范围遗漏 *(where the source names these)*
- **Creative target** (the bar moves, the principle does not) — ✗ 夜色如同一位沉默的巨人，笼罩着整座城市 → ✓ 夜色漫过屋脊，一点点笼罩住整座城市 *(the simile decorates; 漫过 carries the direction and pace, so it earns its place)*
- **Drama, violent verbs, and connotation:** `重生`→`重写后`; `砸`/`杀死`/`焊死`→`投入`/`消除`/`锁定`; `廉价`→`低成本` (cheap carries "shoddy"), `投机性`→`没把握` (投机 means opportunism, not *speculative*), `一刀切`→`彻底分开` (一刀切 is pejorative) when you mean a clean separation.
- **Persuasive genres:** ✓ 十分钟就能上手，无需通读文档 over ✗ 开启高效协作新体验

### 语域 — fit and consistency

#### Methodology

Judge drift against the register, medium and relationship settled up front. The settled trio, not the words, decides. There are **two opposite failures**, and over-correcting one produces the other; for a professional target, aim for the steady middle.

For a professional target, cut narrative openers, casual pronoun + 得, telegraphic fragments, over-strong adverbs (`根本`/`全靠`), dramatic time-moments (`那一刻`/`落下`) — **but** keep concrete, earned phrasing (a vivid "一分钟看懂" beats a flat "高效"), and never reach for bookish filler (`悉数`/`须臾`/`业已`). De-colloquial is not the same as formal. When the target is casual, natural speech rhythm and interjections are correct, not defects — the failure there is stiffness leaking in (`进行沟通` where `聊一聊` belongs). When the target is creative, hold the piece's own voice steady. Whatever the target, *unintended* drift between registers within one text is the failure. Quoted speech, a marked aside, and a deliberate collision in creative prose each hold a register of their own on purpose — set them off as quotation or aside, and keep the surrounding text steady. **完整词形** measures against the target register, never against a shorter one.

#### Examples

「他得先弄清」 is a defect in a professional document and correct in a peer chat.

- ✗ too casual / narrative: 新来的销售只说一句话：…… ｜ 他得先弄清 ｜ 全靠人工算
- ✗ too stiff / 八股：销售人员仅须以一语陈明其诉求 ｜ 其须先行明确 ｜ 悉数依赖人工核算
- ✓ right: 销售只需用一句话说明诉求 ｜ 需先确定 ｜ 依赖人工计算
- **casual target:** ✗ 关于周末聚餐一事，请各位于明日前予以回复 → ✓ 咱们周末聚餐，大家明天之前回复一下哈 *(the casual target licenses 咱们, the loose clause order and the final 哈 — it does not license a clipped word: 回复 stays whole.)*

Quoted speech: ✓ 他把报告推了回来，说：“这些数据我不认可。”之后我们重做了口径 · a marked aside: ✓ 本季度营收同比增长 12%（说实话，这个数比我们预想的好），主要来自新客户 · a deliberate collision: ✓ 那年夏天，我和窗外的蝉达成了“战略合作”：它负责叫，我负责睡不着

### 确定性与义务 — measured claims and warranted force

#### Methodology

Reaching for force or certainty the claim doesn't warrant reads as strident or naive; measured phrasing reads as mature and more credible. Default away from `只能` / `必须` / `一定` / `永远` / `完全` / `绝对` / `任何` / `一旦…就` / `根本`; prefer `通常` / `往往` / `多数` / `倾向于` / `可` / `需`.

Bound a strong claim rather than softening it away: pair a confident claim with scope, condition, evidence, or limitation, and with numbers include the measurement basis when it matters.

The opposite failure is over-hedging into mush: stacking softeners (`可能…也许…或许…`) or weakening the verb itself buries the claim. State the cause→effect flatly and quarantine each honest uncertainty into one measured quantifier on the part it qualifies, never two softeners on one part.

Two carve-outs. **Deontic force:** where the settled genre is one that imposes obligation — contract, policy, safety notice, regulatory text, but not a procedure such as instructions, a runbook or a recipe, whose required steps take `需` while a safety warning inside it stays a safety notice — the categorical word *is* the correct form and softening it is a defect. Contract, policy and safety Chinese carries `应` / `不得` / `严禁`, not `需` / `通常`. **Politeness:** distance is not hedging; politeness written upward or to a client does not spend the one-qualifier budget.

Keep an absolute only when the claim genuinely is absolute, while a step a procedure requires is an instruction, not such a fact, and takes `需`. The rule is don't reach for force you don't need, not "never be definite" — and equally, don't drown a real finding in stacked maybes. In casual or creative prose an intensifier is often voice rather than a claim — judge it only where it asserts something.

#### Examples

- ✗ 这一步只能依赖人工计算 → ✓ 这一步依赖人工计算
- ✗ 一旦接近关口，就必须切换到人工 → ✓ 接近关口时，需要切换到人工

Prefer `在该测试场景下可降低请求耗时`、`代码完成度 = 正确实现数 / 功能点总数`、`准确性有限` over `全面提升准确性`、`仍有优化空间`.

- ✗ 相关信息如果不在 AI 的注意力焦点内，可能也许不太会被考虑到 → ✓ 相关信息若不在 AI 的注意力焦点内，往往不会被纳入考虑

- **Deontic force:** ✓ 严禁在设备通电时拆卸外壳 · ✓ 未经甲方书面同意，乙方不得转让本协议项下的权利和义务
- **Politeness, upward or to a client:** ✓ 是否方便本周内给我们一个初步意见 · ✓ 我们这边先把口径对齐
- **Absolute fact:** "盖章后不可逆" is a fact, and hedging it would be false.
- **Casual or creative voice:** ✓ 这也太好用了吧

### 完整词形 — complete forms in their medium

#### Methodology

Trimming a word or phrase below its natural Chinese form to save characters reads as incomplete shorthand, not concision, which cuts redundant sentences and never a word's characters. Write the whole form.

Prefer the complete, natural form over the clipped one. Read it aloud — if it sounds like a telegram or a variable name, expand it. A clip also goes ambiguous.

*Bound by medium.* A display slot has its own complete form: a button, menu item, table header, form label or empty state is correctly short, and expanding it is the error. Casual chat likewise has its own full forms. Run this check over running prose in the settled medium; the read-aloud test judges a sentence, not a label.

*A settled short form is not a clip.* Some short forms are the term rather than a compression of one. Test one you have not met: can it stand on first mention as the head of its own sentence in a text where the long form never appears, and does it take compounds as a head? Both yes, write the short form. Either no, write the full form. The trap is the clip that only trails its own long form in the same passage, or survives only as a modifier. `提测`、`自测`、`拉齐`、`放量` are internal-process register; use the full form facing outward. `回归` alone is ambiguous with 逻辑回归 wherever machine learning is in scope.

#### Examples

- ✗ 无需重录 → ✓ 无需重复录入
- ✗ 交人把关 → ✓ 交由负责人把关
- ✗ 手维护 config 文件的持续漂移 → ✓ 需手动维护的 config 文件的持续漂移

- **Complete forms:** `交由负责人` / `重复录入` / `手动维护` over `交人` / `重录` / `手维护`.
- **Ambiguous clip:** 「晚点回」 reads as 回家 or 回复, and the reader cannot tell which.
- **Display slots and email:** a button reads ✓ 另存为, not ✗ 另存为其他文件; an empty state reads ✓ 暂无数据, while the same idea in an email is ✓ 目前还没有相关数据.
- **Casual chat:** ✓ 收到 · ✓ 在忙，晚点回复
- **Settled short forms:** `压测`、`灰度`、`埋点`、`扩缩容`、`联调`、`打标`、`兜底`、`提测`、`自测`; compounds as a head: `全链路压测` / `压测平台` / `压测报告`. 阿里云 PTS 的产品概述通篇用“压测”，全篇零次“压力测试”.
- **Clips that only trail a long form or survive as a modifier:** `冒烟` and `回归` look settled but are this, so write `冒烟测试` and `回归测试` on first mention — and `重录`、`手维护` above are the same shape, which is why they are defects.

## 句式 — Sentence construction

### 中文修饰与连接 — Chinese sentence structure

#### Methodology

Chinese must carry Chinese sentence structure, not transliterated English structure. Tells: coordinate pre-modifiers run together without `、`, a pre-modifier stacking three or more of actor, place, time and manner around its verb, `被…所…`, connector pile-ups (`由于…因此…并且`), nominalized verbs (`进行…的处理`), parallelism forced for symmetry, subject drift mid-sentence.

The tell is not how many pre-modifiers a noun carries — a chain of compact coordinate modifiers is native Chinese. Two things are: coordinate pre-modifiers run together with no `、` between them, and a single pre-modifier that stacks three or more of actor, place, time and manner around its verb (`由甲方…三十日内…以书面形式提出的`). Separate the coordinates with `、` and tighten each to a bare predicate, or unstack the packed modifier into a main clause. One or two adjuncts inside a modifier are fine, which is why a scope-bearing contract phrase stays attached.

#### Examples

- ✗ 一个在类型层无法产出非法结果的受约束的接口 → ✓ 一个无法产出非法类型结果的、受约束的接口
- ✗ 由甲方在本协议签署之日起三十日内以书面形式提出的解除通知 → ✓ 该解除通知由甲方在本协议签署之日起三十日内以书面形式提出

The 接口 line separates the coordinates and tightens each to a bare predicate; the 解除通知 line unstacks the packed modifier into a main clause.

- **Scope-bearing contract phrase:** ✓ 本协议项下由甲方提供的、经乙方书面确认的技术资料

### 对比、拆句与衔接 — sentence-craft moves

#### Methodology

- **`不是 A，而是 B` can be natural.** Keep it when A/B are comparable and the contrast is the point. Rewrite to `是 B，而非 A` only when it improves flow and does not invert emphasis; **front clause B**.
- **Split overloaded sentences.** One that bundles definition + justification + instruction reads as three; give each its own sentence — unless the genre binds them, as a contract clause does, where a condition and its consequence belong in one sentence.
- **Weld related clauses with native paired connectives.** When two clauses are one causal or contrastive thought the reader would otherwise parse as separate facts, join them with `之所以…是因为…` / `与其…不如…` — the Chinese way to mark the link explicitly. This is the positive counterpart to **中文修饰与连接**'s warning against stacked Western connectors (`由于…因此…并且`): one native connective binds, a pile-up of them is translationese.

#### Examples

- **Contrast:** ✓ 是取代表单，而非用 AI 优化表单
- **Contract clause:** ✓ 甲方应于收到发票之日起三十日内付款；逾期的，按未付金额每日万分之五计付违约金
- **Native paired connectives:** ✗ 精度有限。上下文不足 → ✓ 之所以精度有限，是因为上下文不足

### 问题、机制与主张 — actionable prose patterns

#### Methodology

Use these wherever the prose makes claims a reader will act on — technical, business, policy, medical, financial, academic. The examples below are software; the patterns are not. They do not govern casual chat, taglines, or creative prose, where bounding a claim is not the job.

1. **Bridge problem to method through the mechanism.** When moving from problem to solution, use a short bridge: name the surface problem, state the underlying mechanism the source gives, then introduce the method.
2. **Acknowledge alternatives with source-backed precision.** If the source says another option has an advantage, keep it before stating the boundary; do not invent balance for tone.
3. **Let memorable phrases earn their place.** If a motif is only catchy, replace it with the concrete mechanism the source states.

#### Examples

- **Genre bounds:** a tagline is correctly ✓ 十分钟就能上手，无需通读文档 with no scope clause attached, and a chat reply is correctly ✓ 这个方案我觉得没问题
- **Problem → mechanism → method:** `多模态识图在复杂 UI 中精度有限；这本质上是上下文不足。因此，工具需要先压缩并结构化 Figma 信息。`
- **Source-backed alternative:** `静态工具样式还原度高，但依赖组件打标`
- **Earned phrases:** `最短交互路径` works because it names a product goal; `不知道自己不知道什么` works because it names a failure mode.

## How to apply

- **Writing** — write to these principles from the first draft; far cheaper than retrofitting.
- **Polishing** — read the whole text before changing a word, so the five variables are settled from all of it rather than from the first paragraph; then revise against the **用词** and **句式** sections without over-correcting (**语域**), and check the result with the self-check.
- **Translating** — read for *meaning*, then write that meaning as Chinese; never go clause-by-clause. Translation is where 翻译腔 creeps in most.

## Self-check

- [ ] Chinese sentence structure throughout — coordinate pre-modifiers are separated by `、`, and no single pre-modifier stacks three or more of actor, place, time and manner around its verb, no `被…所…`, no connector pile-ups (`由于…因此…并且`), no nominalized `进行…的处理`, no subject drift.
- [ ] No needless English — every English token left in the text is a bare acronym that this domain's own Chinese writing leaves in English (**既有术语与英文**: software `LLM` `API` `SPA` `CFG` `FSM` `MCP`; medicine `CT` `MRI` `PCR`; finance `IPO` `ETF` `ROE`; the inventory belongs to the settled domain, so read it off that field, not off this list), a term canonical as English in that field (`agent`), a product name or trademark, an author name, a URL, quoted English, or a code identifier; genuine settled terms (`幂等`/`回滚`/`死锁`) are not over-translated into Chinese.
- [ ] No coinage — every nonstandard term, and every `面`/`态`/`位`/`键` suffix form, passes the substitution test: replaced by a plain description of what it denotes, the text loses no information. A term settled for this audience stays; one settled only inside a narrower field is expanded.
- [ ] No vividness the text's purpose doesn't need — no personification, branded labels, noun-metaphor, slogans, drama, or wrong-connotation words; in creative and persuasive prose, each figure earns its effect and still names something checkable.
- [ ] Register, medium and relationship match what was settled — professional / casual / creative, the medium's own forms, upward / downward / peer / outward — and hold steady, never mixing within the text except where the text quotes a speaker, marks an aside, or stages a deliberate collision in creative prose, each set off as quotation or aside.
- [ ] No absolute/categorical words reached for by default (`只能`/`必须`/`一定`/`永远`/`一旦…就`) — measured phrasing unless the claim is genuinely absolute, or the settled genre is one that imposes obligation — contract, policy, safety notice, regulatory text — where `应`/`不得`/`严禁` are the correct form; and no over-hedge mush (`可能…也许…或许`) — one qualifier per real uncertainty, placed precisely, not counting distance markers written upward or to a client (`是否方便…`/`我们这边…`), which are politeness rather than hedging.
- [ ] No clipped/over-shortened words in running prose — each written in its complete natural form (`重复录入` not `重录`, `手动维护` not `手维护`); display slots and casual chat keep their own short forms, and so does a settled industry short form that heads its own sentence on first mention and heads its own compounds (`压测`/`灰度`/`联调`; `压测平台`), but not one that merely trails its long form nearby (`冒烟`, `回归`).
- [ ] Contrast phrasing preserves emphasis: `不是A而是B` kept when natural, or rewritten as `是B，而非A` only with B fronted and meaning unchanged; one-thought clauses welded with a native connective (`之所以…是因为`/`与其…不如`), not left as disjointed facts; sentences bundling definition + justification + instruction are split, except where the genre binds a condition to its consequence in one clause (a contract).
- [ ] Identifiers, numbers, citations, author names, URLs, statute and clause numbers, drug names and doses, quoted figures with units, and trademarks are byte-for-byte unchanged — including through any 简繁 conversion; in translation only, a drug's generic name and a statute's title take their official Chinese form and a clause number takes the target citation's form with its value unchanged.
- [ ] Technical claims name a mechanism, dependency, or scope; generic praise or business outcomes like `全面提升`、`智能化水平`、`高质量增长`、`赋能` stay only where the source supports them; otherwise they are replaced with the concrete substance the source states, or flagged to the user when it states none, never swapped for milder slogans.
- [ ] Every advantage, tradeoff and limitation stated in the source appears in the output; no source-stated negative was dropped or softened, and none was invented for balance.
- [ ] Every nonstandard term passes the three vocabulary tests — defined at first use, one meaning everywhere (no count-bound shorthand, no one-name-two-concepts), and compressing defined repetition rather than hiding an unstated subject, condition, action, or result; a term the source gives nothing to restore is kept as written and flagged to the user, never filled in.
- [ ] Locale and script match the settled setting — mainland `软件`/`数据`/`网络` against Taiwan `軟體`/`資料`/`網路`; no simplified and traditional mixed in one text outside the spans **Fidelity — protected spans** protects; the 简繁 pass did not run over those spans.
- [ ] Chinese punctuation is fullwidth throughout (，。：；、——……), and quotation marks follow the settled locale — “” for mainland and Singapore, 「」 for Taiwan and Hong Kong; halfwidth marks appear only inside identifiers, URLs, quoted English, or where they are the surrounding non-Chinese sentence's own punctuation around a cited Chinese phrase.
- [ ] Re-read cold: every term the three vocabulary tests flagged was replaced, defined at first use, or, where the source supplies nothing to restore, kept and flagged to the user, and no sentence needed a second pass to parse.
