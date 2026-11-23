"""Offline protocol and process tests for capture.py."""

import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).with_name("capture.py")
SENSITIVE = "must-not-appear-in-capture"

EMIT_EVENTS = r"""
import json
import sys

assert sys.stdin.read() == ''
assert sys.argv[2:] == ['--print', '$(literal value); still argv']
sys.stderr.write('must-not-appear-in-capture\n')
for record in json.loads(sys.argv[1]):
    if isinstance(record, str):
        print(record, flush=True)
    else:
        print(json.dumps(record), flush=True)
"""


def claude_stream(kind, **fields):
    return {"type": "stream_event", "event": {"type": kind, **fields}}


def claude_conversation():
    model = "claude-example-1"
    text_fragments = [" Hé", "llo ", "world\n"]
    message = {"id": "message-1", "role": "assistant", "model": model}
    return [
        {"type": "system", "subtype": "ui_invalidate"},
        {"type": "system", "subtype": "init", "model": "sonnet", "tools": [], "session_id": SENSITIVE},
        claude_stream("message_start", message={**message, "content": []}),
        claude_stream("content_block_start", index=0, content_block={"type": "thinking", "thinking": SENSITIVE}),
        claude_stream("content_block_delta", index=0, delta={"type": "thinking_delta", "thinking": SENSITIVE}),
        {"type": "assistant", "message": {**message, "content": [{"type": "thinking", "thinking": SENSITIVE}]}},
        claude_stream("content_block_stop", index=0),
        claude_stream("content_block_start", index=1, content_block={"type": "text", "text": ""}),
        *(claude_stream("content_block_delta", index=1, delta={"type": "text_delta", "text": text})
          for text in text_fragments),
        {"type": "assistant", "message": {**message, "content": [{"type": "text", "text": "".join(text_fragments)}]}},
        claude_stream("content_block_stop", index=1),
        claude_stream("message_delta", delta={"stop_reason": "end_turn"}),
        claude_stream("message_stop"),
        {"type": "rate_limit_event", "info": SENSITIVE},
        {
            "type": "result", "subtype": "success", "is_error": False, "num_turns": 1,
            "result": "".join(text_fragments), "modelUsage": {model: {}}, "stop_reason": "end_turn",
            "usage": {"service_tier": "standard", "speed": "fast", "private": SENSITIVE},
        },
    ]


def agy_envelope(kind, **fields):
    return {"event": kind, kind: {"conversation_id": SENSITIVE, **fields}}


def agy_step(step_type, step_index, state="DONE", **fields):
    return agy_envelope("step_update", step_type=step_type, step_index=step_index, state=state, **fields)


def agy_conversation():
    return [
        agy_envelope("init", model="gemini-example-1", cwd=SENSITIVE),
        agy_step("user_input", 0, text_delta=SENSITIVE),
        agy_step("thinking", 1, text_delta=SENSITIVE),
        agy_step("agent_response", 2, "ACTIVE", text_delta="Hé"),
        agy_step("agent_response", 2, "ACTIVE", text_delta="llo"),
        agy_step("agent_response", 2, text_delta="!\n"),
        agy_step("checkpoint", 3),
        agy_envelope("result", status="SUCCESS", response="Héllo!\n", num_turns=1),
    ]


@unittest.skipUnless(os.name == "posix", "capture uses POSIX process groups and pipe handles")
class CaptureTests(unittest.TestCase):
    def run_code(self, client, code, *arguments, timeout=4, model=None):
        cmd = [sys.executable, str(SCRIPT), client, "--timeout", str(timeout)]
        if model:
            cmd += ["--expected-model", model]
        cmd += ["--", sys.executable, "-c", code, *arguments]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        self.assertEqual(proc.stderr, "")
        self.assertNotIn(SENSITIVE, proc.stdout)
        records = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(records[0], {"event": "start", "t": 0})
        self.assertEqual(records[-1]["event"], "end")
        self.assertEqual([r["t"] for r in records], sorted(r["t"] for r in records))
        return proc, records

    def capture_events(self, client, records, **options):
        return self.run_code(
            client, EMIT_EVENTS, json.dumps(records), "--print", "$(literal value); still argv",
            **options,
        )

    def assert_failed(self, result, reason):
        proc, records = result
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[-1]["status"], "failed")
        self.assertEqual(records[-1]["reason"], reason)

    def test_claude_stream_preserves_fragments_and_native_mode(self):
        proc, records = self.capture_events("claude", claude_conversation(), model="claude-example-1")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual([r["event"] for r in records[1:-1]], ["text"] * 3)
        self.assertEqual([r["text"] for r in records[1:-1]], [" Hé", "llo ", "world\n"])
        self.assertEqual(records[-1], {
            "event": "end", "t": records[-1]["t"], "status": "completed",
            "model": "claude-example-1", "configured_model": "sonnet", "speed": "fast", "tier": "standard",
        })

    def test_antigravity_ignores_hidden_fields_but_keeps_done_delta(self):
        proc, records = self.capture_events("antigravity", agy_conversation(), model="gemini-example-1")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual([r["text"] for r in records[1:-1]], ["Hé", "llo", "!\n"])
        self.assertEqual(records[-1], {
            "event": "end", "t": records[-1]["t"], "status": "completed", "configured_model": "gemini-example-1",
        })

    def test_done_only_reply_and_unterminated_last_line(self):
        events = agy_conversation()
        events = events[:3] + events[-3:]
        events[-1]["result"]["response"] = "!\n"
        wire = "\n".join(map(json.dumps, events))
        proc, records = self.run_code("antigravity", "import sys; sys.stdout.write(sys.argv[1])", wire)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[1]["text"], "!\n")

    def test_model_expectation_requires_actual_match_when_available(self):
        events = agy_conversation()
        events[-1]["result"]["model"] = "gemini-example-2"
        self.assert_failed(
            self.capture_events("antigravity", events, model="gemini-example-1"),
            "expected_model_unverified",
        )
        events[0]["init"].pop("model")
        events[-1]["result"].pop("model")
        self.assert_failed(
            self.capture_events("antigravity", events, model="gemini-example-1"),
            "expected_model_unverified",
        )
        claude = claude_conversation()
        claude[2]["event"]["message"]["model"] = "claude-example-2"
        self.assert_failed(self.capture_events("claude", claude), "inconsistent_model")

    def test_unknown_metadata_values_are_omitted(self):
        events = claude_conversation()
        events[-1]["usage"].update(service_tier=SENSITIVE, speed=SENSITIVE)
        events[1]["model"] = SENSITIVE
        proc, records = self.capture_events("claude", events)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(set(records[-1]), {"event", "t", "status", "model"})

    def test_inconsistent_native_mode_is_a_failure(self):
        events = claude_conversation()
        events[2]["event"]["message"]["usage"] = {"speed": "standard"}
        self.assert_failed(self.capture_events("claude", events), "inconsistent_mode")

    def test_claude_rejects_invalid_or_incomplete_turns(self):
        cases = {}
        original = claude_conversation()
        cases["missing_result"] = original[:-1]
        cases["incomplete_stream"] = original[:-3] + original[-2:]
        cases["unexpected_tool_or_turn"] = original[:3] + [
            claude_stream("content_block_start", index=0, content_block={"type": "tool_use", "input": SENSITIVE})
        ] + original[3:]
        cases["event_after_result"] = original + [original[-1]]
        cases["invalid_jsonl"] = [SENSITIVE] + original
        cases["terminal_text_mismatch"] = copy.deepcopy(original)
        cases["terminal_text_mismatch"][-1]["result"] = SENSITIVE
        cases["unsuccessful_turn"] = copy.deepcopy(original)
        cases["unsuccessful_turn"][-1]["num_turns"] = 2
        for reason, events in cases.items():
            with self.subTest(reason=reason):
                self.assert_failed(self.capture_events("claude", events), reason)

    def test_claude_requires_explicit_successful_stop_from_stream(self):
        events = [
            event for event in claude_conversation()
            if event.get("event", {}).get("type") != "message_delta"
        ]
        self.assert_failed(self.capture_events("claude", events), "incomplete_stream")
        events[-1].pop("stop_reason")
        self.assert_failed(self.capture_events("claude", events), "incomplete_stream")

        events = claude_conversation()
        events[-1]["stop_reason"] = "stop_sequence"
        self.assert_failed(self.capture_events("claude", events), "stop_reason_mismatch")
        events[-1].pop("stop_reason")
        proc, _ = self.capture_events("claude", events)
        self.assertEqual(proc.returncode, 0)

    def test_claude_requires_incremental_text_events(self):
        events = [
            event for event in claude_conversation()
            if event.get("event", {}).get("delta", {}).get("type") != "text_delta"
        ]
        self.assert_failed(self.capture_events("claude", events), "no_visible_stream")
        text_start = next(
            event["event"]["content_block"] for event in events
            if event.get("event", {}).get("content_block", {}).get("type") == "text"
        )
        text_start["text"] = events[-1]["result"]
        self.assert_failed(self.capture_events("claude", events), "nonincremental_text_start")

    def test_antigravity_rejects_tool_subagent_prompt_and_other_response(self):
        original = agy_conversation()
        for event in (
            agy_step("tool", 3, tool_info={"input": SENSITIVE}),
            agy_step("system", 3, subagent_info={"id": SENSITIVE}),
            agy_step("user_input", 3, text_delta=SENSITIVE),
            agy_step("agent_response", 4, text_delta=SENSITIVE),
        ):
            with self.subTest(kind=event["step_update"]["step_type"]):
                events = original[:-2] + [event] + original[-2:]
                self.assert_failed(self.capture_events("antigravity", events), "unexpected_tool_or_turn")

    def test_rejects_duplicate_json_fields(self):
        events = agy_conversation()
        events.insert(1, '{"event":"tool","event":"step_update","value":"must-not-appear-in-capture"}')
        self.assert_failed(self.capture_events("antigravity", events), "invalid_jsonl")

    def test_child_exit_nonzero_discards_valid_visible_text(self):
        self.assert_failed(
            self.run_code(
                "antigravity", EMIT_EVENTS + "\nsys.exit(17)",
                json.dumps(agy_conversation()), "--print", "$(literal value); still argv",
            ),
            "child_exit_nonzero",
        )

    def test_direct_child_timeout_after_valid_result(self):
        self.assert_failed(
            self.run_code(
                "antigravity", EMIT_EVENTS + "\nimport time; time.sleep(20)",
                json.dumps(agy_conversation()), "--print", "$(literal value); still argv", timeout=0.5,
            ),
            "timeout",
        )

    def test_timeout_terminates_wrapper_child_that_inherited_stdout(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "grandchild-ran"
            code = """
import subprocess, sys
subprocess.Popen([sys.executable, '-c', 'import sys,time; time.sleep(.8); open(sys.argv[1], "w").close()', sys.argv[1]])
"""
            self.assert_failed(
                self.run_code("antigravity", code, str(marker), timeout=0.4),
                "timeout",
            )
            time.sleep(0.7)
            self.assertFalse(marker.exists())

    def test_sigterm_produces_failed_trace_and_cleans_up_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "child-started"
            cmd = [sys.executable, str(SCRIPT), "antigravity", "--timeout", "10", "--", sys.executable, "-c",
                   "import os,sys,time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(20)", str(marker)]
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
                deadline = time.monotonic() + 3
                while not (marker.exists() and marker.stat().st_size) and time.monotonic() < deadline:
                    time.sleep(0.02)
                child_pid = int(marker.read_text())
                proc.send_signal(signal.SIGTERM)
                stdout, stderr = proc.communicate(timeout=4)
                self.assertEqual(stderr, "")
                self.assert_failed((proc, list(map(json.loads, stdout.splitlines()))), "interrupted")
                with self.assertRaises(ProcessLookupError):
                    os.kill(child_pid, 0)

    def test_preserves_waits_between_receipt_events(self):
        code = """
import json, sys, time
for i, event in enumerate(json.loads(sys.argv[1])):
    if i in (4, 7):
        time.sleep(0.25)
    print(json.dumps(event), flush=True)
"""
        proc, records = self.run_code("antigravity", code, json.dumps(agy_conversation()))
        self.assertEqual(proc.returncode, 0)
        self.assertGreater(records[2]["t"] - records[1]["t"], 0.10)
        self.assertGreater(records[-1]["t"] - records[-2]["t"], 0.10)

    def test_spawn_failure_and_argument_errors_do_not_echo_inputs(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "claude", "--", f"/no/such/program/{SENSITIVE}"],
            capture_output=True, text=True, timeout=4,
        )
        self.assertNotIn(SENSITIVE, proc.stderr + proc.stdout)
        self.assert_failed((proc, list(map(json.loads, proc.stdout.splitlines()))), "launch_failed")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "claude", "--timeout", SENSITIVE, "--", SENSITIVE],
            capture_output=True, text=True, timeout=4,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(SENSITIVE, proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
