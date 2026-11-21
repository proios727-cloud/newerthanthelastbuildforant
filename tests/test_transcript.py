import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from _transcript import tool_results  # noqa: E402


def call(ts, uid, name="mcp__x__quote"):
    return json.dumps({"timestamp": ts, "message": {"content": [
        {"type": "tool_use", "id": uid, "name": name, "input": {"s": uid}}]}})


def result(ts, uid, body="ok"):
    return json.dumps({"timestamp": ts, "message": {"content": [
        {"type": "tool_result", "tool_use_id": uid, "content": body}]}})


def names(lines, since):
    return [args["s"] for _, args, _ in tool_results(lines, lambda n: True, since)]


class SinceTest(unittest.TestCase):
    def test_same_second_with_fraction_is_kept(self):
        # Regression: as text, "00:42:57.184Z" sorts before "00:42:57Z" and the call was dropped.
        lines = [call("2026-11-21T00:42:57.184Z", "a"), result("2026-11-21T00:42:57.900Z", "a")]
        self.assertEqual(names(lines, "2026-11-21T00:42:57Z"), ["a"])

    def test_earlier_records_are_skipped(self):
        lines = [call("2026-11-21T00:42:56.999Z", "old"), result("2026-11-21T00:42:57.100Z", "old"),
                 call("2026-11-21T00:43:01Z", "new"), result("2026-11-21T00:43:02Z", "new")]
        self.assertEqual(names(lines, "2026-11-21T00:42:57Z"), ["new"])

    def test_offset_and_z_compare_as_instants(self):
        lines = [call("2026-11-20T19:43:00-05:00", "a"), result("2026-11-20T19:43:01-05:00", "a")]
        self.assertEqual(names(lines, "2026-11-21T00:42:59Z"), ["a"])
        self.assertEqual(names(lines, "2026-11-21T00:43:01Z"), [])

    def test_no_since_keeps_all(self):
        lines = [call("2026-11-21T00:00:00Z", "a"), result("2026-11-21T00:00:01Z", "a")]
        self.assertEqual(names(lines, ""), ["a"])

    def test_unparseable_stamp_falls_back_to_text(self):
        lines = [call("", "a"), result("", "a")]
        self.assertEqual(names(lines, "2026-11-21T00:00:00Z"), [])


if __name__ == "__main__":
    unittest.main()
