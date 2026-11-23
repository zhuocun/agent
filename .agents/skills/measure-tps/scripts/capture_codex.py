#!/usr/bin/env python3
"""Capture one Codex app-server turn as filtered JSONL. Requires Python 3.10+."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import signal
import subprocess
from tempfile import TemporaryDirectory
from threading import TIMEOUT_MAX, Thread
from time import perf_counter_ns


TURN_ID = 3
INTERRUPT_ID = 4
RPC_METHODS = {1: "initialize", 2: "thread/start", TURN_ID: "turn/start", INTERRUPT_ID: "turn/interrupt"}
TURN_EVENTS = {
    "turn/started", "turn/completed", "item/started", "item/completed",
    "item/agentMessage/delta", "thread/tokenUsage/updated", "model/rerouted", "error",
}
USAGE_FIELDS = (
    "inputTokens", "cachedInputTokens", "cacheWriteInputTokens", "outputTokens",
    "reasoningOutputTokens", "totalTokens",
)


class CaptureError(Exception):
    def __init__(self, reason: str, status: str = "failed", observed: int | None = None):
        super().__init__(reason)
        self.status = status
        self.observed = observed


def object_field(value: dict, field: str) -> dict:
    result = value.get(field)
    if not isinstance(result, dict):
        raise CaptureError(f"app-server message is missing a valid {field} object")
    return result


def string_field(value: dict, field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise CaptureError(f"app-server message is missing a valid {field} string")
    return result


class AppServer:
    def __init__(self, executable: str, cwd: Path, timeout: float):
        self.incoming: Queue = Queue()
        self.writer = None
        self.active_turn = None
        self.started = perf_counter_ns()
        self.deadline = self.started + int(timeout * 1_000_000_000)
        try:
            self.process = subprocess.Popen(
                [executable, "app-server", "--stdio"], cwd=cwd, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=os.name == "posix",
            )
        except OSError:
            raise CaptureError("could not launch the configured Codex executable") from None
        self.reader = Thread(target=self.read_stdout, daemon=True)
        self.reader.start()

    def read_stdout(self):
        try:
            with self.process.stdout as source:
                for line in source:
                    self.incoming.put((perf_counter_ns(), line))
        except OSError:
            pass
        finally:
            self.incoming.put((perf_counter_ns(), b""))

    def wait(self, queue: Queue, deadline: int):
        # The reader may have received a result on time while the consumer was busy.
        try:
            return queue.get_nowait()
        except Empty:
            pass
        seconds_left = (deadline - perf_counter_ns()) / 1_000_000_000
        if seconds_left > 0:
            try:
                return queue.get(timeout=seconds_left)
            except Empty:
                pass
        raise CaptureError("app-server did not complete within the attempt timeout", "timed_out", deadline)

    def send(self, method: str, params: dict, identifier: int | None = None, *, deadline: int | None = None) -> int:
        deadline = self.deadline if deadline is None else deadline
        message = {"method": method, "params": params}
        if identifier is not None:
            message["id"] = identifier
        payload = (json.dumps(message) + "\n").encode("utf-8")
        sent: Queue = Queue()

        def write():
            timestamp = perf_counter_ns()
            if timestamp < deadline:
                try:
                    self.process.stdin.write(payload)
                    self.process.stdin.flush()
                except (OSError, ValueError):
                    timestamp = None
            sent.put(timestamp)

        # A wrapper can stop reading stdin. Keep that case inside the deadline, too.
        self.writer = Thread(target=write, daemon=True)
        self.writer.start()
        timestamp = self.wait(sent, deadline)
        if timestamp is None:
            raise CaptureError("app-server closed stdin before accepting a request")
        if timestamp >= deadline:
            raise CaptureError("app-server did not send the request within the attempt timeout",
                               "timed_out", deadline)
        return timestamp

    def receive(self, deadline: int | None = None) -> tuple[int, dict]:
        deadline = self.deadline if deadline is None else deadline
        timestamp, line = self.wait(self.incoming, deadline)
        if timestamp > deadline:
            raise CaptureError("app-server did not complete within the attempt timeout", "timed_out", deadline)
        if not line:
            raise CaptureError("app-server closed stdout before the turn completed", observed=timestamp)
        try:
            message = json.loads(line.decode("utf-8"))
        except (ValueError, RecursionError):
            raise CaptureError("app-server stdout must contain only JSONL protocol messages") from None
        if not isinstance(message, dict) or not line.endswith(b"\n"):
            raise CaptureError("app-server stdout must contain only JSONL protocol messages")
        if "method" in message:
            string_field(message, "method")
            if "id" in message:
                raise CaptureError("app-server issued an unexpected request to the capture client")
        return timestamp, message

    def response(self, identifier: int, pending: list | None = None, *, deadline: int | None = None) -> dict:
        while True:
            timestamp, message = self.receive(deadline)
            if "method" in message:
                if pending is not None and message["method"] in TURN_EVENTS:
                    pending.append((timestamp, message))
                continue
            if type(message.get("id")) is not int or message["id"] != identifier:
                raise CaptureError("app-server sent an unexpected response ID")
            if "error" in message:
                stage = RPC_METHODS[identifier]
                raise CaptureError(f"app-server rejected {stage}; check the configured Codex route and arguments")
            return object_field(message, "result")

    def interrupt(self) -> bool:
        if self.writer is not None and self.writer.is_alive():
            return False
        thread_id, turn_id = self.active_turn
        deadline = perf_counter_ns() + 250_000_000
        try:
            self.send("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, INTERRUPT_ID,
                      deadline=deadline)
        except CaptureError:
            return False
        try:
            self.response(INTERRUPT_ID, deadline=deadline)
        except CaptureError:
            pass
        return True

    def close(self):
        process = self.process
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            elif process.poll() is None:
                process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            # A process in an uninterruptible kernel operation may survive a kill.
            pass
        self.reader.join(timeout=0.1)
        if self.writer is not None:
            self.writer.join(timeout=0.1)
        if self.writer is None or not self.writer.is_alive():
            try:
                process.stdin.close()
            except OSError:
                pass


def start_thread(server: AppServer, cwd: Path, evidence: dict) -> str:
    server.send("initialize", {
        "clientInfo": {"name": "measure_tps", "version": "1.0"},
        "capabilities": {"experimentalApi": True},
    }, 1)
    server.response(1)
    server.send("initialized", {})
    server.send("thread/start", {
        "cwd": str(cwd), "ephemeral": True, "approvalPolicy": "never", "sandbox": "read-only",
        "model": evidence["requested_model"], "serviceTier": evidence["requested_tier"],
        "allowProviderModelFallback": False, "dynamicTools": [],
        "config": {"model_reasoning_effort": evidence["requested_effort"], "web_search": "disabled"},
        "baseInstructions": "Generate only the requested benchmark text. Never use tools or delegate.",
        "developerInstructions": "Return only the requested text. Use no tools or files.",
    }, 2)
    result = server.response(2)
    thread = object_field(result, "thread")
    version = thread.get("cliVersion")
    if isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.+-]{0,40}", version):
        evidence["client_version"] = version
    provider = result.get("modelProvider")
    if isinstance(provider, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", provider):
        evidence["configured_provider"] = provider

    mismatches = []
    for control, field in (("model", "model"), ("effort", "reasoningEffort"), ("tier", "serviceTier")):
        if result.get(field) == evidence[f"requested_{control}"]:
            evidence[f"configured_{control}"] = evidence[f"requested_{control}"]
        else:
            mismatches.append(control)
    if mismatches:
        raise CaptureError(f"app-server did not confirm the requested {', '.join(mismatches)} in thread/start")
    sandbox = object_field(result, "sandbox")
    if sandbox.get("type") != "readOnly" or sandbox.get("networkAccess", False) is not False:
        raise CaptureError("app-server did not confirm the read-only sandbox without network access")
    if result.get("approvalPolicy") != "never" or result.get("cwd") != str(cwd):
        raise CaptureError("app-server did not confirm the scratch workspace and no-approval policy")
    if thread.get("ephemeral") is not True or thread.get("turns") != []:
        raise CaptureError("app-server did not confirm a fresh ephemeral thread")
    return string_field(thread, "id")


class Reply:
    """Validate one uninterrupted answer against its completed content."""

    def __init__(self):
        self.item_id = None
        self.chunks: list[tuple[int, str]] = []
        self.complete_text = None

    def check_id(self, item_id: str):
        if self.item_id is None:
            self.item_id = item_id
        elif self.item_id != item_id:
            raise CaptureError("the benchmark turn returned more than one assistant message")

    def add_delta(self, timestamp: int, params: dict):
        delta = params.get("delta")
        if not isinstance(delta, str):
            raise CaptureError("app-server returned an invalid assistant text delta")
        self.check_id(string_field(params, "itemId"))
        if self.complete_text is not None:
            raise CaptureError("app-server sent a delta after the assistant message completed")
        try:
            delta.encode("utf-8")
        except UnicodeEncodeError:
            raise CaptureError("app-server returned an invalid Unicode assistant text delta") from None
        if delta:
            self.chunks.append((timestamp, delta))

    def check_item(self, item: dict, complete: bool):
        kind = item.get("type")
        if kind in ("userMessage", "reasoning"):
            return
        if kind != "agentMessage":
            raise CaptureError("app-server reported tool activity or another non-answer item")
        if item.get("phase") not in (None, "final_answer") or item.get("delivery") or item.get("questions"):
            raise CaptureError("app-server reported commentary, an interim answer, or a question")
        self.check_id(string_field(item, "id"))
        if complete:
            result = item.get("text")
            if not isinstance(result, str):
                raise CaptureError("app-server returned an invalid completed assistant message")
            if self.complete_text is not None and self.complete_text != result:
                raise CaptureError("app-server returned conflicting completed assistant messages")
            self.complete_text = result

    def finish(self, terminal_turn: dict, suffix: str | None):
        if terminal_turn.get("status") == "interrupted":
            raise CaptureError("app-server reported an interrupted turn", "interrupted")
        if terminal_turn.get("status") != "completed" or terminal_turn.get("error") is not None:
            raise CaptureError("app-server reported an unsuccessful turn")
        items = terminal_turn.get("items")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise CaptureError("app-server returned invalid items in the completed turn")
        for item in items:
            self.check_item(item, complete=True)
        streamed = "".join(text for _, text in self.chunks)
        if not streamed.strip() or streamed != self.complete_text:
            raise CaptureError("streamed assistant text is missing or differs from the completed reply")
        if suffix is not None and not streamed.rstrip().endswith(suffix):
            raise CaptureError("the completed reply is missing the expected output suffix")


def capture_turn(server: AppServer, thread_id: str, prompt: str, suffix: str | None, evidence: dict,
                 trace: list) -> int:
    submitted = server.send("turn/start", {
        "threadId": thread_id, "model": evidence["requested_model"], "effort": evidence["requested_effort"],
        "serviceTier": evidence["requested_tier"], "input": [{"type": "text", "text": prompt}],
    }, TURN_ID)
    trace.append({"event": "submit", "t": elapsed(server.started, submitted)})
    pending: list = []
    accepted = object_field(server.response(TURN_ID, pending), "turn")
    turn_id = string_field(accepted, "id")
    if accepted.get("status") not in ("inProgress", "completed") or accepted.get("error") is not None:
        raise CaptureError("app-server did not accept the benchmark turn")
    server.active_turn = thread_id, turn_id
    reply = Reply()
    from_prefetch = iter(pending)
    while True:
        observation = next(from_prefetch, None)
        timestamp, message = observation if observation is not None else server.receive()
        method = message.get("method")
        if method is None:
            raise CaptureError("app-server sent an unexpected response after turn/start")
        if method not in TURN_EVENTS:
            continue
        params = object_field(message, "params")
        if string_field(params, "threadId") != thread_id:
            continue
        terminal_turn = None
        if method in ("turn/started", "turn/completed"):
            terminal_turn = object_field(params, "turn")
            event_turn_id = string_field(terminal_turn, "id")
        else:
            event_turn_id = string_field(params, "turnId")
        if event_turn_id != turn_id:
            raise CaptureError("app-server sent an unexpected turn for the benchmark thread")
        if method == "turn/completed":
            server.active_turn = None
            try:
                reply.finish(terminal_turn, suffix)
            except CaptureError as error:
                error.observed = timestamp
                raise
            trace.extend({"event": "text", "t": elapsed(server.started, when), "text": text}
                         for when, text in reply.chunks)
            return timestamp
        if method == "item/agentMessage/delta":
            reply.add_delta(timestamp, params)
        elif method in ("item/started", "item/completed"):
            reply.check_item(object_field(params, "item"), complete=method == "item/completed")
        elif method == "model/rerouted":
            raise CaptureError("app-server reported a model reroute")
        elif method == "error":
            raise CaptureError("app-server reported an error during the benchmark turn")
        elif method == "thread/tokenUsage/updated":
            usage = object_field(object_field(params, "tokenUsage"), "last")
            evidence["native_last_usage"] = {
                field: usage[field] for field in USAGE_FIELDS
                if type(usage.get(field)) is int and usage[field] >= 0
            }


def elapsed(started: int, observed: int) -> float:
    return (observed - started) / 1_000_000_000


def capture(executable: str, model: str, effort: str, tier: str, prompt: str, timeout: float,
            suffix: str | None) -> tuple[list, dict]:
    trace = [{"event": "start", "t": 0}]
    evidence = {"requested_model": model, "requested_effort": effort, "requested_tier": tier,
                "served_model": "unavailable", "served_effort": "unavailable", "served_tier": "unavailable"}
    with TemporaryDirectory(prefix="measure-tps-") as workspace:
        cwd = Path(workspace).resolve()
        server = None
        started = perf_counter_ns()
        try:
            server = AppServer(executable, cwd, timeout)
            started = server.started
            thread_id = start_thread(server, cwd, evidence)
            ended = capture_turn(server, thread_id, prompt, suffix, evidence, trace)
            status = {"status": "completed"}
        except CaptureError as error:
            ended = error.observed if error.observed is not None else perf_counter_ns()
            status = {"status": error.status, "reason": str(error)}
        except KeyboardInterrupt:
            ended = perf_counter_ns()
            status = {"status": "interrupted", "reason": "capture interrupted by the operator"}
        finally:
            if server is not None:
                try:
                    if server.active_turn is not None:
                        evidence["interrupt_sent"] = server.interrupt()
                finally:
                    server.close()
        metadata = {key: evidence[key] for key in ("configured_model", "configured_effort", "configured_tier")
                    if key in evidence}
        duration = elapsed(started, ended)
        trace.append({"event": "end", "t": duration, **status, **metadata})
        evidence.update(status, launch_total_s=duration)
        return trace, evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True, help="configured executable or wrapper on PATH or by path")
    parser.add_argument("--model", required=True, help="exact Codex model ID")
    parser.add_argument("--effort", required=True, help="exact Codex reasoning effort")
    parser.add_argument("--tier", required=True, help="exact service tier, such as default for standard speed")
    parser.add_argument("--prompt-file", required=True, type=Path, help="UTF-8 file containing the synthetic prompt")
    parser.add_argument("--output", required=True, type=Path, help="new filtered JSONL trace path")
    parser.add_argument("--timeout", type=float, default=240, help="attempt deadline in seconds (default: 240)")
    parser.add_argument("--expect-suffix", help="required reply suffix, ignoring trailing whitespace")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= TIMEOUT_MAX:
        parser.error("--timeout must be positive and within the platform's supported timeout range")
    controls = (args.model, args.effort, args.tier)
    try:
        if not all(value.strip().encode("utf-8") for value in controls):
            parser.error("--model, --effort, and --tier must be nonempty")
    except UnicodeEncodeError:
        parser.error("--model, --effort, and --tier must be valid UTF-8")
    if args.expect_suffix is not None and not args.expect_suffix.strip():
        parser.error("--expect-suffix must be nonempty")
    executable = shutil.which(args.codex)
    if executable is None:
        parser.error("--codex must name an executable on PATH or give its path")
    try:
        prompt = args.prompt_file.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        parser.error("--prompt-file must be a readable UTF-8 file")
    if not prompt.strip():
        parser.error("--prompt-file must contain a nonempty prompt")
    try:
        descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        parser.error("--output must name a new file in a writable directory")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as destination:
            trace, evidence = capture(os.path.abspath(executable), args.model, args.effort, args.tier,
                                      prompt, args.timeout, args.expect_suffix)
            for record in trace:
                destination.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        parser.exit(1, f"{parser.prog}: could not create the scratch workspace or write the trace\n")
    print(json.dumps(evidence))
    return 0 if evidence["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
