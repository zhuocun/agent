# Adoption in an existing repository

Run the steps in order.

1. **Inventory.** List the existing entry files, canonical sources, skills, and content outside the repository that work still depends on. Check the hosts in use and representative start directories only when loading behaviour is really in doubt.
2. **Classify.**
   - Give each file or separately addressable section one type by pass 1 of `SKILL.md`. Record a unit that fits no type as "mixed" or "out of scope".
   - Split a mixed memory entry along the dimensions in **Dimensions** of [type-tables.md](type-tables.md) first, then decide each part's destination by its function and by **Place memory** in pass 5 of `SKILL.md`. Mark duplicate or stale entries for cleanup, and handle them by **Capture, hand off, promote, clean** and **Staleness and conflicts** in [memory-entries.md](memory-entries.md).
3. **Find mixing and contradictions.** Look for these signals:
   - A section mixes independent task state, approval basis or historical evidence into other content.
   - A stable document holds progress or to-dos, or work state holds standing rules or authorisations.
   - A long-term project decision lives only in personal memory, work state or another staging place, with no decision record in the repository.
   - Evidence holds a value that constrains new work, and no current rule carries it.
   - One rule reads differently in two places, or an index lists a superseded document as current.
   - A version-controlled document links to an ignored file or a local path.
   - A rule that must be obeyed has no route from the entry file.
4. **Decide the treatment.** Use **Adoption change description** in pass 4 of `SKILL.md`. For standing guidance found only in work state, look for its governing source or original approval. Capture a confirmed cross-task decision under **Capture, hand off, promote, clean** in [memory-entries.md](memory-entries.md). Keep unconfirmed guidance pending. Apply the lifecycle and approval of pass 4 to each change. Approved actions that do not depend on each other may go first; the person with authority decides conflicting clauses.
5. **Rewrite the entry file and host adapters.** Rewrite the entry file and its routes by pass 3. Add an adapter only for a host still in use that has a real loading gap. Resolve same-name skills with different content as **Where a skill lives** in [skills-and-hosts.md](skills-and-hosts.md) directs.
6. **Migrate memory.** Migrate by capture, promotion, verification and cleaning, in that order. Confirm the repository's canonical source, the applicable branch and the entry route before you handle the old project copies. Valid preferences in personal entries stay at user level.
7. **Verify.** Check the change by pass 8 of `SKILL.md`. If you find a discovery miss or misapplication, adjust the trigger, target or section size it concerns.
