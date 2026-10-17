---
name: ensemble
description: >-
  Load the maintained member skills when the user explicitly invokes ensemble or
  asks to load its member set. A skill-loading shortcut equivalent to explicitly
  invoking each member, not model voting or work coordination. Do not select it
  automatically from the task's subject.
---

# Ensemble

Treat an explicit invocation as explicit invocation of every member below. Use their actual installed instructions, not copies of their rules in this skill. Each member remains independently usable.

Priority order: **existing instruction hierarchy and user overrides → faithful member behavior → convenience.** The list sets loading order, not authority between members.

## Members

- communicate
- raise-ambition
- burst

## Procedure

1. **Load before work.** Resolve only the listed names against installed skills. Load in list order before substantive work, applying each member's instructions as soon as read. Use the host's native explicit skill-loading mechanism when available, and obtain the full instructions, reading any returned files rather than treating a successful call as proof of loading.

2. **Respect host limits.** If native loading is unavailable or replaces earlier skills, read the full actual installed instruction files where the host supports instruction-by-file, and consider all members together. File reading does not create native activation, metadata or permissions. Disclose any host limit that prevents equivalent use. Name each missing or unreadable member and do not claim complete activation or substitute remembered text.

3. **Apply as directly invoked.** Do not re-filter this explicit request through automatic selection triggers. Honor each member's substantive prerequisites, exclusions and permissions. Preserve the user's task scope and overrides, and each member's own authority, lifecycle and conditions for stopping. Reuse an existing binding brief and completed work under those rules, rather than creating a second brief or repeating finished steps. Resolve conflicts through the existing instruction hierarchy and the members' own priorities; ask the user about genuinely unresolved material conflicts.

4. **Continue faithfully.** On later tasks, compaction or resumption, restore any needed actual member instructions in full, not stale summaries, and continue under each member's lifecycle. Do not silently re-enable a member the user disabled.

## Self-check

- [ ] Every listed member's full actual instructions were obtained, or the unavailable member and host limit were named without a complete-activation claim.
- [ ] Applicable member instructions are considered together as explicit invocations, without inventing native capabilities, authority or list-order precedence.
- [ ] User overrides, member prerequisites and lifecycles, the binding brief and completed work remain intact.
