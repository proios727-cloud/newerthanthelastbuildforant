import unittest
from datetime import date

from fund import spreadbook

from tests.test_putbook import BARS, D, row


def chain():
    # AAPL, Oct 30 expiry: 325 short (~0.28 delta), longs at 324 / 322.5 / 320
    return [row(325, -0.28, 4.55, 4.75, iid="s325"), row(324, -0.26, 4.20, 4.35, iid="l324"),
            row(322.5, -0.24, 3.70, 3.85, iid="l322"), row(320, -0.21, 3.10, 3.25, iid="l320")]


class SpreadBookTests(unittest.TestCase):
    def test_entry_picks_best_return_on_risk_inside_room(self):
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        p = st["positions"]["AAPL"]
        # 2.5- and 5-wide are over MAX_WIDTH; 325/324 (credit .20 = 20% of width, risk ~$80) fits the $100 room
        self.assertEqual((p["short_strike"], p["long_strike"], p["contracts"]), (325, 324, 1))
        self.assertAlmostEqual(p["credit"], 20 - 0.06, places=2)
        self.assertLessEqual(p["max_loss"], 0.2 * 500)

    def test_falls_back_to_next_short_when_nearest_has_no_partner(self):
        st = spreadbook.new_state()
        # 0.30-delta 330 has no long within $2; 0.26-delta 324 pairs with 323
        q = {"chains": {"AAPL": [row(330, -0.30, 6.0, 6.2, iid="s330"), row(324, -0.26, 4.20, 4.35, iid="s324"),
                                 row(323, -0.24, 3.80, 3.95, iid="l323"), row(310, -0.10, 1.0, 1.05)]}}
        spreadbook.apply(st, BARS, q, D)
        p = st["positions"]["AAPL"]
        self.assertEqual((p["short_strike"], p["long_strike"]), (324, 323))

    def test_short_outside_delta_band_is_never_sold(self):
        st = spreadbook.new_state()
        q = {"chains": {"AAPL": [row(340, -0.45, 9.0, 9.2), row(339, -0.43, 8.5, 8.7)]}}
        spreadbook.apply(st, BARS, q, D)
        self.assertEqual(st["positions"], {})

    def test_one_spread_at_a_time(self):
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain(), "TSLA": chain()}}, D)
        self.assertEqual(len(st["positions"]), 1)

    def test_no_spread_when_credit_too_thin(self):
        st = spreadbook.new_state()
        q = {"chains": {"AAPL": [row(325, -0.28, 1.00, 1.05), row(320, -0.21, 0.95, 1.00)]}}
        spreadbook.apply(st, BARS, q, D)
        self.assertEqual(st["positions"], {})
        self.assertEqual(st["log"][-1]["kind"], "spread_skip")

    def test_target_exit_and_earnings_exit(self):
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        spreadbook.apply(st, BARS, {"marks": {"s325": {"bid": 2.0, "ask": 2.1}, "l324": {"bid": 2.0, "ask": 2.05}}},
                         date(2026, 9, 29))
        c = st["closed"][0]
        self.assertEqual(c["why"], "target")          # debit .10 <= 50% of .20
        self.assertAlmostEqual(c["pnl"], 19.94 - 10.06, places=2)

        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        marks = {"s325": {"bid": 4.5, "ask": 4.6}, "l324": {"bid": 4.2, "ask": 4.3}}
        spreadbook.apply(st, BARS, {"marks": marks, "events": {"AAPL": {"earnings_date": "2026-10-01"}}}, date(2026, 9, 30))
        self.assertEqual(st["closed"][0]["why"], "earnings")

    def test_expiry_settles_at_spread_intrinsic(self):
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        bars = {"AAPL": {"last": "2026-10-30", "closes": [321.0]}}
        st["positions"]["AAPL"]["sessions"] = 0
        spreadbook.apply(st, bars, {}, date(2026, 10, 30))
        c = st["closed"][0]
        self.assertEqual(c["why"], "expiry")
        self.assertAlmostEqual(c["buyback"], 400 - 300, places=2)   # 325-321 short, 324-321 long

    def test_final_pass_blocks_and_jev_veto(self):
        st = spreadbook.new_state()
        q = {"chains": {"AAPL": chain()}, "events": {"AAPL": {"earnings_date": "2026-10-15"}}}
        spreadbook.apply(st, BARS, q, D)
        self.assertEqual(st["log"][-1]["reason"], "earnings before planned exit")
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D, judge_fn=lambda s, h, c=None: ("news_catalyst", "p=0.9"))
        self.assertEqual(next(x for x in st["log"] if x["kind"] == "spread_skip")["reason"], "jev news_catalyst")
        self.assertEqual(st["positions"], {})

    def test_vetoed_spread_is_a_ghost_with_no_cash_or_risk(self):
        st = spreadbook.new_state()
        veto = {"veto": ("news_catalyst", "p=0.9"), "p": 0.9, "mode": "live"}
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D, judge_fn=lambda s, h, c=None: veto)
        self.assertEqual((st["cash"], spreadbook.reserved(st)), (500.0, 0))
        self.assertEqual({x["instrument_id"] for x in spreadbook.open_legs(st)}, {"s325", "l324"})
        marks = {"s325": {"bid": 2.0, "ask": 2.1}, "l324": {"bid": 2.0, "ask": 2.05}}
        spreadbook.apply(st, BARS, {"marks": marks}, date(2026, 9, 29))
        g = st["ghost_closed"][0]
        self.assertEqual((g["why"], g["jev_p"]), ("target", 0.9))
        self.assertEqual(st["closed"], [])

    def test_idempotent_and_legs_listed(self):
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        self.assertEqual(spreadbook.apply(st, BARS, {}, D), {"skipped": "already applied today"})
        self.assertEqual({x["instrument_id"] for x in spreadbook.open_legs(st)}, {"s325", "l324"})


if __name__ == "__main__":
    unittest.main()
