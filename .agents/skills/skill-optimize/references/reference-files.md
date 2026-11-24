# Reference files

Apply this reference when a skill has or gains a file under `references/`, or when an edit moves text between `SKILL.md` and such a file. It sets where the pointers go, how to word a read condition, what stays in the body, and how to test that agents read the files.

Check each pointer against three questions. Does the pointer sit under the section's read rule? Can the agent tell from the task or from an event in the work whether the condition holds? If the body summarizes a rule that the file holds, does the body name the file as the holder of the complete rule?

## Placement

- List the reference files in one `## Reference files` section. Do not put the list inside a step or pass, because an agent can skip a list nested among a step's rules.
- Put the section after the rules that hold for the whole task and before the first step or pass.
- Open the section with one sentence that gives the read rule: read each file in full when its condition first holds, before applying its rules, and again after a compaction while the condition holds. State in that sentence any file of which the agent reads only named sections.
- Give every file under `references/` one bullet, including a file that another reference file names. The bullet holds a relative link or the `references/` path in inline code, a short description of the rules the file covers, and the read condition.
- Where a step or pass applies a rule that a reference file holds, name the file there in a short clause. State the condition only in the section.

## Conditions

- Write each condition as a fact the agent can observe in the task, such as "the diff adds a migration", or as an event in the work, such as "before the first edit".
- Do not write a condition that depends on the agent's judgment of itself or of the file, such as "an unfamiliar technique" or "when its procedures apply".
- State the extent of each read: the whole file, or the sections the pointer names. For a whole-file read, link the file and not a heading inside it.
- When a file applies to every task, move its content into the body if the token limit allows; otherwise give it the event "at the start of every task".

## Division of content

- Where the body gives a short form of a rule that a reference file completes, say there that the file holds the complete rule. Do not leave a body summary that an agent can take as the whole rule.
- Give each whole-file read one condition. When the sections of a file have separate conditions, split the file by condition, or list the named sections and their conditions under the file's bullet. When the sections are short, you may instead require a whole-file read when the condition of any section holds.
- Keep material that one condition requires together in one file.

## Checks and tests

- Keep a Self-check line that asks whether each file whose condition held was read. The line detects a missed read only after the work; it does not replace the section.
- A change to the placement, the read rule or a condition is a behavior change. Compare the old and new versions as pass 6 directs, with these additions: include a lower-capability model at low reasoning effort, to test for missed reads; count reads from the tool-call record, not from the agent's report; and, when the skill has a file that some tasks do not require, include a case in which that file's condition does not hold, to count reads that nothing requires.
- Keep the files as separate files that the agent reads. Do not copy them into the body at build time, load them through a host-specific command or hook, or make a read-rate test a merge gate.
