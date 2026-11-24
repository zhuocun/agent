# Memory entries

Use **Place memory** to choose the destination.

- [Content and destination](#content-and-destination)
- [Capture, hand off, promote, clean](#capture-hand-off-promote-clean)
- [Layout and findability](#layout-and-findability)
- [Staleness and conflicts](#staleness-and-conflicts)

## Content and destination

Split an entry that mixes kinds, then send each kind to its place:

| Content | Destination |
| --- | --- |
| The owner's decisions | Decision record |
| Standing authorisations addressed to agents | Decision record, as an authorisation |
| This project's knowledge and pitfalls | Knowledge entry |
| Routes and context maps | The entry file; delete the copy in memory |
| Personal collaboration preferences | Personal memory |
| Tool and machine traits | Decide by the test question |
| Stage status and handoff snapshots | Work state, or archive and evidence; never memory |

- **Destinations.** Repository memory holds the owner's decisions and authorisations for this project, and knowledge and pitfalls that hold for other executors within the project's conditions of application, as decision records and knowledge entries with no separate inbox or new type. Personal memory holds communication and reporting preferences, preferences on dividing work between models and hosts, local paths and machine-specific traits, accounts by name and purpose without credentials, and personal tool habits shared across repositories, in a user-level location outside every repository.

## Capture, hand off, promote, clean

Write a personal item worth keeping in the same turn when you have user-level write access; otherwise tell the owner of that memory what is pending. These steps handle repository memory:

1. **Capture.** In the same turn, record each long-term project decision, authorisation or reusable finding that is new or changed. Record a brief approval together with the one locatable proposal, options and scope it approves. When the object or scope is ambiguous, record what remains unresolved as pending in work state and leave the current rules in force. If work state is unwritable, report the same pending information to the owner or an authorised maintainer. Record project knowledge with a phenomenon and conditions that can be rechecked.
2. Follow **Hand off** in pass 5 of `SKILL.md`.
3. **Promote.** Write the decision basis as a decision record. When a decision changes current text, follow **Run the lifecycle** for that text and link the decision record from it. When an authorisation is itself a complete executable rule, the decision record may be its canonical source. Write knowledge into a knowledge entry after verification. Before the next work that depends on the rule, confirm that the change has reached the applicable branch and can be found from the entry file.
4. **Clean.** After verifying that the canonical source works, delete the pending copies and the project copies in personal memory.

## Layout and findability

- **Layout.** By default, keep decision records in `docs/decisions/`, one file per decision plus a `README.md` index, and knowledge in `docs/knowledge/`, a `README.md` index plus one file per entry. While decisions and entries are few, `docs/decisions.md` and `docs/knowledge.md` may replace them, with one numbered section per item. Another layout is allowed when the entry file's routing line points to the actual location and each entry has every field of its format.
- **Findability.** When the repository has decision records or knowledge entries, the entry file, such as `AGENTS.md`, points to their location in one line. For example: before a scope, authorisation or design judgement, read the applicable decision records; before troubleshooting, testing or changing a tool version, look up knowledge entries by symptom and task. Use the repository's actual paths or sections. When an entry needs indexing, use **Index line**.

## Staleness and conflicts

Before acting on a knowledge entry, confirm by its `verify` method that it still holds under current conditions. The maintainer updates, deletes or moves to evidence an entry that is stale. When personal memory holds a project decision the repository does not record, check the original approval and hand it off by the capture steps; the current repository rules stay in force, and work that depends on the unconfirmed decision waits.
