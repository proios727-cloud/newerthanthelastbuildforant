import unittest

from kalshi import calibration

M = {"ticker": "KXBTC15M-26SEP281815-15", "open_time": "2026-09-28T22:00:00Z",
     "close_time": "2026-09-28T22:15:00Z", "result": "yes"}
CLOSE = calibration._ts(M["close_time"])


def candle(end, yes_bid, yes_ask):
    return {"end_period_ts": end, "yes_bid": {"close_dollars": yes_bid}, "yes_ask": {"close_dollars": yes_ask}}


def fake(path, params):
    assert path.endswith("/candlesticks") and params["period_interval"] == 1
    return {"candlesticks": [candle(CLOSE - 180, "0.9000", "0.9100"), candle(CLOSE - 60, "0.0500", "0.0600")]}


class CalibrationTests(unittest.TestCase):
    def test_snapshot_picks_favourite_side_and_outcome(self):
        s = calibration.snapshot(M, 3, fake)
        self.assertEqual((s["side"], s["ask"], s["won"]), ("yes", 91, True))
        s = calibration.snapshot(M, 1, fake)          # NO is the favourite: ask = 100 − yes bid
        self.assertEqual((s["side"], s["ask"], s["won"]), ("no", 95, False))
        self.assertIsNone(calibration.snapshot(M, 2, fake))

    def test_summary_charges_ask_and_fee(self):
        rows = [{"ask": 92, "won": True}] * 9 + [{"ask": 92, "won": False}]
        b = [s for s in calibration.summarize(rows) if s["bucket"] == "90-95"][0]
        # win: 100−92−1 = 7¢, loss: −92−1 = −93¢ → mean (9·7 − 93)/10 = −3.0
        self.assertEqual((b["n"], b["hit"], b["ev_c"], b["worst_c"]), (10, 0.9, -3.0, -93))

    def test_settled_markets_skips_unresolved(self):
        f = lambda p, q: {"markets": [M, {"ticker": "x", "result": ""}], "cursor": ""}
        self.assertEqual(len(calibration.settled_markets("KXBTC15M", 5, f)), 1)


if __name__ == "__main__":
    unittest.main()
