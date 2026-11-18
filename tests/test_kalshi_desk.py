import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_board  # noqa: E402
import build_dashboard  # noqa: E402
from kalshi import desk, taker_fee_cents  # noqa: E402


def book(yes_bids, no_bids):
    """Bids as (cents, qty); Kalshi lists bids only."""
    f = lambda xs: [[f"{p / 100:.2f}", str(q)] for p, q in xs]
    return {"orderbook_fp": {"yes_dollars": f(yes_bids), "no_dollars": f(no_bids)}}


FIX = {
    "markets": {"KXBTC15M": [{"ticker": "A", "close_time": "t1"}, {"ticker": "B"}],
                "KXETH15M": [{"ticker": "C"}]},
    "books": {"A": book([(48, 10)], [(50, 7)]),      # asks yes 50 / no 52 -> cost 102
              "B": book([(60, 5)], [(60, 5)]),       # crossed: asks 40/40 -> cost 80
              "C": book([], [])},
}


class Edge(unittest.TestCase):
    def test_edge_math(self):
        r = desk.analyse("A", FIX["books"]["A"])
        self.assertEqual((r["yes_ask"], r["no_ask"], r["cost_c"]), (50, 52, 102))
        fees = taker_fee_cents(50, 1) + taker_fee_cents(52, 1)
        self.assertEqual(r["fees_c"], fees)
        self.assertEqual(r["edge_c"], 100 - 102 - fees)
        self.assertEqual(r["spread_c"], 2)
        self.assertEqual(r["depth"], 7)
        self.assertFalse(r["lock"])

    def test_lock_flag(self):
        r = desk.analyse("B", FIX["books"]["B"])
        self.assertEqual(r["edge_c"], 100 - 80 - 2 * taker_fee_cents(40, 1))
        self.assertTrue(r["lock"])

    def test_empty_book(self):
        r = desk.analyse("C", FIX["books"]["C"])
        self.assertIsNone(r["edge_c"])
        self.assertFalse(r["lock"])
        self.assertIsNone(desk.analyse("D", {})["edge_c"])

    def test_rank_and_summary(self):
        rows = desk.rank([desk.analyse(t, FIX["books"][t]) for t in "ACB"])
        self.assertEqual([r["ticker"] for r in rows], ["B", "A", "C"])
        s = desk.summarise(rows)
        self.assertEqual((s["markets"], s["priced"], s["locks"]), (3, 2, 1))
        none = desk.summarise([desk.analyse("A", FIX["books"]["A"])])
        self.assertTrue(none["message"].startswith("No fee-net edge"))
        self.assertIn("No priced", desk.summarise([])["message"])


class EndToEnd(unittest.TestCase):
    def test_offline_run(self):
        with tempfile.TemporaryDirectory() as d:
            fx = pathlib.Path(d) / "fx.json"
            fx.write_text(json.dumps(FIX))
            out = pathlib.Path(d) / "out"
            for _ in range(2):
                self.assertEqual(desk.main(["scan", "--series", "KXBTC15M", "KXETH15M", "--out", str(out),
                                            "--offline", str(fx)]), 0)
            scan = json.loads((out / "scan.json").read_text())
            self.assertEqual([r["ticker"] for r in scan["rows"]], ["B", "A", "C"])
            self.assertEqual(scan["series"], ["KXBTC15M", "KXETH15M"])
            cfg = json.loads((out / "kalshi_desk.json").read_text())
            self.assertEqual(build_board.validate(cfg), [])
            self.assertEqual(cfg["mode"], "PAPER")
            self.assertNotIn("LIVE", (out / "kalshi_desk.json").read_text())
            self.assertNotIn("LIVE", (out / "scan.json").read_text())
            lines = (out / "paper_log.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertNotIn("LIVE", lines[0])
            html = build_dashboard.render(str(out / "scan.json"))
            self.assertIn("Kalshi · book scan", html)

    def test_empty_run_validates(self):
        with tempfile.TemporaryDirectory() as d:
            fx = pathlib.Path(d) / "fx.json"
            fx.write_text("{}")
            r = desk.run(["KXBTC15M"], pathlib.Path(d) / "o", offline=str(fx))
            self.assertEqual(r["rows"], [])
            self.assertEqual(build_board.validate(desk.board_config(r)), [])


if __name__ == "__main__":
    unittest.main()
