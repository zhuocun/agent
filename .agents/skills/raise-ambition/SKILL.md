---
name: raise-ambition
description: >-
  Rewrite a task's brief before work starts so it aims higher, in any domain.
  Use on your own initiative when a task's description names the deliverable, such as a design,
  research or analysis, a business review, a strategy or plan, writing, an operational process,
  or a personal project.
  Treat each new request as a new task, even if it continues earlier work or this skill was used
  before.
  Also use when asked to raise the ambition or standard of a task, prompt or plan.
  Do not use, unless the user asks, for a trivial or mechanical task, a fix whose cause is
  known, a task whose method the user named, a task with a spec or acceptance criteria (a target
  figure, required sections or a reviewer's pass condition), a step you take inside a briefed
  request (a clarification or a fix for a review finding), or a question that needs only an
  answer. A stated audience or limits on scope, length, size, format, budget, time or tools
  are not a
  method or acceptance criteria. Never use it to execute a task or review finished work.
---

# Raise Ambition

Before work starts, rewrite an ordinary task description into one self-contained brief that aims higher and can still be checked, so whoever executes it holds the work to at least the brief's definition of done. The brief rests on four lenses: **Altitude**, the outcome the deliverable serves, one level up; **Depth**, the raw inputs, methods, targets and outside checks a field-leading expert would use; **Range**, methods borrowed from other fields that change the result; and **Speed**, a deadline and an early outside check that reach a verified result sooner. The brief is laid out under those four lenses, so its reader sees what each one raised. It keeps the user's scope, constraints, permissions and budget, and asks the user about every change that needs consent before any work on that change starts. The skill rewrites only: it does not execute the task, review finished work, or grade an existing plan, and whoever was asked to do the task, including you if you were, then does it under the brief.

Priority order, highest first: **the user's constraints, safety and permissions → verifiability → Altitude → Depth → Range → Speed → concision.** A target raised beyond what an outside check can confirm is worse than the original target, so verifiability caps every lens. Apply the lenses in the same order: Altitude sets the outcome, Depth sets the standard and methods that reach it, Range brings in the methods of fields that Depth within one field would miss, and Speed sets when the work the first three define is first checked and finished.

Run the skill once per task, and on your own initiative for every later task in the conversation that it fits; add the user's later approvals to Definition of done as pass 6 directs, and never raise a brief this skill already produced unless the user asks for a further raise. Give the brief verbatim to whoever continues the work, after a break, from a summary, or as a helper or another person, and hold the work to it; only the user can change it. Scale the rewrite to the task: a small task keeps only Task as given, Constraints kept, the four lens headings with Outcome, Targets (its precedent, or "none found", as a clause), Verification, Fields and Schedule under them, Definition of done, Confirm before starting and Slots dropped, which lists the other slots and their reason in one line; on any task, a lens that does not fit is skipped as the template shows. Write the brief in the task's language (slot labels and lens headings may stay English; write each heading's plain-words gloss in the task's language), and return one recommended brief, never alternatives side by side. Word the whole brief, the disproof line in Fields included, in correctness and reliability terms (the rule, the input, the expected result) rather than security-testing terms, since a model executing the brief may decline work that reads as security testing.

## The brief

Slots in this order, grouped under the four lens headings, at most about 40 lines, headings not counted:

```
Task as given:          <the original task, verbatim>
Constraints kept:       <each user constraint, verbatim>

ALTITUDE (the outcome one level up)
  Outcome:              <what the deliverable must cause, observable>
DEPTH (what a field-leading expert would do)
  Inputs:               <primary sources and raw data>
  Methods:              <method or tool → what it produces>
  Targets:              <high target; minimum acceptable target; learning target if novel or complex; guardrails>
  Precedent:            <who reached a comparable result → what it shows>, or none found
  Assumptions to test:  <assumption → test that could disprove it> (2–3)
  Verification:         <check outside the author → how to run it → pass condition>
RANGE (methods from other fields)
  Fields:               <field → method → what it changes> (3–5, one tries to disprove the result; a small task keeps one method and the disproof line)
SPEED (a verified result sooner)
  Schedule:             <deadline; time of the first outside check> (when time is the binding constraint, also: critical path; parallel lines; waits removed, questions and approvals first)

Definition of done:     <minimum targets; guardrails; Verification pass conditions; Confirm items the user approved> (the high target in Targets is the aim, not part of done; work continues toward it after the minimum is met until the stop pass 6 defines, written out as its date or amount; report the result against both beside the deliverable, not inside it)
Out of scope:           <what this brief does not cover>
Confirm before starting: <each item that needs the user's consent, per pass 6>
Slots dropped:          <slot dropped or lens lightened → reason>
```

A skipped lens keeps its heading and replaces its slots with `Skipped: <reason>`.

## Passes

### 1. Fix the frame and check resources

Copy the task verbatim, and copy verbatim every explicit user constraint (scope, length, file format, deadline, budget, tools, audience, actions to ask about first), meaning each limit the user set beyond the deliverable and its subject, which Task as given already carries. Then make one read-only check of what actually exists: the data, tools, access, prior work, and who uses the result. Name only resources the check found; one the raised brief needs but the check did not find becomes a precondition in Confirm before starting. Neither the check, pass 3's reading nor the brief obtains access, spends money, contacts anyone outside or takes an irreversible step on its own authority.

### 2. Altitude — the outcome the deliverable serves

Work out from the task and the resource check who uses the deliverable for which decision, and what would stop this task recurring. Write the Outcome one level up from the deliverable, in observable terms, and keep the deliverable's type. Then ask the same two questions once more of the Outcome; a higher outcome that would replace the deliverable or change its audience goes to Confirm before starting as a proposal, preferably a trial run alongside the current deliverable, not into the brief's working plan. When the Outcome is a standing goal (keeping something true rather than fixing one case), name in Inputs, or as a precondition in Confirm before starting, what the executor needs to pursue and verify it without the user: the data feeds, the mappings between records, the environments to reproduce in. Altitude fits best when the user is after an outcome beyond the deliverable, a sign of which is that the result feeds a discussion or a decision; for work judged mainly on taste, such as fiction, visual design or a personal letter, apply it lightly and put the ambition into Depth and Range.

### 3. Depth — the standard a field-leading expert would hold

Answer four questions (what would a top practitioner do beyond the ordinary version, which raw material would they start from, which methods and tools would they use, and which outside signal would confirm the result) from your own knowledge where you can name the field's leading methods and the standard that sets them, and otherwise, unless the task is small, after reading the field's leading references (standards, method guides, published practice), read-only and counted against the deadline; the brief names the methods found, never the references. Every addition changes a method, an input, a target or the verification, never the number of deliverables. Fill the slots from those answers:

- **Inputs** are primary sources and raw data, not someone else's summary of them.
- **Methods** name concrete methods or tools and what each produces.
- **Targets**: each target carries a number and a unit where the result can be measured. Where it is judged on quality or taste, state it as a pass condition an outside reader applies, such as "two of three readers who did not see the drafts restate the argument in one sentence". Set one high target well beyond what the task strictly needs (where the result is measurable, often an order of magnitude or more past what the task needs: a page that must load in 5 s gets a 200 ms high target), state it in the brief as achievable, backed by the Precedent where one exists, and set one minimum acceptable target. For a novel or complex task (a design, a study, a strategy) add a learning target, such as "compare at least N distinct approaches before choosing": in goal-setting research on people, hard specific goals beat vague ones, but when the strategy for a complex task is not yet known, a hard performance goal alone can lead to worse strategies than a goal to discover them (Locke & Latham, 2002). Add guardrails, the qualities that must not get worse, because a single pursued metric degrades what it does not measure (Goodhart's law; Ordóñez et al., 2009). Once the minimum is met, keep working toward the high target, even when it looks impossible, until the stop that pass 6 defines and Definition of done states; if the work misses it, report the result against both targets as it stands, and never lower a target after the fact.
- **Precedent** names one case where someone reached a result comparable to the high target and what it shows, taken from what you know, the resource check or the reading above, never from a search of its own, marked "(unverified)" unless the resource check or a primary source in that reading confirmed it; where none is found, write "none found" and keep the target.
- **Assumptions to test** are the two or three the result rests on, each with a test that could disprove it.
- **Verification** is a check the author does not grade and that rests on more than the user's opinion: a test suite, held-out data, a measurement, a blind second reviewer, a pilot. State how to run it and what counts as a pass. Prefer a check the executor can run itself and get feedback from immediately. Before delivery, Verification also recomputes every total, rate and other figure the deliverable derives from its inputs, and, where the result cites facts, checks each cited fact a conclusion or decision rests on against its primary source, not a summary; a fact left unchecked carries a mark for the reader where it appears, such as "(unverified)" or "(secondary source)", never an account of what the author did or did not check. Self-assessment is not verification; models in particular rarely fix their own reasoning without an outside signal (Huang et al., 2024). Where the raw material allows, make the high target or the learning target something even top practitioners do not yet know (a signal, cause or result not found before), and reserve held-out data or another outside check in Verification to confirm it.

### 4. Range — methods from other fields

First restate the deliverable as what it must accomplish, starting with a verb ("a deck" becomes "getting busy people to believe a story about cause and effect, and to decide under uncertainty, in 30 minutes"), then pick the fields that are good at that verb. To find more fields, list who would be recruited if the result had to be excellent (specialists for the content, for its form and presentation, and an adversarial reviewer), then keep each one's method, never the role. Each Fields line names a concrete method and the result it changes, never a persona or a tone ("think like an economist" is not a method). One line always tries to disprove the conclusion, phrased as a challenge review: a reviewer who argues the opposite from the same evidence, or a review of the design's weakest point.

### 5. Speed — a verified result sooner

Speed shortens the time to a result that passed its outside check, not to an unchecked draft. Set a deadline at the start: tighter than the user's where the work allows, or, when the user set none, at the stop pass 6 sets. Put the first outside check early, on a small part of the result, a sample, a pilot or an outline, so the course is corrected sooner. When time is the binding constraint (a tight deadline or long work), also name the serial critical path, since it, not the parallel work, sets the finish time, list the lines that can run alongside it, and remove avoidable waits, starting with the step that holds up everything else: batch the questions and approvals at the start, get data and access in place before work begins, and cut work that does not serve the Outcome, never a part the user asked for. Never buy speed by skipping verification, and never write "faster" without a mechanism.

### 6. Close the brief

Fill Out of scope with what the brief deliberately leaves out. Fill Confirm before starting with every item that changes the deliverable or its audience, needs access the resource check did not find, spends money, exceeds a budget or deadline the user set, or, when the user set none, needs clearly more effort than the task as given implies (as a rule of thumb, more than about twice). Include any proposal to relax a user constraint. Only the user can answer these items: ask the user about them before starting them, or, where you cannot reach the user, list them verbatim with the brief for whoever can. Work that does not depend on them proceeds, and until the user agrees, each such item stays out of the working plan. Raises of methods, targets and verification that fit inside those limits need no consent: state them in the brief and proceed. A deadline set earlier than the user's is a raise, not a change of time. Fill Definition of done with the minimum targets, the guardrails and the pass conditions in Verification, and copy into it the rule that the high target is what the work aims for, not part of done, that work continues toward it after the minimum is met until the stop, which is the first reached of the user's deadline or budget, the Schedule's deadline if the brief has one, and, when the user set neither, about twice the effort the task as given implies (unless the user approved more in Confirm before starting), and that the result is reported to whoever receives the work against the high and the minimum target, the Definition of done and the Verification, beside the deliverable (such as in the covering message) and not inside it, so the rule travels with the brief. The deliverable itself carries a target or check only when its user needs it there (a workshop's assessment design, a plan's own milestones), and never the brief's slot names. Each Confirm before starting item is added to it once the user approves it; declined or unanswered items stay out. Fill Slots dropped with each slot dropped and each lens lightened, with its reason; a lens skipped entirely gives its reason under its own heading instead.

## Examples

Extracts; a real brief fills every slot it keeps, and every lens heading appears even when skipped.

**Software — "Design the architecture of a multi-tenant notification service."**
```
ALTITUDE (the outcome one level up)
  Outcome: each tenant's messages arrive on time and exactly once; on-call finds the cause of a failed delivery within 5 minutes.
DEPTH (what a field-leading expert would do)
  Methods: a queueing capacity model, a load simulation, a TLA+ model of retries and deduplication.
  Targets: high, p99 ≤ 1 s at 10× peak; minimum, p99 ≤ 3 s at current peak with no tenant delayed by another's load; guardrail, cost per message does not rise. The numbers are placeholders until checked against real traffic.
  Verification: model-checker output, load data, a replay of historical peaks.
RANGE (methods from other fields)
  Fields: SRE (failure drills that switch off a dependency), scheduling theory (weighted fair queueing); a reviewer argues the design fails when one tenant floods the queue.
SPEED (a verified result sooner)
  Schedule: design review at the end of week 1; first outside check, on-call reviews the capacity model on day 2.
Definition of done: p99 ≤ 3 s at current peak with no tenant delayed by another's load, cost per message not higher, and the model checker finds no lost or duplicated message; the replay of historical peaks is added once production-log access is approved.
Confirm before starting: access to production logs.
```

**Research — "Summarize the research on whether remote work lowers productivity, for the company's office policy."**
```
ALTITUDE (the outcome one level up)
  Outcome: a policy decision the executives can defend, plus how it will be checked after rollout.
DEPTH (what a field-leading expert would do)
  Methods: a systematic search with stated inclusion criteria, effect sizes weighted by study design, split by task type.
  Assumptions to test: productivity means output, not hours.
  Verification: a second reviewer applies the inclusion criteria blind to the conclusions; conclusions are written down before the internal data is opened.
RANGE (methods from other fields)
  Fields: labor economics (causal identification), organizational psychology (team coordination); one line argues the opposite policy from the same evidence.
SPEED (a verified result sooner)
  Schedule: synthesis two days before the policy review; first outside check, the second reviewer applies the inclusion criteria to the first 10 screened studies on day 2.
Definition of done: the blind second review agrees with the inclusion decisions and the conclusions were fixed before the internal data was opened; the internal HR data is added once its use is approved.
Confirm before starting: use of internal HR data.
```

**Business — "Prepare the quarterly business review deck."**
```
ALTITUDE (the outcome one level up)
  Outcome: leadership spots problems earlier and decides on resources.
DEPTH (what a field-leading expert would do)
  Inputs: raw billing, usage and support data, not last quarter's slides.
  Targets: high, a churn warning 60 days ahead that holds on held-out quarters; minimum, the three most urgent decisions from the raw data, each with its case for and against.
  Precedent: subscription businesses that flag cancellations weeks ahead from usage drops → a 60-day warning is reachable from usage data alone (unverified).
RANGE (methods from other fields)
  Fields: epidemiology (survival analysis of churn); a short seller's research argues from the same data that the business is worse than it looks.
SPEED (a verified result sooner)
  Schedule: outline to the CFO a week before the meeting.
Definition of done: three decisions drawn from the raw data, each with its case for and against; the mechanism in Confirm before starting is added once approved.
Confirm before starting (Altitude one more level): a mechanism that catches problems before the quarterly review, run alongside it for one quarter.
```

**Writing — "Write a 1,500-word essay arguing that cities should remove parking minimums."**
```
ALTITUDE (the outcome one level up)
  Outcome (light): a reader who disagreed can state the strongest version of the argument.
DEPTH (what a field-leading expert would do)
  Inputs: the zoning codes and before-and-after permit data from cities that removed minimums, not commentary about them.
  Targets: high, 3 of 3 test readers who did not see the drafts, including one who supports parking minimums, restate the thesis and its main evidence in one sentence each, and that reader names no counterargument the essay leaves unanswered; minimum, 2 of 3 restate them; guardrail, no figure without a primary source.
RANGE (methods from other fields)
  Fields: urban economics (estimate the effect from the permit data), journalism (lead with one case a reader can picture); one line argues for keeping minimums from the same data.
SPEED (a verified result sooner)
  Schedule: draft by Thursday; first outside check, two test readers on the outline on Tuesday.
Definition of done: 2 of 3 test readers restate the thesis and its main evidence; every figure has a primary source.
```

## Failure modes

1. **New vocabulary, same method** — bolder words, no changed method, input, target or check.
2. **Scope growth passed off as depth** — more deliverables, not a higher standard.
3. **Altitude too high or swapped** — an outcome nobody can act on, or a different task quietly replacing the one given.
4. **Self-assessment as verification** — the author grades its own result, or the user's opinion is the only check.
5. **Role-play instead of method** — a persona or tone where a method belongs.
6. **Targets nobody can check** — "fast", "scalable", "best-in-class", with no number or reader pass condition.
7. **Secondhand inputs only** — summaries where the raw material exists.
8. **False speed** — no mechanism, or the check skipped.
9. **Overstepped bounds** — a constraint, permission or cost crossed without asking.
10. **One metric chased** — no guardrails or no minimum target, so the result cannot be reported honestly.
11. **Invented resources** — data, tools or access the resource check did not find.
12. **Full process on a small task** — every slot filled for a two-line job.
13. **A generic brief** — it would fit a different task unchanged.

## Self-check

- [ ] Each item below applies to the slots the brief fills; a slot dropped for a small task is named in Slots dropped.
- [ ] The task and constraints are copied verbatim; the number of deliverables is unchanged or the change is in Confirm before starting.
- [ ] The Outcome is observable, one level up, and does not replace the task.
- [ ] Every target has a number and a unit, or, for work judged on quality, a pass condition an outside reader applies; there is a high target set well beyond what the task strictly needs and stated as achievable, with a Precedent or a statement that none was found, and a minimum target, a learning target if the task is novel or complex, and guardrails.
- [ ] Inputs are primary sources where they exist; Methods name concrete tools the field's practitioners use, from pass 3's reading where it calls for one, and the brief cites none of that reading; two or three assumptions each have a test that could disprove them.
- [ ] Verification comes from outside the author, rests on more than the user's opinion, states how to run it and what passes, recomputes every derived figure, and checks each cited fact a conclusion rests on against its primary source or marks it for the reader as unverified, never with an account of the author's checking; Definition of done holds the minimum targets, guardrails, those pass conditions and only the Confirm items the user approved, never the high target, and states that the high target is the aim, that work continues toward it after the minimum is met until the stop pass 6 defines, and that the result is reported against both beside the deliverable, not inside it.
- [ ] Each Fields line names a method and what it changes, with no persona; one tries to disprove the result, worded so it does not read as security testing.
- [ ] The slots sit under the four lens headings in the template's order, each with its plain-words gloss in the task's language, even on a small task; a skipped lens gives its reason under its heading.
- [ ] The Schedule has a deadline and the time of the first outside check; when time is the binding constraint, it also has the critical path, parallel lines and waits removed.
- [ ] Every item pass 6 requires consent for is in Confirm before starting, and no work that depends on those items starts until the user agrees.
- [ ] Neither the brief nor its reading obtains access, spends money, contacts anyone outside or takes an irreversible step on its own authority.
- [ ] Out of scope is filled; one brief of at most about 40 lines, headings not counted, in the task's language, naming only resources the check found, and given verbatim to whoever continues the work.
