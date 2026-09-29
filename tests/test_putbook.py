import unittest
from datetime import date

from fund import putbook


def trend(n=60, start=300.0, step=1.0):
    return [start + i * step for i in range(n)]


BARS = {"AAPL": {"last": "2026-09-28", "closes": trend(start=280)},
        "SPY": {"last": "2026-09-28", "closes": trend(start=700)}}
D = date(2026, 9, 28)


def row(k, delta, bid, ask, exp="2026-10-30", iid=None):
    return {"instrument_id": iid or f"id{k}", "strike": k, "expiration": exp, "bid": bid, "ask": ask, "delta": delta}


class PutBookTests(unittest.TestCase):
    def test_plan_is_causal_and_lists_candidates(self):
        p = putbook.plan(putbook.new_state(), BARS, D)
        syms = [c["symbol"] for c in p["candidates"]]
        self.assertIn("AAPL", syms)
        c = next(c for c in p["candidates"] if c["symbol"] == "AAPL")
        ks = c["try_strikes"]
        self.assertEqual(ks, sorted(ks))
        self.assertLessEqual(ks[4], c["spot"] + 5)  # centre of the ladder within one strike step of spot

    def test_entry_picks_30_delta_sells_bid_whole_contracts(self):
        st = putbook.new_state()
        q = {"chains": {"AAPL": [row(320, -0.20, 3.4, 3.7), row(325, -0.28, 4.55, 4.9), row(330, -0.34, 6.05, 6.35)]}}
        putbook.apply(st, BARS, q, D)
        p = st["positions"]["AAPL"]
        self.assertEqual((p["strike"], p["contracts"], p["credit_px"]), (325, 1, 4.55))
        self.assertAlmostEqual(st["cash"], 100_000 + 455 - 0.03, places=2)

    def test_size_and_liquidity_skips(self):
        st = putbook.new_state()
        q = {"chains": {"SPY": [row(730, -0.3, 3.37, 3.40)], "AAPL": [row(325, -0.3, 4.0, 5.0)]}}
        putbook.apply(st, BARS, q, D)
        reasons = {x["symbol"]: x["reason"] for x in st["log"] if x["kind"] == "put_skip"}
        self.assertEqual(reasons, {"SPY": "size", "AAPL": "no liquid contract in range"})
        self.assertEqual(st["positions"], {})

    def test_idempotent_per_day(self):
        st = putbook.new_state()
        q = {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9)]}}
        putbook.apply(st, BARS, q, D)
        self.assertEqual(putbook.apply(st, BARS, q, D), {"skipped": "already applied today"})
        self.assertEqual(len(st["positions"]), 1)

    def test_target_exit_buys_back_at_ask(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9, iid="x")]}}, D)
        putbook.apply(st, BARS, {"marks": {"x": {"bid": 2.0, "ask": 2.2}}}, date(2026, 9, 29))
        c = st["closed"][0]
        self.assertEqual(c["why"], "target")
        self.assertAlmostEqual(c["pnl"], 454.97 - 220.03, places=2)

    def test_stop_exit(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9, iid="x")]}}, D)
        putbook.apply(st, BARS, {"marks": {"x": {"bid": 13.5, "ask": 13.8}}}, date(2026, 9, 29))
        self.assertEqual(st["closed"][0]["why"], "stop")

    def test_expiry_settles_at_intrinsic(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9, exp="2026-10-30", iid="x")]}}, D)
        st["positions"]["AAPL"]["sessions"] = -99  # keep it open to expiry
        bars = {"AAPL": {"last": "2026-11-02", "closes": trend(start=280)[:-1] + [320.0]}}
        putbook.apply(st, bars, {}, date(2026, 11, 2))
        c = st["closed"][0]
        self.assertEqual((c["why"], c["buyback"]), ("expiry", 500.0))


if __name__ == "__main__":
    unittest.main()
