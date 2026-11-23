#!/usr/bin/env python3
"""Calculate visible-text timings and rates from JSONL. Requires tiktoken."""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import accumulate
import json
import math
from pathlib import Path
from typing import Iterable


DEFAULT_ENCODING = "o200k_base"
REQUIRED_FIELDS = {
    "start": {"event", "t"},
    "submit": {"event", "t"},
    "text": {"event", "t", "text"},
    "end": {"event", "t", "status"},
}
END_METADATA = {"configured_effort", "configured_model", "configured_tier", "model", "speed", "tier"}


class MeasurementError(ValueError):
    """The input or tokenizer setup cannot produce a measurement."""


@dataclass
class TextChunk:
    t: float
    text: str
    byte_length: int


@dataclass
class Trace:
    submit: float | None
    chunks: list[TextChunk]
    end: float
    metadata: dict[str, str]


def unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("duplicate JSON key")
    return fields


def parse_record(line: str, line_number: int) -> tuple[dict, str, float]:
    try:
        record = json.loads(line, object_pairs_hook=unique_fields)
    except (ValueError, RecursionError) as error:
        raise MeasurementError(f"line {line_number}: expected one valid JSON object") from error
    if not isinstance(record, dict):
        raise MeasurementError(f"line {line_number}: expected one JSON object")
    kind = record.get("event")
    if not isinstance(kind, str) or kind not in REQUIRED_FIELDS:
        raise MeasurementError(f"line {line_number}: expected a start, submit, text, or end event")
    required = REQUIRED_FIELDS[kind]
    allowed = required
    if kind == "end":
        allowed = required | END_METADATA | {"reason"}
    if not required <= record.keys() <= allowed:
        raise MeasurementError(f"line {line_number}: unexpected or missing fields in {kind} event")

    timestamp = record["t"]
    try:
        valid_time = type(timestamp) in (int, float) and math.isfinite(timestamp) and timestamp >= 0
    except OverflowError:
        valid_time = False
    if not valid_time:
        raise MeasurementError(f"line {line_number}: expected finite nonnegative seconds in t")
    return record, kind, timestamp


def utf8_length(value: str, line_number: int, field: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise MeasurementError(f"line {line_number}: {field} contains invalid Unicode") from error


def read_trace(lines: Iterable[str]) -> Trace:
    previous_time = 0.0
    submit = None
    chunks = []
    end = None
    metadata = {}
    for line_number, line in enumerate(lines, start=1):
        if end is not None:
            raise MeasurementError(f"line {line_number}: expected the end event to be last")
        record, kind, timestamp = parse_record(line, line_number)
        if line_number == 1 and (kind != "start" or timestamp != 0):
            raise MeasurementError("line 1: expected a start event at t=0")
        if timestamp < previous_time:
            raise MeasurementError(f"line {line_number}: timestamps must be nondecreasing")
        previous_time = timestamp
        if kind == "start":
            if line_number != 1:
                raise MeasurementError(f"line {line_number}: start must be the first event")
        elif kind == "submit":
            if line_number != 2:
                raise MeasurementError(f"line {line_number}: submit must follow start")
            submit = timestamp
        elif kind == "text":
            fragment = record["text"]
            if not isinstance(fragment, str):
                raise MeasurementError(f"line {line_number}: expected a string in text")
            if fragment:
                chunks.append(TextChunk(timestamp, fragment, utf8_length(fragment, line_number, "text")))
        else:
            if record["status"] != "completed":
                raise MeasurementError(f"line {line_number}: end status must be completed")
            if "reason" in record:
                raise MeasurementError(f"line {line_number}: completed end cannot include a failure reason")
            for field in sorted(END_METADATA & record.keys()):
                value = record[field]
                if not isinstance(value, str) or not value.strip():
                    raise MeasurementError(f"line {line_number}: expected a nonempty string in {field}")
                utf8_length(value, line_number, field)
                metadata[field] = value
            end = timestamp
    if end is None:
        raise MeasurementError("missing final end event with status completed")
    return Trace(submit, chunks, end, metadata)


def rate(tokens: int, seconds: float) -> float | None:
    if tokens <= 0 or seconds <= 0:
        return None
    result = tokens / seconds
    return result if math.isfinite(result) else None


def middle_rate(token_ends: list[int], batch_ends: list[int], batch_times: list[float]) -> float | None:
    # Use one-based nearest ranks for 10% and 90%. A token is available only
    # when the text batch containing its final UTF-8 byte has arrived.
    first_rank = (len(token_ends) + 9) // 10
    last_rank = (9 * len(token_ends) + 9) // 10
    if first_rank == last_rank:
        return None
    first_batch = bisect_left(batch_ends, token_ends[first_rank - 1])
    last_batch = bisect_left(batch_ends, token_ends[last_rank - 1])
    first_count = bisect_right(token_ends, batch_ends[first_batch])
    last_count = bisect_right(token_ends, batch_ends[last_batch])
    return rate(last_count - first_count, batch_times[last_batch] - batch_times[first_batch])


def measure(trace: Trace, encoding) -> dict:
    batch_times = []
    batch_ends = []
    byte_end = 0
    for chunk in trace.chunks:
        byte_end += chunk.byte_length
        if batch_times and chunk.t == batch_times[-1]:
            batch_ends[-1] = byte_end
        else:
            batch_times.append(chunk.t)
            batch_ends.append(byte_end)

    # Encode the complete output once. Encoding chunks independently would
    # miss tokens formed by merges across a chunk boundary.
    token_ids = encoding.encode_ordinary("".join(chunk.text for chunk in trace.chunks))
    token_ends = list(accumulate(len(encoding.decode_single_token_bytes(token)) for token in token_ids))
    first_batch_tokens = 0
    first_text = None
    decode_tps = None
    if batch_times:
        first_text = batch_times[0]
        first_batch_tokens = bisect_right(token_ends, batch_ends[0])
        decode_tps = rate(len(token_ids) - first_batch_tokens, batch_times[-1] - first_text)

    return {
        "encoding": encoding.name,
        **trace.metadata,
        "output_tokens": len(token_ids),
        "text_chunks": len(trace.chunks),
        "text_batches": len(batch_times),
        "first_batch_tokens": first_batch_tokens,
        "launch_ttft_s": first_text,
        "launch_total_s": trace.end,
        "end_to_end_tps": rate(len(token_ids), trace.end),
        "decode_tps": decode_tps,
        "middle_10_90_tps": middle_rate(token_ends, batch_ends, batch_times),
        "submit_ttft_s": (
            first_text - trace.submit if first_text is not None and trace.submit is not None else None
        ),
        "submit_total_s": trace.end - trace.submit if trace.submit is not None else None,
    }


def load_encoding(name: str):
    try:
        import tiktoken
    except ImportError as error:
        raise MeasurementError(
            "tiktoken is required. Install it with python3 -m pip install tiktoken."
        ) from error
    names = tiktoken.list_encoding_names()
    if name not in names:
        available = ", ".join(sorted(names))
        raise MeasurementError(f"unknown tiktoken encoding {name!r}. Available encodings: {available}")
    try:
        return tiktoken.get_encoding(name)
    except (ImportError, OSError, ValueError) as error:
        raise MeasurementError(
            f"could not load tiktoken encoding {name!r}. Check tokenizer cache and network access."
        ) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "trace", type=Path, metavar="TRACE.jsonl", help="UTF-8 JSONL from a completed request"
    )
    parser.add_argument(
        "--encoding", default=DEFAULT_ENCODING, help="tiktoken encoding (default: %(default)s)"
    )
    args = parser.parse_args(argv)
    try:
        with args.trace.open(encoding="utf-8") as source:
            trace = read_trace(source)
        report = measure(trace, load_encoding(args.encoding))
    except UnicodeDecodeError:
        parser.exit(1, f"{parser.prog}: trace must contain valid UTF-8 JSONL\n")
    except (MeasurementError, OSError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
