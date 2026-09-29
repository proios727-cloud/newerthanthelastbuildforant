import json
import os
import tempfile
import unittest

from kalshi import shadow

# YES bids up to 30¢, NO bids up to 68¢ → YES ask 32¢, NO ask 70¢ (NO is the favourite).
BOOK = {"orderbook_fp": {"yes_dollars": [["0.2900", "50"], ["0.3000", "4"]],
                         "no_dollars": [["0.6700", "100"], ["0.6800", "5"]]}}


class ShadowTests(unittest.TestCase):
    def test_book_walk_prices_the_opposite_bids(self):
        self.assertEqual(shadow.book_side(BOOK, "no", 10), (70.0, 4.0, 70.6))   # 4 @70 + 6 @71
        self.assertEqual(shadow.book_side(BOOK, "yes", 5), (32.0, 5.0, 32.0))
        self.assertEqual(shadow.book_side(BOOK, "no", 1000)[2], None)           # book too thin

    def test_decide_applies_rule_b(self):
        d = shadow.decide(BOOK, 10)
        self.assertEqual((d["take"], d["side"], d["ask"], d["book_avg"]), (True, "no", 70.0, 70.6))
        heavy = {"orderbook_fp": {"yes_dollars": [["0.0200", "9"]], "no_dollars": [["0.0300", "9"]]}}
        self.assertFalse(shadow.decide(heavy, 1)["take"])                        # 98¢ favourite: outside range
        self.assertFalse(shadow.decide({"orderbook_fp": {}}, 1)["take"])

    def test_settle_uses_fees_on_both_prices(self):
        rec = {"ticker": "X", "side": "no", "qty": 10, "book_avg": 70.6}
        s = shadow.settle(rec, "no", 70)
        self.assertEqual(s["pnl_book_c"], 29 * 10 - 15)   # 71¢ fill, fee ceil(.07·10·.71·.29·100)=15
        self.assertEqual(s["pnl_vwap_c"], 30 * 10 - 15)
        self.assertEqual(shadow.settle(rec, "yes", None)["pnl_vwap_c"], None)

    def test_run_logs_one_decision_per_market_and_settles(self):
        close = 1_790_000_100 - 1_790_000_100 % 900 + 900
        now = [close - 120.0]
        markets = {s: {"ticker": f"{s}-T", "close_time": "x"} for s in shadow.SERIES}
        trades = {"trades": [{"taker_side": "no", "no_price_dollars": "0.7000", "yes_price_dollars": "0.3000",
                              "count_fp": "50"}]}

        def fetch(path, params):
            if path == "/markets":
                m = markets[params["series_ticker"]]
                return {"markets": [{**m, "close_time": _iso(close)}]}
            if path.endswith("/orderbook"):
                return BOOK
            if path == "/markets/trades":
                return trades
            return {"market": {"result": "no"}}

        def sleep(s):
            now[0] += max(s, 1)

        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "s.jsonl")
            shadow.run(0.02, log, 10, fetch=fetch, clock=lambda: now[0], sleep=sleep)
            with open(log) as f:
                rows = [json.loads(line) for line in f]
            self.assertEqual({r["ticker"] for r in rows}, {"KXBTC15M-T", "KXETH15M-T"})
            self.assertTrue(all(r["won"] and r["secs_before_close"] == 60 for r in rows))
            # Same book on both → one trade kept, the other settled as a logged alternate.
            self.assertEqual(sorted((r["take"], bool(r.get("alt"))) for r in rows), [(False, True), (True, False)])
            self.assertIn("1 settled trades", shadow.report(log))

    def test_one_per_window_keeps_the_higher_priced_favourite(self):
        recs = [{"ticker": "BTC", "take": True, "ask": 84.0}, {"ticker": "ETH", "take": True, "ask": 91.0},
                {"ticker": "X", "take": False, "ask": 99.0}]
        shadow.one_per_window(recs)
        self.assertEqual([r["take"] for r in recs], [False, True, False])
        self.assertTrue(recs[0]["alt"] and "kept ETH" in recs[0]["why"])
        self.assertNotIn("alt", recs[2])


class ExitTests(unittest.TestCase):
    def test_exit_rules(self):
        ex = {"tp": 6, "sl": 20, "trail": 5, "arm": 3}
        self.assertTrue(shadow.exit_hit(80, 86, 86, ex))       # take profit
        self.assertTrue(shadow.exit_hit(80, 80, 60, ex))       # stop loss
        self.assertTrue(shadow.exit_hit(80, 84, 79, ex))       # trailed 5 below an armed peak
        self.assertFalse(shadow.exit_hit(80, 82, 78, ex))      # peak never armed (+2 < +3)
        self.assertFalse(shadow.exit_hit(80, 90, 90, {"tp": None, "sl": None, "trail": None}))

    def test_exit_pnl_pays_fees_both_ways(self):
        # buy 80, sell 86, 10 contracts: +60¢ − ceil(.07·10·.8·.2·100)=12 − ceil(.07·10·.86·.14·100)=9
        self.assertEqual(shadow.exit_pnl_c(80, 86, 10), 60 - 12 - 9)

    def test_watch_exit_sells_on_trigger_and_settle_keeps_hold_pnl(self):
        bids = iter([81, 83, 88, 70])
        now = [1000.0]

        def fetch(path, params):
            return {"orderbook_fp": {"yes_dollars": [[f"{next(bids) / 100:.4f}", "50"]], "no_dollars": []}}

        rec = {"ticker": "T", "side": "yes", "book_avg": 80.0, "qty": 10}
        shadow.watch_exit(rec, 1060, fetch, lambda: now[0], lambda s: now.__setitem__(0, now[0] + s),
                          {"tp": 6, "sl": None, "trail": None})
        self.assertEqual((rec["exit_price"], rec["exit_secs_before_close"]), (88.0, 54.0))
        done = shadow.settle(rec, "no", None)                  # lost at settlement, but sold first
        self.assertEqual(done["pnl_book_c"], shadow.exit_pnl_c(80, 88, 10))
        self.assertEqual(done["pnl_hold_c"], shadow.pnl_c(80, False, 10))


def _iso(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    unittest.main()
