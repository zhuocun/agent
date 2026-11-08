# Claims a reader will act on

Use these wherever the prose makes claims a reader will act on — technical, business, policy, medical, financial, academic. The examples in this file are software; the patterns are not. They do not govern casual chat, taglines, or creative prose, where bounding a claim is not the job.

1. **Name the substance behind generic outcomes.** Generic praise or business outcomes such as `全面提升`、`智能化水平`、`高质量增长`、`赋能` stay only where the source supports them; otherwise replace them with the concrete substance the source states, or, where it states none, keep them and flag the gap to the user. Never swap them for milder slogans.
2. **Bridge problem to method through the mechanism.** When moving from problem to solution, use a short bridge: name the surface problem, state the underlying mechanism the source gives, then introduce the method.
3. **Acknowledge alternatives with source-backed precision.** If the source says another option has an advantage, keep it before stating the boundary; do not invent balance for tone.
4. **Let memorable phrases earn their place.** If a motif is only catchy, replace it with the concrete mechanism the source states.

- **Genre bounds:** a tagline is correctly ✓ 十分钟就能上手，无需通读文档 with no scope clause attached, a chat reply is correctly ✓ 这个方案我觉得没问题, and a line of fiction is correctly ✓ 那是全城最好吃的一碗面.
- **Bounded claims:** `在该测试场景下可降低请求耗时`、`代码完成度 = 正确实现数 / 功能点总数`、`准确性有限` over `全面提升准确性`、`仍有优化空间`.
- **Generic outcomes:** ✗ 全面提升 AI 编码效率、赋能业务高质量增长 → ✓ 降低组件选择和场景匹配成本、提高上下文完整性、减少影响范围遗漏 *(where the source names these)*
- **Problem → mechanism → method:** `多模态识图在复杂 UI 中精度有限，原因在于上下文不足。因此，工具需要先压缩并结构化 Figma 信息。`
- **Source-backed alternative:** `静态工具样式还原度高，但依赖组件打标`
- **Earned phrases:** `最短交互路径` works because it names a product goal; `不知道自己不知道什么` works because it names a failure mode.

## Checks

- [ ] Generic outcomes stay only where the source supports them, are replaced by what the source states, or are kept and flagged to the user; none became a milder slogan.
- [ ] Every advantage the source gives an alternative is kept before its boundary, and no balance was invented.
