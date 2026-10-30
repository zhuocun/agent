---
name: skill-optimize
description: >-
  Creates, reviews and optimizes agent skills for reliable routing and execution.
  Use when authoring a SKILL.md, auditing skill instructions, or improving a
  skill's clarity, structure, scope or behavior. Do not use for ordinary prose
  editing, application code review, or runtime configuration unrelated to skill
  instructions.
---

# Skill Optimize

Create and revise skills that an agent can select correctly and execute reliably. Follow applicable instructions and the user's authorized scope; preserve intended behavior unless the task calls for a change. Optimize useful, reliable guidance per word, with this priority: correct behavior → clear routing and execution → independent composition → concise expression.

## 1. Establish the contract

Read the target skill, relevant source requirements and applicable project conventions. Identify the intended outcome, triggering requests, exclusions, required decisions and observable completion conditions. For an existing skill, distinguish behavior to preserve from behavior the user wants changed. Classify each proposed edit as creation, clarification, reorganization, behavior-neutral shortening or intentional behavior change; make changes in the final category deliberately and within scope.

Keep portable instructions in the core and environment-specific procedures in a scoped reference. For work in the `agent-skills`, `agent` or `pulse` repositories, read [Repository workflow](references/repository-workflow.md) only when its maintenance or distribution procedures apply.

## 2. Shape the routing and structure

Give the skill a short, descriptive name. Use one directory per skill, with `SKILL.md` and optional `references/` or `agents/` directories. Match the directory name to the frontmatter `name`.

Write YAML frontmatter with non-empty string values for `name` and `description`; other keys may be present. Keep the description at most 1024 characters and limit it to what the skill does and when to use it. Include a “Use when…” clause with recognizable triggers and, where over-application is likely, a “Do not use for…” clause describing excluded domains. Put operating rules, output requirements and rationale in the body. Use a folded `>-` scalar when punctuation could make a bare description unsafe to parse.

Open the body with an H1 and one paragraph defining the skill's role. State the priority order where objectives compete, organize execution as numbered passes or failure modes, and end with `## Self-check`.

## 3. Make execution unambiguous and independent

Write imperative, concrete, self-contained instructions for the executing agent. Give each sentence one reading; use standard professional terms and include reasons only when they help the agent apply a rule. Express source requirements as operating rules; keep maintainer notes, provenance and attribution outside the skill body.

Make an ordinary skill work with no other skill loaded and compose without conflicting responsibilities. Do not name another skill, rely on its terminology or output, or add rules for its cases; describe exclusions by domain. A skill-loading shortcut may name its declared members on explicit request only when applicable project instructions authorize that exception. Keep skills whose subject is not software-specific usable outside software. Review agent instructions against their execution contract rather than applying a prose-editing procedure that excludes them.

## 4. Consolidate and revise whole rules

State each rule once, with its exceptions attached. Refer to a section title, bold label or stable pass number instead of a relative position such as “the last rule.”

When changing a rule, rewrite the complete rule so it reads as a coherent instruction. Remove wording that answers an earlier version, such as “no longer” or “not X but Y.” When relaxing a rule, admit only the intended new cases and retain limiting terms such as “only.”

For example, to extend “Use tables only to compare structured attributes” to timelines, write “Use tables only to compare structured attributes or present timelines.”

Treat a cut as behavior-neutral only if removing the text changes no routing, decision, constraint, exception or completion condition. Retain words that carry those distinctions. Handle any resulting behavior change under the classification in pass 1.

## 5. Make rules sufficient before adding examples

State the method and decision criteria before illustrating them. Delete the examples mentally: the instructions alone must still produce the intended result. Use a small number of examples to resolve likely misreadings rather than substitute for a method.

Give each register- or genre-conditional exception a positive example in the permitted register or genre, showing the standard that still applies. For example: “Use neutral wording; in promotional copy, a brief imperative call to action is allowed if it makes no unsupported claim. ✓ Promotional copy: ‘Explore the collection.’”

## 6. Verify facts and claimed effects

Check every tool or product fact against current documentation or observed behavior. Choose a model, tool or product mode by a stable property, such as its position in the provider's current lineup, and define a fallback when nothing qualifies. Do not embed a temporary product ranking as a permanent instruction.

Validate applicable schema and repository constraints, then review whether the instructions preserve the contract from pass 1. Claim improved routing or behavior only from a comparison of the revised and previous versions on held-out cases the editor has not seen. For routing, give evaluators only the descriptions and requests; for execution, give fresh readers only the relevant skill and scenarios. Keep conditions comparable and evaluate against the same expected outcomes. Equal results show only no regression on those cases. Without such evidence, describe the edits and completed checks without claiming behavioral improvement; a new skill has no previous version to outperform.

## Self-check

- **Contract:** Does each change match pass 1's intended behavior, classification and authorized scope, with local procedures scoped to their reference?
- **Routing and structure:** Does the artifact satisfy pass 2's layout, metadata, description and body requirements?
- **Execution and composition:** Can an agent apply pass 3's instructions unambiguously and independently in the intended domains?
- **Rule integrity:** Are pass 4's rules stated once, exceptions attached, references stable, revisions complete and cuts behavior-neutral?
- **Examples:** Does the method remain sufficient without examples, and does each conditional exception covered by pass 5 have its positive example?
- **Evidence:** Are pass 6's facts current, applicable checks complete, and effect claims limited to what the evidence establishes?
