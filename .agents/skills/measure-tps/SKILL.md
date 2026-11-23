---
name: measure-tps
description: >-
  Measure LLM output tokens per second (TPS), time to first token, visible
  streaming speed, and turn latency on Codex, Claude Code, Devin, Antigravity,
  or a model API. Use when the user asks for a live TPS test, a one-turn speed
  check, a model or service-tier comparison, or analysis of a timed stream.
  Do not use for general model selection, quality evaluation, or load tests.
---

# Measure tokens per second

Measure the user's actual model, client, and route. Run the benchmark when the route and spend are already authorized, or calculate from a supplied trace. For a one-turn request, complete one measured turn and report it as a sample.

Prioritize route and configuration fidelity, then timing and counting validity, then sample size.

## Standing rules

- Preserve the configured provider, endpoint, account, authentication, and billing route. Pin the requested model, reasoning effort, and tier through the client's supported controls for the run. Treat a moving alias, automatic router, or unverified fallback as such. If the requested condition is unavailable, report it before substituting any route or condition.
- Record the exact requested and observed model IDs, requested effort and any effective-effort evidence, requested tier, and actual served tier when the provider attests it. Label a client's resolved setting as configuration evidence. Use `unavailable` for missing evidence and `not applicable` for unsupported controls. A settings flag, speed label, normal-looking response, or latency reading cannot verify the served tier. Report the health of the route and the evidence for any fallback.
- Use a synthetic prompt. Allowlist visible assistant text and safe metadata before writing artifacts. Leave account identifiers, credentials, authorization headers, raw request dumps, reasoning text, and reasoning summaries out of benchmark artifacts. Use the client's no-persistence option when available. When the user requires no client retention, use a capture that meets that requirement or report the route's retention limit.
- Use a single monotonic clock at the observation boundary. Timestamp actual incrementally received text. Keep completed messages, snapshots, terminal counters, and chunk durations from replacing the arrival times. Report rates as client-observed. Use engine decode TPS only with provider-side token counts and generation timestamps from the same interval. Hidden reasoning counts without independent matching generation times yield a count with TPS unavailable.
- Read [Client capture](references/client-capture.md) in full when collecting from a CLI or API, and read it again after compaction. Read [Trace and metrics](references/trace-and-metrics.md) in full when capturing, calculating, or interpreting results, and read it again after compaction.

## 1. Design the run

1. Define the factor under comparison. For a tier comparison, keep the model, effort, route, client version, work directory, permissions, hooks, system instructions, and request options fixed where possible. Give each attempt fresh conversation history. Keep concurrency at one unless the user requests a different load.
2. Send the exact same synthetic text-only prompt to each condition. Use the same output limit where supported and record any different limits. Use a clean scratch project and remove optional tools where the client supports that without changing the route. Disallow tools and delegation in the prompt. Check the output against the task and record tool activity as a workload mismatch.
3. For a comparison within budget, warm each condition once outside the measured set unless the test targets first use. Plan six adjacent A/B pairs when affordable. For each successive two-pair block, shuffle one AB and one BA with a recorded seed. Continue in that order through the planned count and record any early stop. With a smaller budget, use the same rule for the available pairs and report the limited sample. Keep first-use and warmed results separate. A new session alone gives no evidence of a cold host, connection, or provider cache.
4. Fix an attempt timeout, an output validity check, and an exclusion rule before collection. Record every attempt, including failing, truncated, and mismatched runs. Keep retries visible and allow only a bounded retry within budget. Repeat the whole pair under the predetermined retry rule and retain both records. Report successful-run distributions with their denominators and report errors separately.

When the user asks to repeat a previous test, reuse its exact prompt and measurement boundary if available. The following prompt is suitable for a fresh test when the user has no workload in mind.

> Write a checklist for a teammate moving a small static documentation website between hosting providers. Give exactly 32 numbered items in order. Each item must be one actionable sentence of 18 to 24 words. Cover preparation, redirects, DNS, TLS, deployment, validation, and rollback. Finish with a separate line containing only END. Respond directly in English. Use no tools, files, links, headings, or code blocks.

Check for items 1 through 32 and the final `END`. Record deviations in length or format. Set the output allowance high enough for the requested text and the model's internal reasoning before the run. Keep the prompt and validity criterion unchanged across conditions.

## 2. Capture and calculate

Run the appropriate collector in [Client capture](references/client-capture.md). Pass one filtered JSONL trace per calculator invocation.

```sh
python3 scripts/measure.py TRACE.jsonl
```

Run from this skill directory or use the absolute script path. Use the same pinned tokenizer for all normalized comparisons. The calculator requires `tiktoken` and defaults to `o200k_base`, with a different encoding selectable through `--encoding`. Its end-to-end TPS uses turn time from launch. Save native counts separately, with their exact scope. Report both if they answer different questions about the run.

A text event must contain genuinely streamed visible text. For completion-only output, measure turn latency and count the final visible answer separately. A genuine stream with one text batch permits first-text receipt and end-to-end measurements but leaves visible streaming TPS unavailable. Use first-text latency as the client-observed TTFT proxy and state whether it starts at launch or submission.

## 3. Report

Give the sample result or comparison first. Include visible streaming TPS, visible end-to-end TPS, first-text latency, and turn latency where the trace supports them. Include the middle 10–90% visible rate if it helps characterize a long, well-streamed reply. Give sample counts, visible token count, and the clock and tokenizer basis beside the rates. Use `unavailable` with the concrete reason for unobserved metrics. Record launch-to-finish and submit-to-finish separately when both were measured.

For a paired comparison, summarize each condition with the median and interquartile range (IQR). Report the median and IQR of the **within-pair ratios** for the primary metric, with the ratio's direction, valid pair count, and total attempt count. For example, `B/A` above one favors B for throughput, while `A/B` above one favors B for latency. Compute each ratio only from a complete comparable pair with positive metrics. For one sample, report the observation without a spread. Include per-attempt rows when the sample is small or when evidence differs across attempts.

Include the client version and route, requested and observed settings with their evidence, the workload and warm/cold condition, tool or retry activity, and any reasons that limit the comparison. Link the filtered traces or the measurement record when saved. Report the observed route's result rather than a general speed claim about a model family.

## Self-check

- [ ] The actual route, model, effort, and tier match the requested condition wherever evidence permits, with unknowns and fallbacks reported.
- [ ] The trace uses real monotonic arrival times and only approved visible text and safe metadata.
- [ ] Each count describes the named text or provider counter, and each elapsed interval uses the stated endpoints.
- [ ] The report includes failures, censoring, order, warm-up, validity checks, and sample sizes when applicable.
- [ ] Every rate and comparison follows from the collected measurements.
