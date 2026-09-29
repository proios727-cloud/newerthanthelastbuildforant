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
        # 325/320 would risk ~$370 > $250 room; 325/322.5 (credit .70, risk ~$180) beats 325/324 (credit .20 = 20%, risk ~$80)
        self.assertEqual((p["short_strike"], p["long_strike"], p["contracts"]), (325, 322.5, 1))
        self.assertAlmostEqual(p["credit"], 70 - 0.06, places=2)
        self.assertLessEqual(p["max_loss"], 0.5 * 500)
        self.assertAlmostEqual(st["cash"], 500 + 69.94, places=2)

    def test_no_spread_when_credit_too_thin(self):
        st = spreadbook.new_state()
        q = {"chains": {"AAPL": [row(325, -0.28, 1.00, 1.05), row(320, -0.21, 0.95, 1.00)]}}
        spreadbook.apply(st, BARS, q, D)
        self.assertEqual(st["positions"], {})
        self.assertEqual(st["log"][-1]["kind"], "spread_skip")

    def test_target_exit_and_earnings_exit(self):
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        spreadbook.apply(st, BARS, {"marks": {"s325": {"bid": 2.0, "ask": 2.1}, "l322": {"bid": 1.8, "ask": 1.9}}},
                         date(2026, 9, 29))
        c = st["closed"][0]
        self.assertEqual(c["why"], "target")          # debit .30 <= 50% of .70
        self.assertAlmostEqual(c["pnl"], 69.94 - 30.06, places=2)

        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        marks = {"s325": {"bid": 4.5, "ask": 4.7}, "l322": {"bid": 3.6, "ask": 3.8}}
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
        self.assertAlmostEqual(c["buyback"], 400 - 150, places=2)   # 325-321 short, 322.5-321 long

    def test_final_pass_blocks_and_jev_veto(self):
        st = spreadbook.new_state()
        q = {"chains": {"AAPL": chain()}, "events": {"AAPL": {"earnings_date": "2026-10-15"}}}
        spreadbook.apply(st, BARS, q, D)
        self.assertEqual(st["log"][-1]["reason"], "earnings before planned exit")
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D, judge_fn=lambda s, h: ("news_catalyst", "p=0.9"))
        self.assertEqual(st["log"][-1]["reason"], "jev news_catalyst")

    def test_idempotent_and_legs_listed(self):
        st = spreadbook.new_state()
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D)
        self.assertEqual(spreadbook.apply(st, BARS, {}, D), {"skipped": "already applied today"})
        self.assertEqual({x["instrument_id"] for x in spreadbook.open_legs(st)}, {"s325", "l322"})


if __name__ == "__main__":
    unittest.main()
