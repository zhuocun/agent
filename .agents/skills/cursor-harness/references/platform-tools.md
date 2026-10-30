# Platform tools

Use this reference for Cursor tools and platform rules during long, concurrent work. Availability varies across IDE, Cloud Agent, and self-hosted workers, and changes over time. Check what is present before relying on it.

## Dynamic tools (documented)

- Discover dynamic tools with `GetDynamicTools` before calling them with `CallDynamicTool`. This applies to MCP servers, the `cursor` namespace, and Cloud Agent diagnostics. Aim for one discovery call followed by one invocation.
- When you know the namespace and tool name, discover that single tool. Read its full description and usage rules.
- A namespace in `needsAuth` or `error` state is unusable until fixed. Authenticate through its `mcp_auth` tool only when needed.

## Built-in `cursor` namespace (documented)

- `AwaitShell`: shell waiting and sleep; see [background-work.md](background-work.md#shell-job-mechanics-documented).
- `Task`: subagents; see [delegation.md](delegation.md).
- `TodoWrite`: the in-session view; see [task-ledger.md](task-ledger.md#where-to-keep-it).
- `WebFetch`, `WebSearch`, `CreateGoal`/`UpdateGoal`, and `GenerateImage`: available on demand. Read the schema first.

## Cloud Agent diagnostics (`cursor-cloud`, documented)

- `get-message-queue`: pending user follow-ups; see the [wait routine](background-work.md#wait-routine).
- `run-info`: run identity, branch, model, and run URL.
- `get-events`: run lifecycle events, including otherwise silent MCP authentication failures.
- `list-cloud-agents` and `batch-fetch-details`: other runs and their transcripts. Read large transcripts through a subagent, never directly.

## Subscriptions (`cursor-subscriptions`, documented)

- `subscribe_timer`: one-shot or recurring safety timers; see [background-work.md](background-work.md#safety-timers).
- `subscribe_slack_thread`, `subscribe_slack_channel`, `subscribe_linear_issue`, and `subscribe_linear_comment`: event-driven wake-ups.
- `list_subscriptions` and `unsubscribe` (safety-timer use **verified 2026-10-12**): check subscriptions during turn-start inventory, and remove each subscription when its ledger entry closes.

For Slack or Linear events, use the matching subscription above rather than a safety timer; for GitHub or CI events, do so only if `GetDynamicTools` lists such a subscription.

## Cloud Agent and self-hosted rules that affect bookkeeping

- Before the first commit on a self-hosted machine, check `user.name` and `user.email`. Git identity comes from the machine's configuration. Set identity per repository only if unset.
- Use the platform's pull-request tool, from `GetDynamicTools` or the built-in namespace, for pull requests, never forge CLIs. If the tool refuses, for example because the forge host is unconfigured, treat the refusal as final for the run. Record it in the ledger and tell the user.
- Shell working directory and environment variables persist between calls in one session. For tmux environment rules, see the [launcher](background-work.md#tmux-run-plus-waiter-verified-2026-10-12).
- The terminals folder contains one file per shell session with a metadata header. Read the first lines before starting a duplicate process.
