import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import measure


START = {"event": "start", "t": 0}


def text(t, fragment):
    return {"event": "text", "t": t, "text": fragment}


def end(t, **metadata):
    return {"event": "end", "t": t, "status": "completed", **metadata}


def jsonl(records):
    return "".join(json.dumps(record) + "\n" for record in records)


class FixtureEncoding:
    """Supply the expected token bytes and record the entire encoder input."""

    name = "fixture"

    def __init__(self, pieces):
        self.pieces = pieces
        self.inputs = []

    def encode_ordinary(self, visible_text):
        self.inputs.append(visible_text)
        return list(range(len(self.pieces)))

    def decode_single_token_bytes(self, token):
        return self.pieces[token]


class MeasureTests(unittest.TestCase):
    def report(self, records, pieces):
        trace = measure.read_trace(io.StringIO(jsonl(records)))
        encoding = FixtureEncoding(pieces)
        result = measure.measure(trace, encoding)
        self.assertEqual(encoding.inputs, [b"".join(pieces).decode("utf-8")])
        return result

    def test_launch_and_submit_timing_with_late_end(self):
        result = self.report(
            [
                START,
                {"event": "submit", "t": 1},
                text(2, "AB"),
                text(3, "C"),
                text(4, "D"),
                end(
                    8,
                    configured_model="selected",
                    configured_effort="medium",
                    configured_tier="priority",
                    model="observed",
                    speed="fast",
                    tier="priority",
                ),
            ],
            [b"A", b"B", b"C", b"D"],
        )
        self.assertEqual(
            result,
            {
                "encoding": "fixture",
                "model": "observed",
                "configured_effort": "medium",
                "configured_model": "selected",
                "configured_tier": "priority",
                "speed": "fast",
                "tier": "priority",
                "output_tokens": 4,
                "text_chunks": 3,
                "text_batches": 3,
                "first_batch_tokens": 2,
                "launch_ttft_s": 2,
                "launch_total_s": 8,
                "end_to_end_tps": 0.5,
                "decode_tps": 1,
                "middle_10_90_tps": 1,
                "submit_ttft_s": 1,
                "submit_total_s": 7,
            },
        )

    def test_split_token_unicode_and_whitespace(self):
        result = self.report(
            [START, text(1, ""), text(2, " hé"), text(3, "llo"), text(4, "界\n"), end(5)],
            [b" ", b"h\xc3\xa9llo", b"\xe7", b"\x95\x8c", b"\n"],
        )
        self.assertEqual(result["output_tokens"], 5)
        self.assertEqual(result["first_batch_tokens"], 1)
        self.assertEqual(result["launch_ttft_s"], 2)
        self.assertEqual(result["decode_tps"], 2)
        self.assertIsNone(result["submit_ttft_s"])

    def test_equal_timestamps_form_one_batch(self):
        result = self.report(
            [START, text(1, "A"), text(1, "B"), text(2, "C"), end(4)],
            [b"A", b"B", b"C"],
        )
        self.assertEqual(result["text_chunks"], 3)
        self.assertEqual(result["text_batches"], 2)
        self.assertEqual(result["first_batch_tokens"], 2)
        self.assertEqual(result["decode_tps"], 1)

    def test_middle_uses_actual_counts_for_two_large_batches(self):
        result = self.report(
            [START, text(2, "a" * 50), text(4, "a" * 50), end(7)],
            [b"a"] * 100,
        )
        self.assertEqual(result["middle_10_90_tps"], 25)

    def test_middle_uses_interior_batches_when_available(self):
        result = self.report(
            [
                START,
                text(1, "a" * 5),
                text(2, "a" * 15),
                text(5, "a" * 75),
                text(9, "a" * 5),
                end(10),
            ],
            [b"a"] * 100,
        )
        self.assertEqual(result["middle_10_90_tps"], 25)

    def test_missing_or_insufficient_text_has_null_rates(self):
        result = self.report(
            [START, {"event": "submit", "t": 1}, text(2, ""), end(3)],
            [],
        )
        self.assertEqual(result["output_tokens"], 0)
        self.assertEqual(result["text_batches"], 0)
        self.assertEqual(result["submit_total_s"], 2)
        for field in ("launch_ttft_s", "submit_ttft_s", "decode_tps", "end_to_end_tps", "middle_10_90_tps"):
            with self.subTest(field=field):
                self.assertIsNone(result[field])

    def test_one_batch_produces_only_end_to_end_rate(self):
        result = self.report([START, text(1, "A"), text(1, "B"), end(3)], [b"A", b"B"])
        self.assertEqual(result["end_to_end_tps"], 2 / 3)
        self.assertEqual(result["text_batches"], 1)
        self.assertIsNone(result["decode_tps"])
        self.assertIsNone(result["middle_10_90_tps"])

    def test_middle_is_null_when_both_thresholds_land_in_the_same_batch(self):
        result = self.report(
            [START, text(1, "a" * 95), text(2, "a" * 5), end(3)],
            [b"a"] * 100,
        )
        self.assertEqual(result["decode_tps"], 5)
        self.assertIsNone(result["middle_10_90_tps"])

    def test_zero_or_unrepresentable_rate_is_null(self):
        result = self.report([START, text(0, "A"), end(0)], [b"A"])
        self.assertEqual(result["launch_ttft_s"], 0)
        self.assertIsNone(result["end_to_end_tps"])
        self.assertIsNone(measure.rate(1, 5e-324))


class TraceTests(unittest.TestCase):
    def test_rejects_invalid_sequences(self):
        cases = [
            ([], "missing final end"),
            ([START, text(1, "secret")], "missing final end"),
            ([text(0, "secret"), end(1)], "line 1: expected a start"),
            ([{"event": "start", "t": 1}, end(2)], "line 1: expected a start"),
            ([START, START, end(2)], "line 2: start must be the first"),
            ([START, text(1, ""), {"event": "submit", "t": 2}, end(3)], "line 3: submit must follow"),
            ([START, text(2, "secret"), end(1)], "line 3: timestamps must be nondecreasing"),
            (
                [START, text(9007199254740993, "secret"), end(9007199254740992)],
                "line 3: timestamps must be nondecreasing",
            ),
            ([START, end(2), text(3, "secret")], "line 3: expected the end event to be last"),
            ([START, end(2), end(2)], "line 3: expected the end event to be last"),
            ([START, end(2, status="failed", reason="secret")], "line 2: end status must be completed"),
            ([START, end(2, reason="secret")], "line 2: completed end cannot include a failure reason"),
            ([START, {"event": "error", "t": 2, "text": "secret"}, end(3)], "line 2: expected a start"),
        ]
        for records, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(measure.MeasurementError, expected) as caught:
                    measure.read_trace(io.StringIO(jsonl(records)))
                self.assertNotIn("secret", str(caught.exception))

    def test_rejects_invalid_timestamps(self):
        for invalid in (True, "1", -1, float("inf"), float("-inf"), float("nan"), 10**400, None):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(measure.MeasurementError, "line 2: expected finite"):
                    measure.read_trace(io.StringIO(jsonl([START, text(invalid, "secret"), end(3)])))

    def test_rejects_bad_fields_and_json(self):
        cases = (
            ('{"event":"text","t":1,"text":"secret","text":"last"}', "expected one valid JSON object"),
            ('{"event":[],"t":1}', "expected a start, submit, text, or end event"),
            ('{"event":"text","t":1,"reasoning":"secret","text":"visible"}', "unexpected or missing fields"),
            ('{"event":"text","t":1}', "unexpected or missing fields"),
            ('{"event":"text","t":1,"text":1}', "expected a string"),
            ('{"event":"text","t":1,"text":"\\ud800"}', "contains invalid Unicode"),
            ('{"event":"end","t":2,"status":"completed","model":null}', "expected a nonempty string"),
            ('{"event":"end","t":2,"status":"completed","tier":" "}', "expected a nonempty string"),
            ('["secret"]', "expected one JSON object"),
            ('secret', "expected one valid JSON object"),
            ('', "expected one valid JSON object"),
        )
        for raw, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(measure.MeasurementError, expected) as caught:
                    measure.read_trace(io.StringIO(jsonl([START]) + raw + "\n" + jsonl([end(3)])))
                self.assertNotIn("secret", str(caught.exception))

    def test_cli_accepts_an_encoding_override_and_prints_only_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.jsonl"
            path.write_text(jsonl([START, text(1, "visible"), end(2)]), encoding="utf-8")
            with patch.object(measure, "load_encoding", return_value=FixtureEncoding([b"visible"])) as load:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(measure.main([str(path), "--encoding", "selected_encoding"]), 0)
        load.assert_called_once_with("selected_encoding")
        self.assertEqual(json.loads(stdout.getvalue())["output_tokens"], 1)
        self.assertNotIn("visible", stdout.getvalue())

    def test_cli_reports_invalid_trace_before_loading_tokenizer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.jsonl"
            path.write_text(jsonl([START, text(1, "secret")]), encoding="utf-8")
            stderr = io.StringIO()
            stdout = io.StringIO()
            with patch.object(measure, "load_encoding") as load:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught:
                        measure.main([str(path)])
        self.assertEqual(caught.exception.code, 1)
        load.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("missing final end event with status completed", stderr.getvalue())
        self.assertNotIn("secret", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
