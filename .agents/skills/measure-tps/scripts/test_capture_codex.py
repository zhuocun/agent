import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from tempfile import TemporaryDirectory
import textwrap
import unittest
from unittest.mock import patch

from capture_codex import AppServer, CaptureError
from measure import read_trace


SCRIPT = Path(__file__).resolve().with_name("capture_codex.py")
MOCK_SERVER = '''\
import json
import os
from pathlib import Path
import sys

case = os.environ["TEST_CAPTURE_SCENARIO"]
secret = "PRIVATE_PROTOCOL_PAYLOAD"
assert sys.argv[1:] == ["app-server", "--stdio"]
assert not list(Path.cwd().iterdir())
print(secret, file=sys.stderr, flush=True)


def receive(method):
    message = json.loads(sys.stdin.readline())
    assert message["method"] == method
    return message.get("id"), message["params"]


def send(message):
    print(json.dumps(message), flush=True)


def answer(identifier, **result):
    send({"id": identifier, "result": result})


def notify(method, **params):
    send({"method": method, "params": params})


def turn_event(method, **params):
    notify(method, threadId="target-thread", turnId="target-turn", **params)


if case == "bad_stdout":
    print(secret, flush=True)
    sys.exit()
if case == "bad_method":
    send({"method": [secret]})
    sys.exit()
identifier, initialization = receive("initialize")
assert initialization["capabilities"]["experimentalApi"] is True
answer(identifier, codexHome=secret)
receive("initialized")
identifier, config = receive("thread/start")
assert config["model"] == "mock-model"
assert config["serviceTier"] == "default"
assert config["config"]["model_reasoning_effort"] == "xhigh"
assert config["approvalPolicy"] == "never"
assert config["sandbox"] == "read-only"
assert config["ephemeral"] is True
assert config["allowProviderModelFallback"] is False
assert config["dynamicTools"] == []
assert Path(config["cwd"]) == Path.cwd()
if case == "rpc_error":
    send({"id": identifier, "error": {"message": secret}})
    sys.exit()
answer(identifier, model="another-model" if case == "model_mismatch" else config["model"],
       modelProvider="mock-provider",
       serviceTier="priority" if case == "tier_mismatch" else config["serviceTier"],
       reasoningEffort="low" if case == "effort_mismatch" else config["config"]["model_reasoning_effort"],
       cwd=config["cwd"], approvalPolicy="never",
       sandbox={"type": "readOnly", "networkAccess": case == "wrong_sandbox"},
       thread={"id": "target-thread", "ephemeral": True, "turns": [], "cliVersion": "0.100.0"})
identifier, submitted = receive("turn/start")
assert submitted["threadId"] == "target-thread"
assert submitted["model"] == "mock-model"
assert submitted["input"] == [{"type": "text", "text": "A synthetic text prompt."}]
assert submitted["serviceTier"] == "default"
assert submitted["effort"] == "xhigh"
notify("turn/started", threadId="target-thread", turn={"id": "target-turn", "status": "inProgress"})
answer(identifier, turn={"id": "target-turn", "status": "inProgress"})
if case == "eof":
    sys.exit()
if case == "timeout":
    interrupt_id, params = receive("turn/interrupt")
    assert params == {"threadId": "target-thread", "turnId": "target-turn"}
    answer(interrupt_id)
    sys.exit()
if case == "tool":
    turn_event("item/started", item={"type": "commandExecution", "command": secret})
if case == "server_request":
    send({"id": 78, "method": "item/commandExecution/requestApproval", "params": {"command": secret}})
if case == "rerouted":
    turn_event("model/rerouted", toModel=secret)
if case == "error":
    turn_event("error", error={"message": secret}, willRetry=True)
notify("item/agentMessage/delta", threadId="other-thread", turnId="other-turn", itemId="other-item", delta=secret)
turn_event("item/completed", item={"type": "reasoning", "content": [secret], "summary": [secret]})
turn_event("item/started", item={"type": "agentMessage", "id": "answer", "text": "", "phase": "final_answer"})
if case == "wrong_turn":
    notify("item/agentMessage/delta", threadId="target-thread", turnId="wrong-turn", itemId="answer", delta=secret)
if case != "final_only":
    turn_event("item/agentMessage/delta", itemId="answer", delta="Hello, ")
    turn_event("item/agentMessage/delta", itemId="answer", delta="")
    turn_event("item/agentMessage/delta", itemId="answer", delta="世界!\\nEND\\n")
completed = {"type": "agentMessage", "id": "second" if case == "wrong_item" else "answer", "phase": "final_answer",
             "text": "different text" if case == "missing_delta" else "Hello, 世界!\\nEND\\n"}
turn_event("item/completed", item=completed)
turn_event("thread/tokenUsage/updated", tokenUsage={"last": {
    "inputTokens": 100, "outputTokens": 80, "reasoningOutputTokens": 60, "secret": secret,
}})
notify("turn/completed", threadId="target-thread", turn={
    "id": "target-turn", "status": "interrupted" if case == "interrupted" else "completed",
    "items": [completed], "error": None,
})
'''


class ArrivalDeadlineTests(unittest.TestCase):
    def test_deadline_uses_reader_receipt_even_when_the_consumer_is_late(self):
        server = AppServer.__new__(AppServer)
        server.incoming = Queue()
        server.deadline = 10
        line = b'{"method":"turn/completed"}\n'
        server.incoming.put((9, line))
        server.incoming.put((11, line))
        with patch("capture_codex.perf_counter_ns", return_value=12):
            self.assertEqual(server.receive(), (9, {"method": "turn/completed"}))
            with self.assertRaises(CaptureError) as error:
                server.receive()
        self.assertEqual(error.exception.status, "timed_out")
        self.assertEqual(error.exception.observed, 10)


@unittest.skipUnless(os.name == "posix", "mock executable uses a POSIX shebang")
class CodexCaptureTests(unittest.TestCase):
    def setUp(self):
        workspace = TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name)
        self.wrapper = self.workspace / "mock-codex"
        self.wrapper.write_text(f"#!{sys.executable}\n" + textwrap.dedent(MOCK_SERVER), encoding="utf-8")
        self.wrapper.chmod(0o700)
        self.prompt = self.workspace / "prompt.txt"
        self.prompt.write_text("A synthetic text prompt.", encoding="utf-8")

    def run_capture(self, case, timeout=5, suffix="END"):
        trace_path = self.workspace / f"{case}.jsonl"
        process = subprocess.run([
            sys.executable, str(SCRIPT), "--codex", "./mock-codex", "--model", "mock-model",
            "--effort", "xhigh", "--tier", "default", "--prompt-file", str(self.prompt),
            "--output", str(trace_path), "--timeout", str(timeout), "--expect-suffix", suffix,
        ], cwd=self.workspace, env={**os.environ, "TEST_CAPTURE_SCENARIO": case},
            text=True, capture_output=True, timeout=8)
        raw_trace = trace_path.read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE_PROTOCOL_PAYLOAD", raw_trace + process.stdout + process.stderr)
        self.assertNotIn("A synthetic text prompt.", raw_trace + process.stdout + process.stderr)
        self.assertEqual(process.stderr, "")
        records = [json.loads(line) for line in raw_trace.splitlines()]
        return process.returncode, records, json.loads(process.stdout)

    def test_capture_is_readable_by_the_calculator(self):
        code, records, evidence = self.run_capture("success")
        self.assertEqual(code, 0)
        self.assertEqual([record["event"] for record in records], ["start", "submit", "text", "text", "end"])
        trace = read_trace(json.dumps(record) for record in records)
        self.assertEqual([chunk.text for chunk in trace.chunks], ["Hello, ", "世界!\nEND\n"])
        self.assertGreater(trace.submit, 0)
        self.assertLessEqual(trace.submit, trace.chunks[0].t)
        self.assertLessEqual(trace.chunks[-1].t, trace.end)
        self.assertEqual(trace.metadata, {
            "configured_model": "mock-model", "configured_effort": "xhigh", "configured_tier": "default",
        })
        self.assertEqual(evidence["client_version"], "0.100.0")
        self.assertEqual(evidence["configured_provider"], "mock-provider")
        self.assertEqual(evidence["served_tier"], "unavailable")
        self.assertEqual(evidence["native_last_usage"], {
            "inputTokens": 100, "outputTokens": 80, "reasoningOutputTokens": 60,
        })

    def test_failures_discard_text_and_record_a_reason(self):
        for case, reason in {
            "wrong_turn": "unexpected turn", "wrong_item": "more than one assistant message",
            "missing_delta": "differs from the completed reply", "final_only": "text is missing",
            "tool": "tool activity", "rerouted": "model reroute", "error": "reported an error",
            "server_request": "unexpected request", "eof": "closed stdout", "bad_stdout": "JSONL",
            "bad_method": "method string", "interrupted": "interrupted turn",
            "wrong_suffix": "expected output suffix",
        }.items():
            with self.subTest(case=case):
                code, records, evidence = self.run_capture(case, suffix="THE END" if case == "wrong_suffix" else "END")
                self.assertEqual(code, 1)
                self.assertNotIn("text", [record["event"] for record in records])
                self.assertEqual(records[-1]["status"], "interrupted" if case == "interrupted" else "failed")
                self.assertEqual(evidence["reason"], records[-1]["reason"])
                self.assertIn(reason, evidence["reason"])

    def test_configuration_mismatches_stop_before_submission(self):
        for case, reason in {
            "model_mismatch": "requested model", "tier_mismatch": "requested tier",
            "effort_mismatch": "requested effort", "wrong_sandbox": "read-only sandbox",
            "rpc_error": "rejected thread/start",
        }.items():
            with self.subTest(case=case):
                code, records, evidence = self.run_capture(case)
                self.assertEqual(code, 1)
                self.assertEqual([record["event"] for record in records], ["start", "end"])
                self.assertIn(reason, evidence["reason"])

    def test_timeout_censors_the_attempt_at_the_configured_boundary(self):
        code, records, evidence = self.run_capture("timeout", timeout=0.5)
        self.assertEqual(code, 1)
        self.assertEqual([record["event"] for record in records], ["start", "submit", "end"])
        self.assertEqual(records[-1]["t"], 0.5)
        self.assertEqual(evidence["status"], "timed_out")
        self.assertTrue(evidence["interrupt_sent"])


if __name__ == "__main__":
    unittest.main()
