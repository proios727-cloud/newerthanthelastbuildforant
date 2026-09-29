import math
import unittest
from datetime import date, datetime, timezone

import judge
from fund import battery, trendbook

T0 = int(datetime(2026, 5, 23, tzinfo=timezone.utc).timestamp())
NOW = datetime(2026, 9, 29, 20, 40, tzinfo=timezone.utc).timestamp()
TODAY = date(2026, 9, 29)


def series(n=130, start=100.0, drift=0.004, wiggle=0.05):
    return [start * math.exp(drift * i + wiggle * math.sin(i)) for i in range(n)]


def raw(**over):
    out = {}
    for a in trendbook.ASSETS:
        cs = over.get(a, series())
        out[a] = [[T0 + 86400 * i, c] for i, c in enumerate(cs)]
    return out


Q = {"IBIT": {"bid": 50.0, "ask": 50.02}, "ETHA": {"bid": 20.0, "ask": 20.02}, "BSOL": {"bid": 30.0, "ask": 30.02}}


def fresh(**over):
    st = trendbook.new_state()
    trendbook.ingest(st, raw(**over), now=NOW)
    return st


class TrendBookTests(unittest.TestCase):
    def test_ingest_drops_the_unfinished_bar(self):
        st = trendbook.new_state()
        r = raw()
        r["BTC"].append([int(NOW) - 3600, 999.0])          # today's candle, still open
        trendbook.ingest(st, r, now=NOW)
        self.assertNotEqual(st["bars"]["BTC"]["closes"][-1], 999.0)
        self.assertEqual(st["bars"]["BTC"]["last"], "2026-09-28")   # the 9/29 candle is still open at 20:40 UTC

    def test_uptrend_buys_vol_targeted_sleeves_at_the_ask(self):
        st = fresh()
        out = trendbook.apply(st, Q, TODAY)
        self.assertEqual({e["etf"] for e in out["events"]}, {"IBIT", "ETHA", "BSOL"})
        b = st["books"]["b500"]
        ibit = next(e for e in out["events"] if e["etf"] == "IBIT" and e["book"] == "b500")
        self.assertEqual((ibit["side"], ibit["fill_px"]), ("buy", 50.02))
        self.assertAlmostEqual(b["shares"]["IBIT"] * 50.02, out["targets"]["BTC"] * 500, places=2)
        self.assertLessEqual(out["targets"]["BTC"], 0.5)
        self.assertGreater(b["cash"], 0)
        self.assertEqual(trendbook.apply(st, Q, TODAY), {"skipped": "already applied today"})

    def test_downtrend_stays_flat_and_crossed_quotes_never_trade(self):
        st = fresh(BTC=series(drift=-0.004), ETH=series(drift=-0.004), SOL=series(drift=-0.004))
        self.assertEqual(trendbook.apply(st, Q, TODAY)["events"], [])
        st = fresh()
        bad = {**Q, "IBIT": {"bid": 50.1, "ask": 50.0}}
        out = trendbook.apply(st, bad, TODAY)
        self.assertNotIn("IBIT", {e["etf"] for e in out["events"]})
        self.assertTrue(any(x.get("reason") == "no, zero or crossed quote" for x in st["books"]["b500"]["log"]))

    def test_stale_bars_do_not_trade(self):
        st = fresh()
        out = trendbook.apply(st, Q, date(2026, 10, 9))
        self.assertEqual((out["events"], out["stale"]), ([], ["BTC", "ETH", "SOL"]))

    def test_jev_can_veto_buys_but_exits_bypass_it(self):
        st = fresh()
        calls = []
        veto = lambda a, o: calls.append(o["side"]) or {"veto": ("data_error", "p=0.9"), "answers": {}, "mode": "live"}
        out = trendbook.apply(st, Q, TODAY, judge_fn=veto)
        self.assertEqual(out["events"], [])
        st = fresh()
        trendbook.apply(st, Q, TODAY)
        st["signal"]["BTC"]["on"] = True
        down = series()[:-3] + [series()[-4] * 0.7] * 3        # trailing stop: 30% below peak
        trendbook.ingest(st, raw(BTC=down), now=NOW + 86400)
        st["last_signal_bar"] = None
        calls.clear()
        out = trendbook.apply(st, Q, date(2026, 9, 30), judge_fn=veto)
        sells = [e for e in out["events"] if e["etf"] == "IBIT"]
        self.assertTrue(sells and all(e["side"] == "sell" for e in sells))
        self.assertNotIn("sell", calls)
        self.assertEqual(st["signal"]["BTC"].get("exit_reason"), "trailing stop")

    def test_kill_switch_blocks_buys_and_drawdown_kills_the_book(self):
        st = fresh()
        self.assertEqual(trendbook.apply(st, Q, TODAY, kill="test")["events"], [])
        st = fresh()
        trendbook.apply(st, Q, TODAY)
        crash = {k: {"bid": v["bid"] * 0.4, "ask": v["ask"] * 0.4} for k, v in Q.items()}
        out = trendbook.apply(st, crash, date(2026, 9, 30))
        self.assertIn("20% below peak", out["kill"])
        self.assertEqual(st["books"]["b500"]["shares"], {})
        self.assertTrue(all(e["why"] == "kill" for e in out["events"]))

    def test_trend_battery_vetoes_only_live_answers(self):
        stub = battery.trend_verdict(battery.assess_trend(judge.StubClient(), "BTC", {"side": "buy"}))
        self.assertIsNone(stub["veto"])
        live = {"data_error": judge.Answer(False, 0.1, live=True),
                "event": judge.Answer("crypto_structural", 0.6, {"crypto_structural": 0.6}, live=True),
                "order_mistake": judge.Answer(False, 0.05, live=True)}
        self.assertEqual(battery.trend_verdict(live)["veto"][0], "crypto_structural")


if __name__ == "__main__":
    unittest.main()
