---
name: ensemble
description: >-
  Load the maintained member skills when the user explicitly invokes ensemble or
  asks to load its member set, invoking every member again on each invocation even
  if it was invoked earlier. A skill-loading shortcut equivalent to explicitly
  invoking each member, not model voting or work coordination. Do not select it
  automatically from the task's subject.
---

# Ensemble

Treat every explicit invocation, including a repeat in the same session, as a fresh explicit invocation of every member below, even one invoked, loaded or active earlier. Use their actual installed instructions, not copies of their rules in this skill. Each member remains independently usable.

Priority order: **existing instruction hierarchy and user overrides → faithful member behavior → convenience.** The list sets loading order, not authority between members.

## Members

- communicate
- raise-ambition
- conductor

## Procedure

1. **Load first, every time.** On each explicit invocation, before any other work, resolve only the listed names against installed skills and invoke each member the user did not exclude in this message, in list order, applying its instructions as soon as read. Use the host's native explicit skill-loading mechanism when available, and obtain the full instructions, reading any returned files rather than treating a successful call as proof of loading. After reading each member's instructions, follow **Read member references** for that member. A load or read meets this procedure only if you made it at or after the latest event from which **Read member references** counts a session. A summary or recollection of a load or read never meets it, because an installed member's files can change during a session.

2. **Read member references.** Read each of the member's reference files whose read condition, as the member states it, holds when you finish reading the member's instructions, and follow the member's stated timing for each later read, including a reread of a file already read. Read each such file in full unless the member states a narrower extent. Where a read condition refers to a session, such as a first use in a session, count the session from the latest explicit invocation or, if later, from the latest start of a later task, compaction or resumption under **Continue faithfully**.

3. **Respect host limits.** If native loading is unavailable or replaces earlier skills, read the full actual installed instruction files where the host supports instruction-by-file, and consider all members together. File reading does not create native activation, metadata or permissions. Disclose any host limit that prevents equivalent use. If a member is missing or unreadable, name it and do not claim complete activation. If you cannot read a reference file that **Read member references** requires, name it and disclose the resulting limit on applying the member. Do not substitute remembered text for a required read.

4. **Apply as directly invoked.** Do not re-filter this explicit request through automatic selection triggers. Honor each member's substantive prerequisites, exclusions and permissions. Preserve the user's task scope and overrides, and each member's own authority, lifecycle and conditions for stopping. Re-invoking a member restores its instructions; its own rules decide what the current request needs, so reuse an existing binding brief and completed work under those rules rather than creating a second brief or repeating finished steps. Resolve conflicts through the existing instruction hierarchy and the members' own priorities; ask the user about genuinely unresolved material conflicts.

5. **Continue faithfully.** Between explicit invocations, before starting a later task and before continuing after each compaction or resumption, apply this rule to each member that an explicit invocation loaded, that the user has not disabled since and whose own lifecycle has not ended. Read the member's actual installed instructions in full under **Respect host limits**, then follow **Read member references** for that member, and continue under the member's lifecycle. A clarification, a status request or a further step on the current task does not start a later task. Do not re-enable a member the user disabled until the next explicit invocation of ensemble; that invocation re-enables it, and you say so, unless the user excludes it in the same message.

## Self-check

- [ ] **Load first, every time**, **Read member references** and **Respect host limits** were followed whenever each rule applied, under its stated conditions and fallbacks.
- [ ] Applicable member instructions are considered together as explicit invocations, without inventing native capabilities, authority or list-order precedence.
- [ ] Every requirement of **Apply as directly invoked** and **Continue faithfully** was met, at the times and under the conditions each rule specifies.
