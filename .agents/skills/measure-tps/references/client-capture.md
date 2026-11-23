# Client capture

- [Before any run](#before-any-run)
- [Codex](#codex)
- [Claude Code](#claude-code)
- [Devin](#devin)
- [Antigravity](#antigravity)
- [Direct model APIs](#direct-model-apis)

## Before any run

Use the intended tool's installed version to check flags and protocol support. Resolve the exact model ID with the active route's model list or metadata. Use provider response evidence to check the observed model, effort, and tier wherever available. Keep a command template and sanitized metadata, not a shell history or configuration dump. Use the route's established authentication without exporting its credentials from the native tool. Work in a temporary, trusted, non-sensitive project with the same permissions and tool availability for each comparable run.

Run the examples from the benchmark directory and set `TPS_SKILL_DIR` to the absolute path to this skill. Use supported model and effort settings for the chosen route. Set `TPS_PROMPT` to the exact controlled prompt for examples that pass it as an argument.

For Claude Code and Antigravity, `scripts/capture.py` requires Python 3.10 or newer on POSIX. Pass the installed executable or the existing route-preserving wrapper after the literal `--`. The script launches that command, filters its output in memory, discards its stderr, and writes the trace to stdout. Check both the exit code and the terminal status. `--expected-model` checks the reported model where available and otherwise checks the client's selection. The latter provides configuration evidence only. The script retains known tier and speed strings where the client reports them. Use a separate filtered adapter or authorized provider telemetry to collect native token counts when needed.

For other clients, apply the event mappings below with a streaming driver. Start the clock before launching the process or creating the request. For a live protocol with a distinct prompt submission, add a `submit` event immediately before the write and flush or HTTP stream creation. Read every line or SDK stream event as it arrives. Timestamp arrivals before doing further work. Apply the safety and workload checks before saving any text. Give the driver a deadline, interrupt through the supported protocol on expiry, and save a censored outcome. [Trace and metrics](trace-and-metrics.md)

## Codex

Use the bundled app-server collector with Python 3.10 or newer for incremental text on a supported local route. Prepare a UTF-8 prompt file that contains the chosen prompt. Set the exact model, effort, and requested tier from the installed route. Set `TPS_CODEX` to the intended executable or an executable wrapper that supports `app-server --stdio`. Use `--tier default` for an explicit standard-speed request. If the workload ends with an exact marker, pass it with `--expect-suffix`.

```sh
python3 "$TPS_SKILL_DIR/scripts/capture_codex.py" \
  --codex "$TPS_CODEX" --model "$TPS_MODEL" --effort "$TPS_EFFORT" \
  --tier "$TPS_TIER" --prompt-file prompt.txt --output codex-turn.jsonl \
  --timeout 240 --expect-suffix END > codex-attempt.json
```

Use a new path for `--output` on every attempt. Retain the separate filtered stdout JSON to record status, requested and configured controls, client version when available, and the `native_last_usage` counters from the last matching `thread/tokenUsage/updated` event. Keep those counters separate from the visible token calculation.

The collector uses a fresh ephemeral thread in a temporary directory and inherits the existing authentication environment. If the intended route depends on project settings, preserve them through the approved wrapper or another matching native capture. The emitted `configured_model`, `configured_effort`, and `configured_tier` describe resolved configuration. Treat the served tier as unavailable when the native protocol provides no attestation. For an unfinished turn with known IDs, the collector attempts a bounded protocol interrupt before terminating the local app-server. On POSIX it signals the process group. Retain any safe configured provider identifier and interrupt evidence from the stdout report. Provider-side cancellation remains unverified.

`codex exec --json` exposes a stream of item lifecycle events. A completed `agent_message` describes its full text at item completion. With completion-only output, measure launch-to-turn completion and visible end-to-end TPS. A final item's timestamp measures final message receipt. Use `--ephemeral` where supported. Pin model and supported overrides with `--model "$TPS_MODEL"`, `-c "model_reasoning_effort=$TPS_EFFORT"`, and `-c "service_tier=$TPS_TIER"` as needed. Keep any required profile or wrapper. The configured `fast` preference maps to an upstream `priority` request on supported stock routes. Confirm the meaning on the active route. [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode) · [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

For a custom incremental driver, use the installed `codex app-server --stdio` or the equivalent entry point for the intended Codex route. Export the installed protocol including experimental fields with `codex app-server generate-json-schema --experimental --out "$TPS_SCHEMA_DIR"`. Filter the following JSONL exchange in memory.

1. Send `initialize` with a request ID and `params.clientInfo` containing `name` and `version`, with an optional `title`. Set `params.capabilities.experimentalApi: true` for the experimental fields used by the bundled collector. Wait for success, then send the `initialized` notification.
2. Send `thread/start` with `ephemeral: true`, the scratch `cwd`, the exact `model`, and the approved sandbox and approval policy. Under a read-only benchmark policy use `sandbox: "read-only"` and `approvalPolicy: "never"` where allowed. Where available, use the experimental `allowProviderModelFallback: false` and `dynamicTools: []` fields as the bundled collector does. Resolve effort with the thread's `config.model_reasoning_effort` or a per-run app-server override. Resolve the requested tier with the documented thread control `serviceTier` where available. Keep the configured provider. Check `result.model`, `result.modelProvider`, `result.reasoningEffort`, and `result.serviceTier` where the schema provides them. These fields describe resolved configuration.
3. Mark submit and send `turn/start` with a new request ID and `params` containing `threadId` from `result.thread.id` and `input: [{"type":"text","text":"YOUR PROMPT"}]`. Where supported, `serviceTierForTurn` overrides the tier for that turn only. On `turn/start`, `serviceTier` and `effort` set the current and subsequent turns. The bundled collector uses a fresh thread and sets both on its only turn. Confirm the installed schema and use `summary: "none"` if supported for the route and model.
4. For the matched thread and turn, timestamp `item/agentMessage/delta` and retain `params.delta` for the measured message. Match deltas to `item/completed` by `itemId` and use the completed text for validation without appending it. Record the occurrence of tool items. Drop reasoning, summaries, and tool payloads. Check `model/rerouted`, and retain only safe usage counters from `thread/tokenUsage/updated` with their documented scope.
5. End at `turn/completed` for that turn. Require `params.turn.status == "completed"` for success. Actual backend model, effort, and tier require provider evidence if the stream exposes only preferences. Mark unavailable facts accordingly.

[Codex App Server protocol](https://learn.chatgpt.com/docs/app-server)

## Claude Code

Use `--no-session-persistence` and the partial-message mode. For the controlled workload use `--tools ""` where the installed version supports it. Keep the normal auth and configuration. Minimal startup modes such as `--bare` can change authentication and therefore the route. [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)

```sh
python3 "$TPS_SKILL_DIR/scripts/capture.py" claude --timeout 300 \
  --expected-model "$TPS_MODEL" -- \
  claude -p --output-format stream-json --verbose --include-partial-messages \
    --no-session-persistence --model "$TPS_MODEL" --effort "$TPS_EFFORT" \
    --tools "" -- "$TPS_PROMPT" > claude-turn.jsonl
```

The relevant payload is `type: "stream_event"`, nested `event.type: "content_block_delta"`, with `event.delta.type: "text_delta"` and text in `event.delta.text`. Validate against the final assistant text and a successful `result` record. The nested API `message_start`, when present, may report model and usage. Confirm the effective effort through documented telemetry if exposed. Keep CLI fast-mode configuration and Anthropic API service-tier evidence separate. Follow the installed version's and route's fast-mode instructions for a speed comparison. Keep `usage.speed` separate from `usage.service_tier` where both are available. [Claude Agent SDK streaming events](https://code.claude.com/docs/en/agent-sdk/streaming-output) · [Claude Code fast mode](https://code.claude.com/docs/en/fast-mode)

## Devin

Use `devin models` on the intended route, then pin the exact slug. Stable shortcuts such as `opus` can resolve to newer models over time. Also check for Adaptive, Fusion, or a configured fallback. For a simple end-to-end sample, run `devin --model "$TPS_MODEL" -p "$TPS_PROMPT"` in the trusted benchmark directory. Treat final-only stdout as completed output and use its observed delivery boundary. For local incremental capture, confirm the installed release exposes `devin acp --help` and use `devin acp --model "$TPS_MODEL"`. Where the intended route is Devin Cloud, use its supported interface and model controls. The local ACP model flag applies only to local sessions. [Devin CLI commands](https://docs.devin.ai/cli/reference/commands) · [Devin models and reasoning controls](https://docs.devin.ai/cli/models) · [Devin ACP integration](https://docs.devin.ai/cli/acp/zed)

For an ACP v1 stdio client, send newline-delimited JSON-RPC 2.0 messages. Confirm support on the installed Devin release before using this mapping.

1. Send `initialize` with `protocolVersion: 1` and only the supported capabilities. Create a fresh session with `session/new`, the absolute scratch `cwd`, and an empty `mcpServers` array.
2. Read the model and effort choices that the server advertises in `configOptions`, including `model` and `thought_level` categories where present. Use the advertised `configId` and value in `session/set_config_option` and confirm the returned `currentValue`. Where effort is only configurable through a supported interactive control, make and verify that setting in the measured session or report it unavailable.
3. Mark submit and send `session/prompt` with the returned `sessionId` and `prompt: [{"type":"text","text":"YOUR PROMPT"}]`. In matching `session/update` notifications accept `params.update.content.text` only for `sessionUpdate: "agent_message_chunk"` and `content.type: "text"`. Track message IDs where present. Ignore thought updates, note tool calls without retaining their payloads, and deny any unexpected permission request.
4. End when the response matching the `session/prompt` request ID returns `stopReason: "end_turn"`. Record other stop reasons or transport failures as interrupted, censored, or failed. Look for provider evidence of the actual model, effort, and tier. ACP's selected options establish requested configuration.

[ACP session setup](https://agentclientprotocol.com/protocol/v1/session-setup) · [ACP configuration](https://agentclientprotocol.com/protocol/v1/session-config-options) · [ACP prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn)

## Antigravity

For a Google-supported direct script or CI workflow, use the installed `agy` with the existing allowed sign-in route. On consumer plans, Google supports direct scripting and CI and excludes wrapping `agy` inside third-party coding agents or applications. Use a standalone user-run shell or CI job for that route and analyze its filtered trace. Check the operator's plan before agent-driven collection. [Antigravity FAQ](https://antigravity.google/docs/faq#can-i-use-antigravity-cli-headless-mode-in-third-party-coding-agents-or-automate-account-switching)

List model slugs with `agy models`. Choose a model slug that encodes the requested effort, when available. With a base slug, use the documented `--effort` value and verify the resolved configuration. Match `--expected-model` to the exact client-reported ID when it differs from the selector. [Antigravity headless mode](https://antigravity.google/docs/cli/headless)

```sh
python3 "$TPS_SKILL_DIR/scripts/capture.py" antigravity --timeout 300 \
  --expected-model "$TPS_MODEL" -- \
  agy --model "$TPS_MODEL" --output-format stream-json -p "$TPS_PROMPT" \
  > antigravity-turn.jsonl
```

In matching `step_update` events, use `step_update.text_delta` only for `step_type: "agent_response"`. Both `ACTIVE` and `DONE` can carry incremental fragments. A short response may arrive entirely in one `DONE`. Validate against the terminal `result.response` without adding it to the deltas. Require `result.status: "SUCCESS"` and one fresh turn. Keep `init.model` as the requested client selection. Record a provider-reported served tier only if the intended route actually exposes it. Treat native thinking counters and checkpoint overhead as separate evidence, and exclude reasoning text, tool output, and raw JSON from saved traces. [Antigravity streaming JSON](https://antigravity.google/docs/cli/headless#streaming-json)

## Direct model APIs

Use the configured endpoint, SDK, and credentials for the intended API test. Suppress SDK auto-retries where the test can control retries. Fix one model, one prompt, one candidate, one output limit, and no tool definitions for the controlled workload. Use provider stop status and workload validation in addition to stream termination. Standard public API protocol mappings follow. Adapt field names only with evidence from the active SDK or gateway.

| Route | Submission, visible text, and terminal evidence |
| --- | --- |
| OpenAI Responses | Start a streamed `responses.create` request with `model`, `input`, `stream: true`, the supported `reasoning.effort`, `max_output_tokens`, and requested `service_tier`. Use `store: false` where supported for the benchmark. Use `response.output_text.delta` for visible text and `response.completed` for completion. Read `response.model`, `response.reasoning.effort` when present, the actual `response.service_tier`, and usage. Keep `usage.output_tokens_details.reasoning_tokens` separate from visible counts. Preserve `response.incomplete`, failure, and error outcomes. [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) |
| Anthropic Messages | Start streamed `messages.create` with `model`, `messages`, `max_tokens`, the selected model's supported thinking and `output_config.effort`, and `service_tier` where supported. Read `content_block_delta` events with `delta.type: "text_delta"` and stop at `message_stop`. Check the stop reason, returned model, and reported `usage.service_tier` from the initial or final usage records. Inference speed is a separate field where exposed. Record the last cumulative `output_tokens` with its documented scope. [Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming) · [Messages API](https://platform.claude.com/docs/en/api/python/messages/create) · [Service tiers](https://platform.claude.com/docs/en/api/service-tiers) |
| Gemini API | Use `streamGenerateContent` with the exact supported model, requested thinking configuration, and service tier when exposed by the route. Select one candidate and include only text parts with no thought marker. Verify the candidate's successful finish reason and stream completion. Read `modelVersion` and final `usageMetadata`, including `candidatesTokenCount`, `thoughtsTokenCount`, and `serviceTier` where reported. Flag model changes within the attempt. [Gemini streaming and response schema](https://ai.google.dev/api/generate-content) |

For a custom capture on one of these routes, implement the event loop below with the route's existing client, the mappings above, and the trace contract.

```python
from time import perf_counter_ns

origin = perf_counter_ns()
write_trace("start", t=0)
write_trace("submit", t=(perf_counter_ns() - origin) / 1e9)
for source_event in open_stream_on_configured_route():
    t = (perf_counter_ns() - origin) / 1e9
    # Allowlist deltas and metadata in memory, and retain the terminal timestamp.
    capture_visible_text_or_outcome(source_event, t)
validate_and_write_filtered_events()
```

Require a clean terminal outcome and a matching workload. For final-only output, use the completion-only calculation in [Trace and metrics](trace-and-metrics.md). If the gateway echoes a requested value without describing actual service, label that value as configuration evidence. Keep API measurements scoped to that endpoint.
