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

1. **Load first, every time.** On each explicit invocation, before any other work, resolve only the listed names against installed skills and invoke each the user did not exclude in this message, in list order, applying its instructions as soon as read. Invoke a member again even when it was invoked earlier in the session; an earlier load, a summary or a recollection of its instructions does not count. Use the host's native explicit skill-loading mechanism when available, and obtain the full instructions, reading any returned files rather than treating a successful call as proof of loading.

2. **Respect host limits.** If native loading is unavailable or replaces earlier skills, read the full actual installed instruction files where the host supports instruction-by-file, and consider all members together. File reading does not create native activation, metadata or permissions. Disclose any host limit that prevents equivalent use. Name each missing or unreadable member and do not claim complete activation or substitute remembered text.

3. **Apply as directly invoked.** Do not re-filter this explicit request through automatic selection triggers. Honor each member's substantive prerequisites, exclusions and permissions. Preserve the user's task scope and overrides, and each member's own authority, lifecycle and conditions for stopping. Re-invoking a member restores its instructions; its own rules decide what the current request needs, so reuse an existing binding brief and completed work under those rules rather than creating a second brief or repeating finished steps. Resolve conflicts through the existing instruction hierarchy and the members' own priorities; ask the user about genuinely unresolved material conflicts.

4. **Continue faithfully.** Between explicit invocations, on later tasks, compaction or resumption, restore any needed actual member instructions in full, not stale summaries, and continue under each member's lifecycle. Do not re-enable a member the user disabled until the next explicit invocation of ensemble; that invocation re-enables it, and you say so, unless the user excludes it in the same message.

## Self-check

- [ ] Every listed member the user did not exclude in this message was invoked on this invocation, before other work and even if invoked earlier, and its full actual instructions were obtained, or the unavailable member and host limit were named without a complete-activation claim.
- [ ] Applicable member instructions are considered together as explicit invocations, without inventing native capabilities, authority or list-order precedence.
- [ ] User overrides, member prerequisites and lifecycles, the binding brief and completed work remain intact.
