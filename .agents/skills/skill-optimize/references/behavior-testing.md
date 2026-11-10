# Behavior testing

Apply this reference when you compare a revised skill with its previous version under pass 6. It sets how to build the cases, run the readers and judges, and report the result.

## Cases

- Have an author other than the skill's editor, such as a fresh agent given only the contract from pass 1 and the list of changed rules, write each case. Give every changed rule at least one case whose expected outcome differs when the rule is misread or missing, and add cases for unchanged rules the edit could break.
- Have the case author write the expected outcomes and a scoring rubric before any reader runs. Mark each rubric item that tests a changed rule.
- Test routing only when the description changed. Identical descriptions give identical routing input, so a routing run then shows nothing.
- When the test environment cannot exercise a rule, such as one that needs a browser, a real tool call or a real wait, simulate the condition and state what the simulation cannot show, or list the rule as untested.
- When the number of runs is limited, spend runs first on cases for changed rules, then on repeats of those cases, then on other cases.

## Readers

- Give each routing evaluator a fresh context, the requests, and the descriptions of the version under test and of the other skills installed beside it. Give each execution reader a fresh context, one version of the skill and the case materials. Do not tell an evaluator or reader which version it has or that a comparison exists.
- Assign versions to evaluators and readers in a recorded order that balances the versions across cases.
- Collect each evaluator's routing choice, and each reader's final answer and every file it produced.

## Judges

- Score each routing choice by comparing it with its expected outcome; routing choices need no judge.
- Give each judge the rubric, the case materials the reader received and every file the reader produced. Withhold the skill the reader had and anything else that reveals an answer's version, put in the rubric any fact that scoring needs, taken from the contract in pass 1 so that it is the same for both versions, and keep the mapping from answers to versions where the judges cannot read it.
- Require each verdict to quote, word for word, the answer or material it rests on. Check every quote against its source. Discard a verdict whose quotes do not occur in the source or that scores material its judge did not read. Disclose, without discarding the verdict, a defect in a judge's record that changes no evidence the verdict rests on, such as a misspelled file name in a read log.
- A judge that scores several answers in one context can compare them, which correlates its scores. Give each judge one answer when the run budget allows; otherwise disclose the correlation.
- When a verdict penalizes a defect of the test package rather than of the answer, such as a file the judge did not receive, report the raw score and the score with that item corrected, and name the defect.

## Reporting

- Report each version's score on the same rubric, and report the rubric items for changed rules separately.
- Describe a difference from one run per case and version as a trend, not an improvement. Describe equal results as no regression on those cases.
- List the planned cases that were not run, the rules left untested, each simulation and its limit, judge correlations, discarded verdicts and test-package defects.
