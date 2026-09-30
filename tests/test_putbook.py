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


class FinalPassTests(unittest.TestCase):
    def q(self, **events):
        return {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9)]}, "events": {"AAPL": events}}

    def test_earnings_before_planned_exit_blocks(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, self.q(earnings_date="2026-10-15"), D)
        self.assertEqual(st["positions"], {})
        self.assertEqual(st["log"][-1]["reason"], "earnings before planned exit")

    def test_earnings_after_planned_exit_allows(self):
        # 2026-09-28 entry: planned exit 2026-10-19 (21 days) < 2026-10-23 (7 days before expiry)
        st = putbook.new_state()
        putbook.apply(st, BARS, self.q(earnings_date="2026-10-29"), D)
        self.assertIn("AAPL", st["positions"])

    def test_open_put_closed_session_before_earnings(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9, iid="x")]}}, D)
        putbook.apply(st, BARS, {"marks": {"x": {"bid": 4.0, "ask": 4.2}},
                                 "events": {"AAPL": {"earnings_date": "2026-10-02"}}}, date(2026, 10, 1))
        self.assertEqual(st["closed"][0]["why"], "earnings")

    def test_jev_veto_blocks(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, self.q(headlines=["AAPL halted"]), D,
                      judge_fn=lambda s, h, c=None: ("news_catalyst", "material p=0.93"))
        self.assertEqual(st["positions"], {})
        skip = next(x for x in st["log"] if x["kind"] == "put_skip")
        self.assertEqual(skip["reason"], "jev news_catalyst")
        self.assertAlmostEqual(st["cash"], putbook.START_NAV)          # the vetoed sale moved no cash

    def test_vetoed_sale_is_tracked_as_ghost_through_the_same_exits(self):
        st = putbook.new_state()
        veto = {"veto": ("news_catalyst", "p=0.93"), "p": 0.93, "mode": "live"}
        putbook.apply(st, BARS, self.q(headlines=["AAPL halted"]), D, judge_fn=lambda s, h, c=None: veto)
        self.assertIn("AAPL", st["ghosts"])
        plan = putbook.plan(st, BARS, date(2026, 9, 29))
        self.assertIn(st["ghosts"]["AAPL"]["instrument_id"], [x["instrument_id"] for x in plan["open"]])
        iid = st["ghosts"]["AAPL"]["instrument_id"]
        putbook.apply(st, BARS, {"marks": {iid: {"bid": 13.0, "ask": 14.0}}}, date(2026, 9, 29))
        g = st["ghost_closed"][0]
        self.assertEqual((g["why"], g["jev_p"], g["jev_mode"]), ("stop", 0.93, "live"))
        self.assertLess(g["pnl"], 0)
        self.assertAlmostEqual(st["cash"], putbook.START_NAV)          # ghosts never touch cash
        self.assertEqual(st["closed"], [])

    def test_outage_veto_is_not_a_ghost_and_taken_trades_keep_the_verdict(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, self.q(), D,
                      judge_fn=lambda s, h, c=None: {"veto": ("unavailable", "timeout"), "p": None, "mode": "error"})
        self.assertEqual(st.get("ghosts", {}), {})
        st = putbook.new_state()
        putbook.apply(st, BARS, self.q(), D, judge_fn=lambda s, h, c=None: {"veto": None, "p": 0.12, "mode": "live"})
        self.assertEqual((st["positions"]["AAPL"]["jev_p"], st["positions"]["AAPL"]["jev_mode"]), (0.12, "live"))

    def test_stub_jev_never_vetoes(self):
        import judge
        from fund import catalyst
        client = judge.StubClient()
        st = putbook.new_state()
        putbook.apply(st, BARS, self.q(headlines=["AAPL beats estimates"]), D,
                      judge_fn=lambda s, h, c=None: catalyst.veto(catalyst.assess(client, s, h)))
        self.assertIn("AAPL", st["positions"])
