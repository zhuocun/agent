---
name: raise-ambition
description: >-
  Rewrite a task's brief before work starts so it aims higher, in any domain, through four
  lenses: Altitude (the outcome the task serves, one level up), Depth (the raw material,
  methods, hard targets, tested assumptions and outside verification a field-leading expert
  would use) and Range (methods from other fields that change the result) from Felix
  Rieseberg's essay on ambition, plus Speed (a deadline, an early first check, parallel work and
  no avoidable waits).
  Keeps the user's scope, constraints, permissions and budget; the result is one brief,
  definition of done included, that whoever does the work follows.
  Use on your own initiative whenever a non-trivial task is about to start and its description
  names the deliverable — a design or architecture, a research or analysis question, a
  business review, a strategy or plan, a piece of writing, an operational process, a personal
  project — with any constraints (the audience, or limits on scope, length or size, file
  format, budget, time or tools) but no method and no acceptance criteria (a stated test of
  whether the result is good enough: a target figure for the result itself, such as a daily
  calorie total, a load time or an error rate, but not its length or size; a required set of
  sections; or a reviewer's pass condition); every new request in a conversation is a new
  task, even when it continues earlier work or the skill was already used in that
  conversation; a brief it wrote stays binding on whoever continues that work.
  Also use when asked to make a task, prompt or plan more ambitious or to raise its standard.
  Do not use, unless the user asks, for a trivial or mechanical task, a fix whose cause is
  already known, a task that already has acceptance criteria or a spec, a task whose method
  the user fixed, a step you take inside a request already briefed (a clarification about the
  work, fixing a review finding, a status check), or a question that needs only an answer; never
  use it for executing the task or reviewing finished work.
---

# Raise Ambition

Before work starts, rewrite an ordinary task description into one self-contained brief that aims higher and can still be checked, so whoever executes it holds the work to at least the brief's definition of done. The brief rests on four lenses: **Altitude**, the outcome the deliverable serves, one level up; **Depth**, the raw inputs, methods, targets and outside checks a field-leading expert would use; **Range**, methods borrowed from other fields that change the result; and **Speed**, a schedule that reaches a verified result early. It keeps the user's scope, constraints, permissions and budget, and asks the user about every change that needs consent before any work on that change starts. The skill rewrites only: it does not execute the task, review finished work, or grade an existing plan, and whoever was asked to do the task, including you if you were, then does it under the brief. The lenses come from Felix Rieseberg's essay "How to be more ambitious: A tutorial for humans with models" (2026-10-13, https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/; summarized in `references/rieseberg-ambition.md` for reading offline); the essay names Speed only as doing the same work faster and skips it, so this skill's Speed lens and its mechanisms come from other sources.

Priority order, highest first: **the user's constraints, safety and permissions → verifiability → Altitude → Depth → Range → Speed → concision.** A target raised beyond what an outside check can confirm is worse than the original target, so verifiability caps every lens. Apply the lenses in the same order: Altitude sets the outcome, Depth sets the standard and methods that reach it, Range brings in the methods of fields that Depth within one field would miss, and Speed schedules the work the first three define.

Run the skill once per task, and on your own initiative for every later task in the conversation that it fits; add the user's later approvals to Definition of done as pass 6 directs, and never raise a brief this skill already produced unless the user asks for a further raise. Give the brief verbatim to whoever continues the work, after a break, from a summary, or as a helper or another person, and hold the work to it; only the user can change it. Scale the rewrite to the task: a small task keeps only Task as given, Constraints kept, Outcome, Targets, Verification, Definition of done, Fields, Confirm before starting and Lenses skipped, which lists the other slots, dropped, in one line; on any task, a lens that does not fit is skipped with its reason. Write the brief in the task's language (slot labels may stay English), gloss each lens name in plain words on first use, and return one recommended brief, never alternatives side by side. Word the whole brief, the disproof line in Fields included, in correctness and reliability terms (the rule, the input, the expected result) rather than security-testing terms, since a model executing the brief may decline work that reads as security testing.

## The brief

Fixed slots, in this order, at most about 40 lines:

```
Task as given:        <the original task, verbatim>
Constraints kept:     <each user constraint, verbatim>
Outcome:              <what the deliverable must cause, one level up, observable>
Targets:              <high target; minimum acceptable target; learning target if novel or complex; guardrails>
Inputs:               <primary sources and raw data>
Methods:              <method or tool → what it produces>
Assumptions to test:  <assumption → test that could disprove it> (2–3)
Verification:         <check outside the author → how to run it → pass condition>
Definition of done:   <minimum targets; guardrails; Verification pass conditions; Confirm items the user approved> (the high target in Targets is the aim, not part of done; work continues toward it after the minimum is met until the stop pass 6 defines, written out as its date or amount; report the result against both beside the deliverable, not inside it)
Fields:               <field → method → what it changes> (3–5, one tries to disprove the result; a small task keeps one method and the disproof line)
Schedule:             <deadline; critical path; parallel lines; waits removed; time of first outside check>
Out of scope:         <what this brief does not cover>
Confirm before starting: <each item that needs the user's consent, per pass 6>
Lenses skipped:       <lens or slot → reason>
```

## Passes

### 1. Fix the frame and check resources

Copy the task verbatim, and copy verbatim every explicit user constraint (scope, length, file format, deadline, budget, tools, audience, actions to ask about first), meaning each limit the user set beyond the deliverable and its subject, which Task as given already carries. Then make one read-only check of what actually exists: the data, tools, access, prior work, and who uses the result. Name only resources the check found; one the raised brief needs but the check did not find becomes a precondition in Confirm before starting. Neither the check nor the brief obtains access, spends money, contacts anyone outside or takes an irreversible step on its own authority.

### 2. Altitude — the outcome the deliverable serves

Work out from the task and the resource check who uses the deliverable for which decision, and what would stop this task recurring. Write the Outcome one level up from the deliverable, in observable terms, and keep the deliverable's type. Then ask the same two questions once more of the Outcome; a higher outcome that would replace the deliverable or change its audience goes to Confirm before starting as a proposal, preferably a trial run alongside the current deliverable, not into the brief's working plan. When the Outcome is a standing goal (keeping something true rather than fixing one case), name in Inputs, or as a precondition in Confirm before starting, what the executor needs to pursue and verify it without the user: the data feeds, the mappings between records, the environments to reproduce in. Altitude fits best when the user is after an outcome beyond the deliverable, a sign of which is that the result feeds a discussion or a decision; for work judged mainly on taste, such as fiction, visual design or a personal letter, apply it lightly and put the ambition into Depth and Range.

### 3. Depth — the standard a field-leading expert would hold

Answer the essay's four questions: what would a top practitioner do beyond the ordinary version, which raw material would they start from, which methods and tools would they use, and which outside signal would confirm the result. Every addition changes a method, an input, a target or the verification, never the number of deliverables. Fill the slots from those answers:

- **Inputs** are primary sources and raw data, not someone else's summary of them.
- **Methods** name concrete methods or tools and what each produces.
- **Targets**: each target carries a number and a unit where the result can be measured. Where it is judged on quality or taste, state it as a pass condition an outside reader applies, such as "two of three readers who did not see the drafts restate the argument in one sentence". Set one high target well beyond what the task strictly needs (where the result is measurable, often an order of magnitude or more past what the task needs: a page that must load in 5 s gets a 200 ms high target), state it in the brief as achievable, and set one minimum acceptable target. For a novel or complex task (a design, a study, a strategy) add a learning target, such as "compare at least N distinct approaches before choosing": in goal-setting research on people, hard specific goals beat vague ones, but when the strategy for a complex task is not yet known, a hard performance goal alone can lead to worse strategies than a goal to discover them (Locke & Latham, 2002). Add guardrails, the qualities that must not get worse, because a single pursued metric degrades what it does not measure (Goodhart's law; Ordóñez et al., 2009). Once the minimum is met, keep working toward the high target, even when it looks impossible, until the stop that pass 6 defines and Definition of done states; if the work misses it, report the result against both targets as it stands, and never lower a target after the fact.
- **Assumptions to test** are the two or three the result rests on, each with a test that could disprove it.
- **Verification** is a check the author does not grade: a test suite, held-out data, a measurement, a blind second reviewer, a pilot. State how to run it and what counts as a pass. Prefer a check the executor can run itself and get feedback from immediately. Where the result cites facts, Verification also checks, before delivery, each cited fact a conclusion or decision rests on against its primary source, not a summary, and labels any fact left unchecked as unverified where it appears in the deliverable. Self-assessment is not verification; models in particular rarely fix their own reasoning without an outside signal (Huang et al., 2024). Where the raw material allows, make the high target or the learning target something even top practitioners do not yet know (a signal, cause or result not found before), and reserve held-out data or another outside check in Verification to confirm it.

### 4. Range — methods from other fields

First restate the deliverable as what it must accomplish, starting with a verb ("a deck" becomes "getting busy people to believe a story about cause and effect, and to decide under uncertainty, in 30 minutes"), then pick the fields that are good at that verb. To find more fields, list who would be recruited if the result had to be excellent (specialists for the content, for its form and presentation, and an adversarial reviewer), then keep each one's method, never the role. Each Fields line names a concrete method and the result it changes, never a persona or a tone ("think like an economist" is not a method). One line always tries to disprove the conclusion, phrased as a challenge review: a reviewer who argues the opposite from the same evidence, or a review of the design's weakest point.

### 5. Speed — time to a verified result

Speed shortens the time to a result that passed its outside check, not to an unchecked draft. It rests on four mechanisms:

1. Set a tight deadline at the start (Collison's "Fast" list of projects that met hard goals on short deadlines).
2. Get the first outside check early: a small part of the result, a sample, a pilot, a draft review; a short observe–decide–act cycle (the OODA loop) corrects course sooner.
3. List the lines of work that can run in parallel and name the serial critical path, since the serial part, not the parallel work, sets the finish time (Amdahl's law).
4. Remove avoidable waits, starting with the step that holds up everything else (theory of constraints): batch the questions and approvals at the start, get data and access in place before work begins, and cut work that does not serve the Outcome, never a part the user asked for.

Never buy speed by skipping verification, and never write "faster" without a mechanism.

### 6. Close the brief

Fill Out of scope with what the brief deliberately leaves out. Fill Confirm before starting with every item that changes the deliverable or its audience, needs access the resource check did not find, spends money, exceeds a budget or deadline the user set, or, when the user set none, needs clearly more effort than the task as given implies (as a rule of thumb, more than about twice). Include any proposal to relax a user constraint. Only the user can answer these items: ask the user about them before starting them, or, where you cannot reach the user, list them verbatim with the brief for whoever can. Work that does not depend on them proceeds, and until the user agrees, each such item stays out of the working plan. Raises of methods, targets and verification that fit inside those limits need no consent: state them in the brief and proceed. A deadline set earlier than the user's is a raise, not a change of time. Fill Definition of done with the minimum targets, the guardrails and the pass conditions in Verification, and copy into it the rule that the high target is what the work aims for, not part of done, that work continues toward it after the minimum is met until the stop, which is the first reached of the user's deadline or budget, the Schedule's deadline if the brief has one, and, when the user set neither, about twice the effort the task as given implies (unless the user approved more in Confirm before starting), and that the result is reported to whoever receives the work against the high and the minimum target, the Definition of done and the Verification, beside the deliverable (such as in the covering message) and not inside it, so the rule travels with the brief. The deliverable itself carries a target or check only when its user needs it there (a workshop's assessment design, a plan's own milestones), and never the brief's slot names. Each Confirm before starting item is added to it once the user approves it; declined or unanswered items stay out. Fill Lenses skipped with each skipped or lightened lens and its reason.

## Examples

Extracts; a real brief fills every slot it keeps.

**Software — "Design the architecture of a multi-tenant notification service."**
- Outcome: each tenant's messages arrive on time and exactly once; on-call finds the cause of a failed delivery within 5 minutes.
- Targets: high, p99 ≤ 1 s at 10× peak; minimum, p99 ≤ 3 s at current peak with no tenant delayed by another's load; guardrail, cost per message does not rise. The numbers are placeholders until checked against real traffic.
- Methods: a queueing capacity model, a load simulation, a TLA+ model of retries and deduplication.
- Fields: SRE (failure drills that switch off a dependency), scheduling theory (weighted fair queueing); a reviewer argues the design fails when one tenant floods the queue.
- Verification: model-checker output, load data, a replay of historical peaks.
- Definition of done: p99 ≤ 3 s at current peak with no tenant delayed by another's load, cost per message not higher, and the model checker finds no lost or duplicated message; the replay of historical peaks is added once production-log access is approved.
- Confirm before starting: access to production logs.

**Research — "Summarize the research on whether remote work lowers productivity, for the company's office policy."**
- Outcome: a policy decision the executives can defend, plus how it will be checked after rollout.
- Methods: a systematic search with stated inclusion criteria, effect sizes weighted by study design, split by task type.
- Assumptions to test: productivity means output, not hours.
- Verification: a second reviewer applies the inclusion criteria blind to the conclusions; conclusions are written down before the internal data is opened.
- Definition of done: the blind second review agrees with the inclusion decisions and the conclusions were fixed before the internal data was opened; the internal HR data is added once its use is approved.
- Fields: labor economics (causal identification), organizational psychology (team coordination); one line argues the opposite policy from the same evidence.
- Confirm before starting: use of internal HR data.

**Business — "Prepare the quarterly business review deck."**
- Outcome: leadership spots problems earlier and decides on resources.
- Methods: start from the raw data, find the three most urgent decisions, and give the case for and against each.
- Definition of done: three decisions drawn from the raw data, each with its case for and against; the mechanism in Confirm before starting is added once approved.
- Confirm before starting (Altitude one more level): a mechanism that catches problems before the quarterly review, run alongside it for one quarter.

**Writing — "Write a 1,500-word essay arguing that cities should remove parking minimums."**
- Outcome (Altitude light): a reader who disagreed can state the strongest version of the argument.
- Targets: high, 3 of 3 test readers who did not see the drafts, including one who supports parking minimums, restate the thesis and its main evidence in one sentence each, and that reader names no counterargument the essay leaves unanswered; minimum, 2 of 3 restate them; guardrail, no figure without a primary source.
- Inputs: the zoning codes and before-and-after permit data from cities that removed minimums, not commentary about them.
- Fields: urban economics (estimate the effect from the permit data), journalism (lead with one case a reader can picture); one line argues for keeping minimums from the same data.
- Definition of done: 2 of 3 test readers restate the thesis and its main evidence; every figure has a primary source.
- Schedule: draft by Thursday; first outside check, two test readers on the outline on Tuesday; no parallel lines, since one author writes in sequence.

## Failure modes

1. **New vocabulary, same method** — bolder words, no changed method, input, target or check.
2. **Scope growth passed off as depth** — more deliverables, not a higher standard.
3. **Altitude too high or swapped** — an outcome nobody can act on, or a different task quietly replacing the one given.
4. **Self-assessment as verification** — the author grades its own result.
5. **Role-play instead of method** — a persona or tone where a method belongs.
6. **Targets nobody can check** — "fast", "scalable", "best-in-class", with no number or reader pass condition.
7. **Secondhand inputs only** — summaries where the raw material exists.
8. **False speed** — no mechanism, or the check skipped.
9. **Overstepped bounds** — a constraint, permission or cost crossed without asking.
10. **One metric chased** — no guardrails or no minimum target, so the result cannot be reported honestly.
11. **Invented resources** — data, tools or access the resource check did not find.
12. **Full process on a small task** — fourteen slots for a two-line job.
13. **A generic brief** — it would fit a different task unchanged.

## Self-check

- [ ] Each item below applies to the slots the brief fills; a slot dropped for a small task is named in Lenses skipped.
- [ ] The task and constraints are copied verbatim; the number of deliverables is unchanged or the change is in Confirm before starting.
- [ ] The Outcome is observable, one level up, and does not replace the task.
- [ ] Every target has a number and a unit, or, for work judged on quality, a pass condition an outside reader applies; there is a high target set well beyond what the task strictly needs and stated as achievable, and a minimum target, a learning target if the task is novel or complex, and guardrails.
- [ ] Inputs are primary sources where they exist; Methods name concrete tools; two or three assumptions each have a test that could disprove them.
- [ ] Verification comes from outside the author, states how to run it and what passes, and checks each cited fact a conclusion rests on against its primary source or labels it unverified; Definition of done holds the minimum targets, guardrails, those pass conditions and only the Confirm items the user approved, never the high target, and states that the high target is the aim, that work continues toward it after the minimum is met until the stop pass 6 defines, and that the result is reported against both beside the deliverable, not inside it.
- [ ] Each Fields line names a method and what it changes, with no persona; one tries to disprove the result, worded so it does not read as security testing.
- [ ] The Schedule has a deadline, critical path, parallel lines, waits removed (questions and approvals first) and the time of the first outside check.
- [ ] Every item pass 6 requires consent for is in Confirm before starting, and no work that depends on those items starts until the user agrees.
- [ ] The brief obtains no access, spends no money, contacts no one outside and takes no irreversible step on its own authority.
- [ ] Out of scope is filled; skipped lenses carry reasons; one brief of at most about 40 lines, in the task's language, naming only resources the check found, and given verbatim to whoever continues the work.
