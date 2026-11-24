import json
import pathlib
import tempfile
import unittest

from options.fallback import board, summarize
from scripts import fallback_board


def row(exp, strike, typ, ratio, date="2026-11-24"):
    return {"expiration": exp, "strike": f"{strike:.2f}", "type": typ, "date": date,
            "volume_open_interest_ratio": None if ratio is None else f"{ratio:.8f}"}


class SummarizeTest(unittest.TestCase):
    def test_window_and_lean(self):
        rows = [row("2026-11-25", 100, "call", 9), row("2026-11-25", 100, "put", 1),
                row("2026-11-25", 200, "call", 500),          # strike outside the 12% band
                row("2027-01-15", 100, "put", 500)]           # expiry after the window
        s = summarize(rows, 100.0, "2026-12-18")
        self.assertEqual(s["call_avg"], 9)
        self.assertEqual(s["put_avg"], 1)
        self.assertEqual(s["lean"], "calls")
        self.assertEqual((s["call_active"], s["put_active"]), (1, 0))
        self.assertTrue(s["top"].startswith("2026-11-25 100C 9x"))

    def test_mixed_puts_and_nulls(self):
        self.assertEqual(summarize([row("2026-11-25", 100, "call", 2), row("2026-11-25", 100, "put", 2.5)],
                                   100.0, "2026-12-18")["lean"], "mixed")
        s = summarize([row("2026-11-25", 100, "call", None), row("2026-11-25", 100, "put", 3)], 100.0, "2026-12-18")
        self.assertEqual(s["call_avg"], 0)
        self.assertEqual(s["lean"], "puts")

    def test_min_expiry_skips_same_day(self):
        rows = [row("2026-11-24", 100, "call", 400), row("2026-11-25", 100, "call", 2)]
        self.assertEqual(summarize(rows, 100.0, "2026-12-18", min_expiry="2026-11-25")["call_avg"], 2)

    def test_empty_window(self):
        self.assertIsNone(summarize([row("2027-01-15", 100, "call", 5)], 100.0, "2026-12-18"))


class BoardTest(unittest.TestCase):
    def test_rank_and_quote_join(self):
        scores = {"AAA": summarize([row("2026-11-25", 100, "call", 2)], 100.0, "2026-12-18"),
                  "BBB": summarize([row("2026-11-25", 50, "put", 8)], 50.0, "2026-12-18"),
                  "CCC": None}
        b = board(scores, {"AAA": {"close": 102, "low": 100, "high": 104, "change": -1.234}})
        self.assertEqual([r["ticker"] for r in b], ["BBB", "AAA"])
        self.assertEqual(b[1]["above_low_pct"], 2.0)
        self.assertEqual(b[1]["change_pct"], -1.23)
        self.assertIsNone(b[0]["close"])
        self.assertTrue(all(r["source"] == "fallback" for r in b))


class ScriptTest(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "av.json").write_text(json.dumps({"symbol": "AAA", "data": [row("2026-11-25", 100, "call", 4),
                                                                               row("2026-11-25", 100, "put", 1)]}))
            (d / "q.json").write_text(json.dumps({"data": {"NASDAQ:AAA": {"close": 100, "low": 95, "high": 101,
                                                                          "change": 2}}}))
            fallback_board.main(["--today", "2026-11-24", "--quotes", str(d / "q.json"), "--out", str(d / "out"),
                                 f"{d / 'av.json'}:AAA", f"{d / 'missing.json'}:ZZZ"])
            text = (d / "out/flow_board.csv").read_text().splitlines()
            self.assertEqual(len(text), 2)
            self.assertIn("AAA,fallback,calls", text[1])


if __name__ == "__main__":
    unittest.main()
