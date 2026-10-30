# Host capabilities and evidence

Use [SKILL.md — 6. Check capabilities and retain evidence](../SKILL.md#6-check-capabilities-and-retain-evidence) for capability checks and limits. Tool names, context inheritance, message delivery, permissions, and persistence vary across Codex hosts. Commands, timer behavior, cloud rules, permission inheritance, and persistence observed in another runtime do not establish Codex behavior. Discover deferred capabilities only when needed through the host's available tool inventory or search facility.

## Documented reference-host schemas

The following examples reflect schemas exposed on 2026-10-13. They are not universal Codex API names. Apply **6. Check capabilities and retain evidence** when using them in the current host.

| Exposed tool | Relevant contract |
| --- | --- |
| `collaboration.spawn_agent` | Creates a native child. Accepts available `model`, `reasoning_effort`, and `fork_turns` options. A full-history fork inherits model and effort. For an authorized model or effort override, choose a `fork_turns` value that the current host explicitly permits with that override. |
| `collaboration.send_message` | Delivers a message to an existing agent, including its controller. It does not trigger an idle child's new turn. |
| `collaboration.followup_task` | Sends work to an existing non-root agent and can trigger its idle turn. |
| `collaboration.wait_agent` | Waits for mailbox activity or user steering with a timeout. Its summary is not the result payload. |
| `collaboration.list_agents` | Lists agents in the current thread tree. See [SKILL.md — 2. Reconstruct the current task](../SKILL.md#2-reconstruct-the-current-task) for ownership reconciliation. |
| `collaboration.interrupt_agent` | Interrupts an identified agent's current turn. It does not establish that every external process launched by that agent stopped. |
| `exec_command` and `write_stdin` | A continuing command returns a numeric `session_id`. Retrieve new output and terminal exit through `write_stdin`. |
| `functions.exec` and `functions.wait` | An orchestration call may return a string `cell_id`. Call `functions.wait` only after a running-cell response. A cell can contain a tool call that subsequently returns a separate command session. |

Keep native agent identities, command session IDs, and orchestration cell IDs separate. Preserve the tool namespace with each handle. Waits for one handle type do not consume results from another.

In this host, call collaboration tools directly, outside `functions.exec`. Await nested tool promises inside `functions.exec`. The isolate discards unawaited promises when it ends. Obey current wait bounds and communication limits rather than copying another runtime's timing advice.

Pass only model and effort values the current schema permits. Respect instructions governing overrides. The native spawn schema here has no speed selector, so native Fast mode cannot be confirmed from that schema.

Permissions also vary by tool and path. A writable workspace can contain protected directories. Use a staged artifact or patch when direct writes are unavailable. Do not broaden a sandbox merely to preserve an assumed workflow.

## Verified active-session bridge

- **Status:** verified 2026-10-13.
- **Observation:** One native watcher observed four existing external CLI groups. A `collaboration.send_message` reached the active root thread.
- **Scope:** This establishes native watcher message delivery during that active session. It does not establish wake-up after a final response, application closure, or session reclamation.
- **Operational consequence:** Use [background-work.md — Native owner and read-only watcher](background-work.md#native-owner-and-read-only-watcher) for watcher mechanics and [SKILL.md — 4. Wait, validate, and continue](../SKILL.md#4-wait-validate-and-continue) for event handling.

## Subscription discovery limits

- **Status:** documented host inventory and discovery observation, 2026-10-13.
- **Observation:** No suitable general `automation_update` or `subscribe_timer` tool for local CLI thread wake-up appeared in the reference-host discovery. Page or Sites automations have a different scope.
- **Scope:** This is a host-specific discovery result. It does not establish that every Codex environment lacks timers or subscriptions.
- **Operational consequence:** Use [background-work.md — Wait, consume, continue](background-work.md#wait-consume-continue) to discover and verify subscriptions or continue active-turn monitoring.

Active waits and sleeps do not establish a future subscription. Do not invent callbacks, promise a later notification, create cron jobs, change persistent configuration, add providers, send or configure external notifications, or configure persistent schedules by implication.

## Evidence labels

Use [SKILL.md — 6. Check capabilities and retain evidence](../SKILL.md#6-check-capabilities-and-retain-evidence) for reusable facts and task-specific evidence locations. Mark uncertain behavior unverified until evidence supports it.
