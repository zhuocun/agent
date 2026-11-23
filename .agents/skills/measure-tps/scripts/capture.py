#!/usr/bin/env python3
"""Capture one CLI answer as normalized JSONL. Requires Python 3.10+ on POSIX."""

import argparse
import json
import math
import os
import re
import selectors
import signal
import subprocess
import sys
import time


MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_TEXT_EVENTS = 100_000
MODEL_ID = re.compile(
    r"(?:(?:(?:us|eu|apac|global)\.)?anthropic\.)?claude[-.][A-Za-z0-9_.:@-]{1,100}"
    r"|gemini[-.][A-Za-z0-9_.:@-]{1,100}|opus|sonnet|haiku"
)
TIERS = {"auto", "standard", "priority", "default", "flex", "batch", "scale"}
SPEEDS = {"standard", "fast"}
STOP_REASONS = (None, "end_turn", "stop_sequence")


class CaptureFailure(Exception):
    """A failure with a fixed diagnostic that contains no child output."""


def mapping(value):
    if not isinstance(value, dict):
        raise CaptureFailure("invalid_protocol_record")
    return value


def integer(value):
    if type(value) is not int or value < 0:
        raise CaptureFailure("invalid_protocol_record")
    return value


def string(value):
    if not isinstance(value, str):
        raise CaptureFailure("invalid_protocol_record")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(_value):
    raise ValueError("invalid JSON number")


class Capture:
    def __init__(self):
        self.chunks = []
        self.text_size = 0
        self.configured_models = set()
        self.models = set()
        self.metadata = {}
        self.terminal_time = None

    def record_models(self, destination, *values):
        for value in values:
            if value is not None:
                destination.add(string(value))

    def record_text(self, elapsed, value):
        text = string(value)
        if text:
            byte_count = len(text.encode("utf-8"))
            self.text_size += byte_count
            if self.text_size > MAX_RECORD_BYTES or len(self.chunks) >= MAX_TEXT_EVENTS:
                raise CaptureFailure("visible_output_too_large")
            self.chunks.append((elapsed, text))

    def record_usage(self, usage):
        usage = mapping(usage)
        for key, field, known in (("tier", "service_tier", TIERS), ("speed", "speed", SPEEDS)):
            value = usage.get(field)
            if isinstance(value, str) and value in known:
                if key in self.metadata and self.metadata[key] != value:
                    raise CaptureFailure("inconsistent_mode")
                self.metadata[key] = value

    def complete(self, elapsed, response):
        text = "".join(fragment for _, fragment in self.chunks)
        if not text.strip():
            raise CaptureFailure("no_visible_stream")
        if text != string(response):
            raise CaptureFailure("terminal_text_mismatch")
        self.terminal_time = elapsed

    def consume(self, elapsed, event):
        if self.terminal_time is not None:
            raise CaptureFailure("event_after_result")
        self.handle(elapsed, mapping(event))

    def verify(self, expected_model):
        if self.terminal_time is None:
            raise CaptureFailure("missing_result")
        if len(self.models) > 1 or len(self.configured_models) > 1:
            raise CaptureFailure("inconsistent_model")
        model = next(iter(self.models), None)
        configured = next(iter(self.configured_models), None)
        if expected_model is not None and expected_model != (model or configured):
            raise CaptureFailure("expected_model_unverified")

        # Only release identifier-shaped provider metadata from known fields.
        for key, value in (("model", model), ("configured_model", configured)):
            if value and MODEL_ID.fullmatch(value):
                self.metadata[key] = value


class ClaudeCapture(Capture):
    def __init__(self):
        super().__init__()
        self.initialized = False
        self.message_id = None
        self.message_stopped = False
        self.stop_reason = None
        self.block_kind = None
        self.block_index = -1
        self.snapshots = []
        self.snapshot_size = 0

    def handle(self, elapsed, event):
        kind = event.get("type")
        if event.get("parent_tool_use_id") is not None or kind == "user":
            raise CaptureFailure("unexpected_tool_or_turn")
        if kind == "system" and event.get("subtype") == "init":
            if self.initialized:
                raise CaptureFailure("unexpected_tool_or_turn")
            self.initialized = True
            self.record_models(self.configured_models, event.get("model"))
            if event.get("tools"):
                raise CaptureFailure("tools_enabled")
        elif kind == "system" and event.get("subtype") in ("status", "ui_invalidate"):
            return
        elif kind == "rate_limit_event":
            return
        elif kind == "stream_event":
            self.handle_stream(elapsed, mapping(event.get("event")))
        elif kind == "assistant":
            if event.get("error"):
                raise CaptureFailure("unsuccessful_turn")
            self.handle_snapshot(mapping(event.get("message")))
        elif kind == "result":
            self.handle_result(elapsed, event)
        else:
            raise CaptureFailure("unexpected_protocol_event")

    def handle_stream(self, elapsed, event):
        kind = event.get("type")
        if kind == "message_start":
            message = mapping(event.get("message"))
            if self.message_id is not None or message.get("role") != "assistant":
                raise CaptureFailure("unexpected_tool_or_turn")
            self.message_id = string(message.get("id"))
            if not self.message_id or message.get("content"):
                raise CaptureFailure("invalid_protocol_record")
            self.record_models(self.models, message.get("model"))
            self.record_usage(message.get("usage", {}))
            return
        if self.message_id is None or self.message_stopped:
            raise CaptureFailure("incomplete_stream")
        if self.stop_reason is not None and kind not in ("message_delta", "message_stop"):
            raise CaptureFailure("incomplete_stream")
        if kind == "content_block_start":
            if self.block_kind is not None or integer(event.get("index")) != self.block_index + 1:
                raise CaptureFailure("incomplete_stream")
            block = mapping(event.get("content_block"))
            self.block_kind = block.get("type")
            self.block_index += 1
            if self.block_kind == "text":
                if string(block.get("text", "")):
                    raise CaptureFailure("nonincremental_text_start")
            elif self.block_kind not in ("thinking", "redacted_thinking"):
                raise CaptureFailure("unexpected_tool_or_turn")
        elif kind in ("content_block_delta", "content_block_stop"):
            if self.block_kind is None or integer(event.get("index")) != self.block_index:
                raise CaptureFailure("incomplete_stream")
            if kind == "content_block_stop":
                self.block_kind = None
                return
            delta = mapping(event.get("delta"))
            if self.block_kind == "text" and delta.get("type") == "text_delta":
                self.record_text(elapsed, delta.get("text"))
            elif self.block_kind != "thinking" or delta.get("type") not in (
                "thinking_delta", "signature_delta",
            ):
                raise CaptureFailure("unexpected_block_delta")
        elif kind == "message_delta":
            delta = mapping(event.get("delta"))
            stop_reason = delta.get("stop_reason")
            if self.block_kind is not None or stop_reason not in STOP_REASONS:
                raise CaptureFailure("unsuccessful_turn")
            if stop_reason is not None:
                if self.stop_reason is not None and self.stop_reason != stop_reason:
                    raise CaptureFailure("stop_reason_mismatch")
                self.stop_reason = stop_reason
            self.record_usage(event.get("usage", {}))
        elif kind == "message_stop" and self.block_kind is None:
            if self.stop_reason is None:
                raise CaptureFailure("incomplete_stream")
            self.message_stopped = True
        else:
            raise CaptureFailure("unexpected_protocol_event")

    def handle_snapshot(self, message):
        if (self.message_id is None or message.get("id") != self.message_id
                or message.get("role") != "assistant"):
            raise CaptureFailure("unexpected_tool_or_turn")
        if message.get("stop_reason") not in STOP_REASONS:
            raise CaptureFailure("unsuccessful_turn")
        self.record_models(self.models, message.get("model"))
        self.record_usage(message.get("usage", {}))
        blocks = message.get("content")
        if not isinstance(blocks, list):
            raise CaptureFailure("invalid_protocol_record")
        for block in blocks:
            block = mapping(block)
            kind = block.get("type")
            if kind == "text":
                text = string(block.get("text"))
                if text:
                    self.snapshot_size += len(text.encode("utf-8"))
                    if self.snapshot_size > MAX_RECORD_BYTES or len(self.snapshots) >= MAX_TEXT_EVENTS:
                        raise CaptureFailure("visible_output_too_large")
                    self.snapshots.append(text)
            elif kind not in ("thinking", "redacted_thinking"):
                raise CaptureFailure("unexpected_tool_or_turn")

    def handle_result(self, elapsed, event):
        if event.get("subtype") != "success" or event.get("is_error") is not False:
            raise CaptureFailure("unsuccessful_turn")
        if event.get("stop_reason") not in STOP_REASONS or integer(event.get("num_turns")) != 1:
            raise CaptureFailure("unsuccessful_turn")
        if not self.initialized or not self.message_stopped:
            raise CaptureFailure("incomplete_stream")
        if event.get("stop_reason") not in (None, self.stop_reason):
            raise CaptureFailure("stop_reason_mismatch")
        self.record_models(self.models, event.get("model"), *mapping(event.get("modelUsage", {})))
        self.record_usage(event.get("usage", {}))
        response = string(event.get("result"))
        if self.snapshots and "".join(self.snapshots) != response:
            raise CaptureFailure("terminal_text_mismatch")
        self.complete(elapsed, response)


class AntigravityCapture(Capture):
    def __init__(self):
        super().__init__()
        self.initialized = False
        self.conversation_id = None
        self.user_step = None
        self.response_step = None
        self.response_done = False

    def handle(self, elapsed, event):
        kind = event.get("event") or event.get("type")
        if kind not in ("init", "step_update", "result"):
            raise CaptureFailure("unexpected_protocol_event")
        payload = mapping(event.get(kind, event))
        if any(payload.get(field) for field in ("tool_calls", "tool_name", "tool_info", "subagent_info")):
            raise CaptureFailure("unexpected_tool_or_turn")
        for value in (event.get("conversation_id"), payload.get("conversation_id")):
            if value is not None:
                conversation_id = string(value)
                if self.conversation_id is not None and conversation_id != self.conversation_id:
                    raise CaptureFailure("unexpected_tool_or_turn")
                self.conversation_id = conversation_id
        if kind == "init":
            if self.initialized:
                raise CaptureFailure("unexpected_tool_or_turn")
            self.initialized = True
            self.record_models(self.configured_models, payload.get("model"), payload.get("model_id"))
        elif not self.initialized:
            raise CaptureFailure("incomplete_stream")
        elif kind == "step_update":
            self.handle_step(elapsed, payload)
        else:
            if (payload.get("status") != "SUCCESS" or integer(payload.get("num_turns")) != 1
                    or payload.get("error")):
                raise CaptureFailure("unsuccessful_turn")
            if not self.response_done:
                raise CaptureFailure("incomplete_stream")
            self.record_models(self.models, payload.get("model"), payload.get("model_id"))
            self.record_usage(payload.get("usage", {}))
            self.complete(elapsed, payload.get("response"))

    def handle_step(self, elapsed, payload):
        step = payload.get("step_type")
        if step in ("user_input", "user_message"):
            index = integer(payload.get("step_index"))
            if self.response_step is not None or (self.user_step is not None and self.user_step != index):
                raise CaptureFailure("unexpected_tool_or_turn")
            self.user_step = index
            return
        if step in ("thinking", "system", "agent_thinking", "checkpoint"):
            return
        if step != "agent_response":
            raise CaptureFailure("unexpected_tool_or_turn")
        index = integer(payload.get("step_index"))
        state = payload.get("state")
        if self.response_done or (self.response_step is not None and self.response_step != index):
            raise CaptureFailure("unexpected_tool_or_turn")
        if self.user_step is not None and index <= self.user_step:
            raise CaptureFailure("unexpected_tool_or_turn")
        if state not in ("ACTIVE", "DONE"):
            raise CaptureFailure("incomplete_stream")
        self.response_step = index
        self.response_done = state == "DONE"
        self.record_models(self.models, payload.get("model"), payload.get("model_id"))
        self.record_usage(payload.get("usage", {}))
        if "text_delta" in payload:
            self.record_text(elapsed, payload["text_delta"])


def pipe_records(pipe, deadline):
    pending = bytearray()
    last_read = 0.0
    with selectors.DefaultSelector() as selector:
        selector.register(pipe, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CaptureFailure("timeout")
            if not selector.select(min(remaining, 60)):
                continue
            chunk = os.read(pipe.fileno(), 64 * 1024)
            received = time.monotonic()
            if received > deadline:
                raise CaptureFailure("timeout")
            if not chunk:
                if pending:
                    yield last_read, pending
                return
            last_read = received
            lines = chunk.split(b"\n")
            for line in lines[:-1]:
                pending.extend(line)
                if len(pending) > MAX_RECORD_BYTES:
                    raise CaptureFailure("protocol_record_too_large")
                yield received, pending
                pending.clear()
            pending.extend(lines[-1])
            if len(pending) > MAX_RECORD_BYTES:
                raise CaptureFailure("protocol_record_too_large")


def run(capture, command, started, timeout, expected_model):
    deadline = started + timeout
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except (OSError, ValueError):
        raise CaptureFailure("launch_failed") from None
    try:
        with process.stdout as pipe:
            for received, line in pipe_records(pipe, deadline):
                if not line.strip():
                    continue
                try:
                    event = json.loads(
                        line.decode("utf-8"),
                        object_pairs_hook=unique_object,
                        parse_constant=invalid_constant,
                    )
                    capture.consume(received - started, event)
                except (ValueError, RecursionError):
                    raise CaptureFailure("invalid_jsonl") from None
        if process.wait(timeout=max(0.0, deadline - time.monotonic())) != 0:
            raise CaptureFailure("child_exit_nonzero")
        capture.verify(expected_model)
    finally:
        # The wrapper can leave children in its group even after it exits.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        self.print_usage(sys.stderr)
        self.exit(2, "capture.py: use a supported client, valid options, and -- followed by the approved argv\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = ArgumentParser(
        description=__doc__, allow_abbrev=False,
        usage="%(prog)s {claude,antigravity} [--timeout SECONDS] [--expected-model ID] -- COMMAND [ARG ...]",
    )
    parser.add_argument("client", choices=("claude", "antigravity"))
    parser.add_argument("--timeout", type=float, default=300, help="positive timeout in seconds (default: 300)")
    parser.add_argument("--expected-model", help="exact model ID from the stream or client init")
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command or not math.isfinite(args.timeout) or args.timeout <= 0 or args.expected_model == "":
        parser.error("invalid arguments")

    def emit(event, elapsed, **fields):
        print(json.dumps({"event": event, "t": elapsed, **fields}), flush=True)

    def interrupted(_signum, _frame):
        raise CaptureFailure("interrupted")

    capture = ClaudeCapture() if args.client == "claude" else AntigravityCapture()
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        emit("start", 0)
        started = time.monotonic()
        try:
            run(capture, command, started, args.timeout, args.expected_model)
        except (CaptureFailure, subprocess.TimeoutExpired, KeyboardInterrupt, OSError) as failure:
            if isinstance(failure, subprocess.TimeoutExpired):
                reason = "timeout"
            elif isinstance(failure, KeyboardInterrupt):
                reason = "interrupted"
            elif isinstance(failure, OSError):
                reason = "capture_io_failed"
            else:
                reason = str(failure)
            emit("end", time.monotonic() - started, status="failed", reason=reason)
            return 1

        for elapsed, fragment in capture.chunks:
            emit("text", elapsed, text=fragment)
        emit("end", capture.terminal_time, status="completed", **capture.metadata)
        return 0
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
