# Tables, diagrams, media, and code

1. Use tables for stable repeated columns such as options and tradeoffs, risks and mitigations, contracts and meanings, scenarios and verification, or phases and success criteria. Use prose for causality, rationale, the reasoning behind a tradeoff, ambiguity, uncertainty, risk, hidden assumptions, and nuanced caveats.
2. Use parallel table shapes for parallel structures, and do not force uncertain reasoning into apparently precise cells. Tables improve placement; they do not replace the decision narrative.
3. Give every retained or added diagram, image, video, code block, callout, evidence citation, or other native block an editorial job: evidence, instruction, architecture, workflow, or reference.
4. Use a diagram only when it explains a spatial, temporal, boundary, state, or relationship model more clearly than prose. Use a format supported by the destination and its maintainers; do not impose one tool or syntax on every document.
5. Give every figure that must be understood independently the minimum in-place legend needed to read it. Keep semantics consistent by using the same wording in each figure's legend; do not make figures depend on one shared legend. Check decision-tree branches for mutually exclusive and collectively complete coverage.
6. Place an overview diagram after the framing needed to interpret it and before the details it organizes. Validate an editable diagram with its actual renderer after changes; if rendering cannot be checked, report that limitation.
7. Introduce code blocks with what they demonstrate and summarize the design implication when it is not obvious. Avoid raw dumps unless required for reproducibility, contract review, or implementation reference.

## Structured technical expression

Choose the representation from the judgment the reader needs to make; do not default every technical fact to prose or every complex passage to a diagram.

| Reader judgment | Preferred representation |
| --- | --- |
| Data shape, nesting, or current-to-target structure | Minimal JSON, or JSONC when annotations are needed |
| Type, cardinality, optionality, or allowed values | A typed schema suited to the domain, such as TypeScript |
| Request, response, error, or system-boundary contract | A protocol-native example such as HTTP or RPC |
| Parsing order, validation logic, branching, or fallback | Pseudocode or a complete decision tree |
| Observable behavior and acceptance outcome | Gherkin, Given/When/Then, or another scenario form |
| Repeated field, trigger, state, or ownership mapping | A compact table with only varying columns |

1. Introduce each block with the question it helps answer, show only the minimum complete structure, and state the implication afterward when it is not self-evident.
2. Label every block as normative, current-state, target-state, illustrative, pseudocode, or unresolved when readers could mistake one for another.
3. Preserve frozen identifiers byte-exact. Use conspicuous placeholders for unresolved names and say that they are not part of the frozen contract; never invent realistic-looking fields, enum values, routes, or configuration keys.
4. Keep static contracts, dynamic control flow, observable behavior, and cross-item mappings in their native forms. Do not overload one notation to explain all four.
5. Structured blocks reduce reconstruction work; they do not replace judgment.
