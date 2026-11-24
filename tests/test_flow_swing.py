import csv
import json
import pathlib
import tempfile
import unittest

from options.flow_swing import candidates, pick_contract
from scripts import flow_swing


def brow(t, c, p, active=20, above=2.0, close=100, low=98):
    return {"ticker": t, "call_avg": str(c), "put_avg": str(p), "call_active": str(active),
            "above_low_pct": "" if above is None else str(above), "close": str(close), "day_low": str(low)}


def call(exp, strike, delta, bid, ask, oi=1000):
    return {"type": "call", "expiry": exp, "strike": strike, "delta": delta, "bid": bid, "ask": ask, "oi": oi}


class CandidatesTest(unittest.TestCase):
    def test_filters_and_rank(self):
        rows = [brow("AAA", 10, 4), brow("BBB", 6, 1), brow("CCC", 3, 2),           # CCC ratio 1.5 < 2
                brow("DDD", 9, 1, active=5), brow("EEE", 9, 1, above=0.5),          # too few active / not off low
                brow("FFF", 9, 1, above=None), brow("GGG", 0, 0)]
        self.assertEqual([r["ticker"] for r in candidates(rows)], ["BBB", "AAA"])
        self.assertEqual(candidates([brow("HHH", 5, 0)])[0]["ratio"], 999.0)


class ContractTest(unittest.TestCase):
    def test_pick(self):
        chain = {"contracts": [call("2026-12-11", 80, 0.42, 1.40, 1.50),      # 17 dte, fits
                               call("2026-12-11", 78, 0.55, 2.40, 2.50),      # delta and ask out of band
                               call("2026-11-27", 80, 0.40, 0.90, 1.00),      # 3 dte, too short
                               call("2026-12-11", 82, 0.33, 0.60, 0.90),      # spread too wide
                               call("2026-12-11", 81, 0.38, 1.10, 1.15, oi=100)]}  # thin OI
        c = pick_contract(chain, "2026-11-24")
        self.assertEqual((c["strike"], c["ask"]), (80, 1.50))
        self.assertEqual((c["take_profit_at"], c["stop_at"], c["time_exit"]), (2.4, 0.75, "2026-12-04"))
        self.assertIsNone(pick_contract({"contracts": []}, "2026-11-24"))


class ScriptTest(unittest.TestCase):
    def test_candidate_then_no_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            with open(d / "b.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(brow("X", 1, 1)))
                w.writeheader()
                w.writerow(brow("AAA", 10, 2))
            (d / "ch").mkdir()
            (d / "ch/a.json").write_text(json.dumps({"symbol": "AAA", "asof": "2026-11-24T16:00:00Z",
                                                     "contracts": [call("2026-12-11", 80, 0.42, 1.40, 1.50)]}))
            log = d / "log.jsonl"
            flow_swing.main(["--today", "2026-11-24", "--board", str(d / "b.csv"), "--log", str(log)])
            flow_swing.main(["--today", "2026-11-24", "--board", str(d / "b.csv"), "--log", str(log),
                             "--chains", str(d / "ch")])
            lines = [json.loads(x) for x in log.read_text().splitlines()]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["status"], "candidate (no quoted chain)")
            log.unlink()
            flow_swing.main(["--today", "2026-11-24", "--board", str(d / "b.csv"), "--log", str(log),
                             "--chains", str(d / "ch")])
            line = json.loads(log.read_text())
            self.assertEqual(line["status"], "paper pick")
            self.assertIn("BUY TO OPEN 1 AAA 2026-12-11 80 CALL", line["ticket"])


if __name__ == "__main__":
    unittest.main()
