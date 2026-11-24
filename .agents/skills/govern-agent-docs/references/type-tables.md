# Type tables

Pass 1 of `SKILL.md` gives the classification order and omission conditions. Pass 2 gives the authority order. Pass 4 gives the lifecycle.

- [Dimensions](#dimensions)
- [Boundary cases of the classification order](#boundary-cases-of-the-classification-order)
- [Folded kinds](#folded-kinds)
- [What each type holds](#what-each-type-holds)
- [Force, stability, change and loading](#force-stability-change-and-loading)
- [Common mixing and its test](#common-mixing-and-its-test)

## Dimensions

The types differ along these dimensions. Use them to split a unit that mixes kinds; the order in pass 1 of `SKILL.md` then gives each part its type.

| Dimension | Values | What it separates |
| --- | --- | --- |
| Binding force | Binding (must be obeyed); explanatory (reasons, examples, experience, history); enforced by a host program | Work state, knowledge and pitfalls, and archive and evidence from the binding types; host configuration from the rest |
| Stability | Long-term; evolves with the design; frozen; valid only within this task | Decision records (frozen), current design and contract (evolving) and work state (this task) |
| Scope | Whole repository; subtree or path; a kind of task; one task | Whether an entry file sits at the root or is nested |
| When needed | Every task; on touching a path; on a kind of task; when checking | The loading tier, never the type |
| Source and change authority | Owner decision; fact verified from code or run results; executor experience | Decision records from the project register and the current design and contract |
| Portability | General across projects; this project only | General canonical text from project clauses in engineering rules |
| Reader scope | All shared workers; one person or one machine | Whether content enters the repository |

## Boundary cases of the classification order

Apply these with the step of pass 1 they name:

- **Step 3, decision record.** Mark a separately kept draft ruling awaiting approval `proposed`. A complete candidate contract takes step 5. An open question or a decision that affects only the current task is work state. Current text a decision record cites keeps the type of its canonical source. A superseded decision stays a decision record with its supersession link.
- **Step 4, archive and evidence.** Evidence may be archived on its own while its task is still open.
- **Step 5, current design and contract.** Mark a candidate contract `proposed`. A question that only asks for a decision stays in work state; the basis of an approved design is a decision record.
- **Step 6, principles and methodology.** Coding, naming, authorisation-boundary and branch constraints that can be checked item by item go to the rulebook or the project register by scope.
- **Step 7, rulebook and project register.** The approval basis stays in the decision record.
- **Step 8, runbook.** Steps that must be performed are runbook text. The checked-off record of one run is work state; proof kept after closure is archive and evidence.

## Folded kinds

These kinds have no type of their own:

- Nested entries and directory index pages carry the entry file's routing.
- Exemption registers, exception lists and adoption registers are the project register.
- Ledgers, plans, loop files and handoff pages are work state.
- Superseded documents, execution logs, and verification and review reports are archive and evidence.
- Reference material is no type: write requirement sources in the basis section of the current design and contract, and leads on external tools in knowledge and pitfalls.
- Memory is a mechanism and no type; place its content as pass 5 of `SKILL.md` directs.
- A skill is a packaging and loading method and no type; choose it as pass 6 of `SKILL.md` directs.
- Summaries and display artefacts are no type. Apply **One canonical source** in `SKILL.md`.

## What each type holds

| Type | The one question it answers | Holds | Does not hold |
| --- | --- | --- | --- |
| Entry file, with nested entries and directory index pages | Before acting in this scope, what must I know and where do I read it? | The authority order; scope and task routes; the location of required guidance | Repository overviews and introductions; rule text that needs expanding; history; progress; command step details; knowledge entries |
| Principles and methodology | How does this repository judge: in what trade-off order, and how where no rule applies? | Numbered principles with strength words; each principle's reason; scope; how to handle a conflict with the rulebook | Detailed rules checkable item by item (rulebook or project register); the words of a single decision (decision record; link it here); progress |
| Rulebook | What general engineering rules are shared across projects? | Stable rule numbers; strength words; checkable criteria; general requirements of the exemption procedure | Adoptions, tightenings, exemptions and project-only conditions |
| Project register | Which engineering rules does this project adopt, tighten or relax, and which checkable constraints are its own? | Adopted rules; tightenings; frozen scope; exemptions, each with its ID, the rule ID it relaxes, scope, conditions of effect, review or expiry condition, and a link to the approving decision record; project-only rules with local IDs and strength words | New general rules; long design rationale; blanket claims such as "a principle overrides the rulebook" that are not registered as exemptions |
| Decision record | What did the owner decide, when, for what scope, and what did it supersede? | One decision per record, using **Decision record** under **Entry formats** in `SKILL.md` | Design text; operating steps; agent guesses the owner has not confirmed |
| Current design and contract | What should the system do, and what do its interfaces and data look like? | A status header under **Run the lifecycle** in `SKILL.md`, with a successor link when superseded; the applicable branch when current only on one branch; the date or revision last verified; the requirement basis; behaviour, interfaces, data structures, invariants, error codes | Engineering rules on how work must be done; task progress; undated implementation status |
| Runbook | How exactly is this operation performed? | Preconditions; executable commands; expected results; what to do on failure; links only, for the decisions it relies on | Policy decisions themselves; the record of one run; local absolute paths |
| Work state | Where does this task stand, and what is next? | Goal; completion criteria; status per item; verified and unverified evidence; open questions; links only, for the decisions it relies on | Standing rules; owner decisions recorded only here; closed old items |
| Knowledge and pitfalls | Which project facts, invisible in the code and history, will the next work need? | Verified phenomena, conditions of application, possible causes, optional diagnosis and workaround practices | Owner decisions; personal preferences and traits specific to one machine; content readable directly from the code; credentials |
| Archive and evidence | What did things look like before, and how was something proved? | Superseded documents; execution records; verification and review reports; each with status, date, successor link and what it proves | Current rules; embedded binding values |
| Host configuration | How does each host read the same source, and which irreversible actions are blocked by force? | Import declarations and adapter links; the minimum hooks and deny rules the project approved; path-approval maps | Rule text, since hook output only points to documents; blocking of preferences; configuration pointing to local absolute paths; skill copies without their source marked |

## Force, stability, change and loading

Where this table says "pass 4", the change follows the lifecycle and approval of pass 4 of `SKILL.md`. The scope and conflict order of binding text follow pass 2.

| Type | Binding force | Stability | Who may change it | How the agent loads it |
| --- | --- | --- | --- | --- |
| Entry file | Clauses written directly bind by their own function; routes and summaries only point to canonical sources | Long-term | Current clauses and the authority order: pass 4. Faithful summaries and routes update with their canonical source in the same change, under ordinary review | Which root and nested entries load automatically depends on the host, start location and configuration; otherwise read by entry path or route. Directory index pages load by link |
| Principles and methodology | Binding | Long-term | Pass 4 | The summary in the entry file is always loaded; the full text loads by link |
| Rulebook | Binding | Long-term | The rulebook's maintainer approves; consumers never change copies | Routed by an entry-file line; when packaged as a skill, it may also load by its description |
| Project register | Binding | Evolves with the project | Pass 4 | Linked by section from the entry file or rulebook |
| Decision record | Decisions and authorisations that take effect on their own bind; cited current text keeps the level of its canonical source | Frozen: only superseded, revoked, or expired by its expiry condition | See **Capture, hand off, promote, clean** in [memory-entries.md](memory-entries.md) and **Run the lifecycle** and **Decision record** in `SKILL.md`. | Read through the entry file's memory route |
| Current design and contract | Binds system behaviour | Evolves with the design | Pass 4 | Routed from the entry file by path or domain |
| Runbook | Binds execution steps | Evolves with the tools | Updated in the same change as its scripts, and tested after its steps change; pass 4 | Linked by task. See **Skill or plain document** in [skills-and-hosts.md](skills-and-hosts.md). |
| Work state | No rule authority | Valid only within its task | The executor changes it at any time; archived or deleted when the task closes | Read by the task flow or a hook. See **Nested entries** in `SKILL.md` for the shared task route. |
| Knowledge and pitfalls | No rule authority; see **Staleness and conflicts** in [memory-entries.md](memory-entries.md) | Long-lived, but goes stale | See **Promote** in [memory-entries.md](memory-entries.md); pass 4 | Read through the entry file's memory route |
| Archive and evidence | No current authority | Frozen | Only added or moved in; the body never changes, and only successor links may be added | Opened only by link; never listed in a current route |
| Host configuration | See **Host controls** in `SKILL.md`. | Long-term | Pass 4 | Read by the host program |

## Common mixing and its test

| Type | Common mixing | Test |
| --- | --- | --- |
| Entry file | Overviews, command details and design facts | Apply the **Entry test** of pass 3 in `SKILL.md` under its stated conditions. |
| Principles and methodology | Detailed rules checkable item by item, or principles written into the register | Can you answer "complies" or "does not comply" for a given piece of code? If so, it is a detailed rule. |
| Rulebook | Project paths and allow-lists | Would this still hold in another project? If not, it belongs in the project register. |
| Project register | Exemptions without bounds or an approval link | Does this relax a rule? If so, it must be an exemption with a decision record. |
| Decision record | Approval words kept only in work state, plans, loop files or personal memory | Must it still be obeyed after the task closes? If so, write it as a decision record. |
| Current design and contract | Task breakdowns and "not yet implemented" | Will this sentence change as the task progresses? If so, it is work state. |
| Runbook | Reusable steps mixed with one run's to-dos | Can the next operation of this kind follow it as written? The parts that cannot are work state or archive. |
| Work state | Standing rules or authorisations | The decision-record test: must it still be obeyed after the task closes? |
| Knowledge and pitfalls | Personal and machine-local content, or entries that carry routes | Apply the test question of pass 5 in `SKILL.md`; routes belong in the entry file. |
| Archive and evidence | Binding values embedded in evidence, such as a budget cap | Does this number constrain new work? If so, move it to the type that holds the rule, and let the evidence link to it. |
| Host configuration | Rule text in hook output; skill copies with no marked source in host directories | Is this a written rule? If so, move it into a document. |
