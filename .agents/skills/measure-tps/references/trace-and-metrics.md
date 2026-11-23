# Trace and metrics

## Filtered trace

Use one UTF-8 JSONL file per attempt. All `t` values are monotonic elapsed seconds from the same `start` clock, such as Python's `time.perf_counter_ns()`. Timestamp a received line or parsed event as soon as the reader retrieves it, before filtering, formatting, printing, or writing to disk. Hold received text in memory when final validation requires matching fragments to a reply or checking for tool activity. Preserve the original timestamps if the trace is written after validation.

| Event | Boundary and payload |
| --- | --- |
| `start` | `t: 0` immediately before agent launch or another named measurement boundary. |
| `submit` | Optional second record, immediately after `start`. Mark the moment immediately before sending the prompt or opening the streaming request when independently observable. Omit for a process launched with the prompt as an argument. |
| `text` | Incremental visible assistant text in `text`, with the observation time in `t`. Keep nonempty fragments verbatim, including spaces and newlines. |
| `end` | Final record. Use `status: "completed"` at the timestamp of confirmed success. The six permitted optional fields are `model`, `configured_model`, `configured_effort`, `configured_tier`, provider-reported `tier`, and `speed`. Give each supplied field a nonempty string. |

`scripts/measure.py` rejects failed, interrupted, and censored inputs. Keep those records with their observed elapsed times and reasons for the report. Keep raw provider counters outside the calculator's trace.

The following synthetic trace illustrates the data contract.

```jsonl
{"event":"start","t":0}
{"event":"submit","t":0.12}
{"event":"text","t":1.12,"text":"Measure the first"}
{"event":"text","t":1.62,"text":" visible reply and the rest of the stream."}
{"event":"end","t":1.66,"status":"completed"}
```

Use an in-memory parser for native JSONL or a proper server-sent events (SSE) parser for HTTP streams. Never use file modification time, a UI animation, or a later copy of a transcript as a token-arrival clock. An adapter may use source-provided timestamps only when the clock, boundary, scope, resolution, and order are established. Use matching event IDs to keep a turn and its messages together. For cumulative snapshots, emit only the newly appended suffix with that snapshot's timestamp if the prefix is unchanged. For revisions, replayed text, or unresolved duplicate delivery, mark incremental TPS unavailable unless the adapter can reconstruct original deltas from documented semantics.

For completion-only output, keep the elapsed times and final text outside the incremental trace. Tokenize that final visible answer with the same encoding and divide its token count by the elapsed time to confirmed turn completion. Label the answer's timestamp final receipt and leave TTFT and streaming TPS unavailable. A genuine stream with a single first-and-only text payload supports first-text receipt timing. Completed snapshots following true deltas can validate the aggregate text. Exclude them from the delta sequence.

## Time and token boundaries

Use `t_start` for the launch boundary, `t_submit` for a separately observed submission, `t_first` and `t_last` for first and last nonempty visible text receipt, and `t_end` for confirmed completion. Report the applicable measures below.

- **First-text latency**, `t_first - t_start`, or `t_first - t_submit` when reporting from submission. It includes any queueing, network, prefill, hidden reasoning, and buffering before visible delivery. A provider's first generated token or the first reasoning event can precede it.
- **Turn latency**, `t_end - t_start`, with `t_end - t_submit` also reported when measurable. Terminal events can arrive after visible text and may include client housekeeping. Record the output observation boundary and avoid mixing process exit, terminal event, and final text across conditions.
- **Visible end-to-end TPS**, `N / (t_end - t_start)` in the calculator, for a valid completed turn with visible tokens and a positive interval. Empty visible output yields `null` for this rate. A separately labeled submit-to-completion rate uses `t_end - t_submit`. `N` is the token count of the joined visible text.
- **Visible streaming TPS**, `(N - C_first) / (t_last - t_first)`, for valid completed turns with positive duration and positive `N - C_first`. The calculator reports it as `decode_tps`. It groups equal-time fragments into a batch and assigns each token from the full text to the batch carrying its last UTF-8 byte. `C_first` counts tokens complete by the end of the first batch. This is a delivery estimate. Use the same attribution for every condition and note heavy batching.
- **Middle 10–90% visible TPS** uses the first batches reaching the ranks `ceil(0.10 × N)` and `ceil(0.90 × N)`. Divide the actual difference in cumulative token totals at those batch ends by their receipt time difference. If both ranks land in one batch, the rate is unavailable.

Tokenize the reconstructed text as one string. Chunk boundaries can break token merges. Pin the tokenizer name and version, and use the same encoding for every normalized comparison. If `tiktoken` is absent, install it in an isolated Python environment and run the calculator with that interpreter. Its first use may need network access to retrieve the public vocabulary. The text stays local. If the tokenizer is unavailable, retain the measured elapsed metrics and compute visible characters per second separately with explicit units, or use verified provider counts with a matching scope. Never present characters, words, or an undocumented heuristic as tokens.

Native counters can include reasoning, formatting, tool calls, retries, subagents, or multiple model requests. Record the raw fields, their scope, and any cache hits as counts alongside the normalized visible text. Sum per-request deltas only where the producer defines deltas. For cumulative counters, retain the final value for that scope. For native visible streaming TPS, the numerator must describe visible tokens after the first payload with evidence for that split. Without that attribution, use the normalized streaming measurement. Keep native total output per response second labeled as such. For a thinking TPS measurement, require matching reasoning-generation start and end timestamps along with a compatible counter supplied by the provider or engine. Client progress banners and launch-to-first-text latency combine other work and cannot supply this interval.

NVIDIA AIPerf defines per-user output throughput as the inverse of inter-token latency and distinguishes it from aggregate throughput. Its usual calculation excludes one token from the numerator and can account for multiple tokens in the first chunk when compatible provider counters supply that split. Use these definitions as references for metric boundaries. AIPerf may use different eligibility, token scope, or terminal handling than a visible-answer capture. [NVIDIA AIPerf metrics reference](https://docs.nvidia.com/aiperf/reference/ai-perf-metrics-reference)

## Keep comparable evidence

For each attempt, keep its condition and order, time window and location, client version, observation boundary, configuration and response evidence, workload ID, output count, warm-up or cache observation, outcome, and file reference. Keep trigger-to-submit separate from submit-to-first-text when both are available. If the provider has multiple cache layers, use any available cache-hit counters and say which layer was observed. Distinguish an observed first launch or first connection from an assumed cold cache.

Classify timeouts as right-censored at their elapsed time. Also record cancellation, rate limit, non-streaming, model or tier mismatch, tool activity, and incomplete output when present. Non-streaming can still qualify for end-to-end latency and rate. A refusal or a token-cap stop can be a real protocol terminal event without meeting the controlled workload. Preserve duration and valid partial counters for failed attempts where available. Completed and comparable attempts supply the ordinary TPS summaries. Do not drop an otherwise valid slow attempt. A tier mismatch may remain valid for a comparison of requested routing policies if that was the stated question. A claimed served-tier comparison requires observed matching tiers.

Choose one primary metric before comparing. Record `Q1` and `Q3` as the IQR endpoints and name the quantile convention for small samples. A reproducible convention is linear interpolation at sorted zero-based index `(n - 1) × p`, where `p` is 0.25 or 0.75. For ratios, apply this rule to the observed pair ratios. Never divide separate condition medians and call that the median paired ratio. A single pair has a ratio but no meaningful spread.
