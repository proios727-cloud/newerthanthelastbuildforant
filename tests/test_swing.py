import unittest

from options import swing as S


def chain(spot=50.0, expiry="2026-12-18", calls=None):
    calls = calls or [
        {"strike": 50.0, "delta": 0.52, "bid": 1.90, "ask": 1.98, "oi": 900, "iv": 0.30},
        {"strike": 51.0, "delta": 0.46, "bid": 1.50, "ask": 1.56, "oi": 800, "iv": 0.30},
        {"strike": 53.0, "delta": 0.33, "bid": 0.90, "ask": 0.95, "oi": 100, "iv": 0.30},
    ]
    cs = [dict(c, type="call", expiry=expiry) for c in calls]
    cs.append({"strike": 50.0, "type": "put", "expiry": expiry, "delta": -0.48, "bid": 1.8, "ask": 1.9, "oi": 500,
               "iv": 0.30})
    return {"spot": spot, "contracts": cs, "asof": "2026-11-12T16:00:00Z"}


def uptrend(n=80, start=40.0, step=0.12, wiggle=0.9):
    # rising closes with alternating noise so realized vol is well above 0
    return [start + step * i + (wiggle if i % 2 else -wiggle) for i in range(n)]


class SwingTests(unittest.TestCase):
    def test_pick_expiry_closest_to_30(self):
        self.assertEqual(S.pick_expiry(["2026-12-04", "2026-12-18"], "2026-11-12"), "2026-12-18")
        self.assertEqual(S.pick_expiry(["2026-12-11", "2026-12-18"], "2026-11-12"), "2026-12-18")  # weekly skipped
        self.assertTrue(S.is_monthly("2026-12-18"))
        self.assertFalse(S.is_monthly("2026-12-11"))
        self.assertIsNone(S.pick_expiry(["2026-11-14"], "2026-11-12"))

    def test_pass_picks_delta_nearest_045_under_budget(self):
        closes = uptrend()
        r = S.screen_call("XYZ", chain(spot=closes[-1]), closes, None, "2026-11-12")
        self.assertEqual(r["status"], "pass", r["reason"])
        self.assertEqual(r["strike"], 51.0)  # 0.46 delta; the 53 fails OI
        self.assertEqual(r["cost"], 156.0)
        self.assertEqual(r["take_profit_at"], round(1.56 * 1.6, 2))
        self.assertEqual(r["stop_at"], 0.78)
        self.assertEqual(r["time_exit"], "2026-12-08")

    def test_fails_downtrend(self):
        closes = list(reversed(uptrend()))
        r = S.screen_call("XYZ", chain(spot=closes[-1]), closes, None, "2026-11-12")
        self.assertEqual(r["status"], "fail")
        self.assertIn("uptrend", r["reason"])

    def test_fails_earnings_and_expensive_iv(self):
        closes = uptrend()
        r = S.screen_call("XYZ", chain(spot=closes[-1]), closes, "2026-12-01", "2026-11-12")
        self.assertIn("earnings", r["reason"])
        rich = chain(spot=closes[-1], calls=[{"strike": 51.0, "delta": 0.46, "bid": 1.5, "ask": 1.56, "oi": 800,
                                               "iv": 3.0}])
        for c in rich["contracts"]:
            c["iv"] = 3.0
        r = S.screen_call("XYZ", rich, closes, None, "2026-11-12")
        self.assertIn("not cheap", r["reason"])

    def test_budget_excludes_expensive_calls(self):
        closes = uptrend()
        ch = chain(spot=closes[-1], calls=[{"strike": 50.0, "delta": 0.45, "bid": 2.4, "ask": 2.5, "oi": 900,
                                             "iv": 0.30}])
        r = S.screen_call("XYZ", ch, closes, None, "2026-11-12")
        self.assertIn("no call fits", r["reason"])

    def test_rank_and_exit_check(self):
        rs = S.rank([{"ticker": "A", "status": "pass", "score": 1.0}, {"ticker": "B", "status": "pass", "score": 3.0},
                     {"ticker": "C", "status": "pass", "score": 2.0}, {"ticker": "D", "status": "fail"}])
        self.assertEqual([(r["ticker"], r["rank"]) for r in rs], [("B", 1), ("C", 2), ("A", None), ("D", None)])
        p = {"take_profit_at": 2.5, "stop_at": 0.78, "time_exit": "2026-12-08"}
        self.assertIn("take profit", S.exit_check(p, 2.6, "2026-11-20"))
        self.assertIn("stop", S.exit_check(p, 0.7, "2026-11-20"))
        self.assertIn("time exit", S.exit_check(p, 1.5, "2026-12-08"))
        self.assertIsNone(S.exit_check(p, 1.5, "2026-11-20"))

    def test_open_picks(self):
        rows = [{"id": "a"}, {"id": "b"}, {"close_of": "a"}]
        self.assertEqual([r["id"] for r in S.open_picks(rows)], ["b"])


if __name__ == "__main__":
    unittest.main()
