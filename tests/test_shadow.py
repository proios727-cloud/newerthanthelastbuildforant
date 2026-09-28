import unittest
from datetime import datetime, timezone

from fund import shadow
from tests.test_fund import cfg


def trend(n=60, start=100.0, step=0.5):
    return [start + i * step for i in range(n)]


def bars(sym_closes, last="2026-09-24"):
    return {s: {"source": "test", "last": last, "closes": c} for s, c in sym_closes.items()}


class SignalTests(unittest.TestCase):
    def test_uptrend_is_momentum_and_breakout(self):
        names = [s for s, _ in shadow.signals(trend())]
        self.assertIn("momentum", names)
        self.assertIn("breakout", names)

    def test_downtrend_has_no_long_signal(self):
        self.assertEqual(shadow.signals(trend(step=-0.5)), [])

    def test_dip_in_uptrend_is_mean_reversion(self):
        c = trend()[:-2] + [128.0, 120.0]  # two down closes, still above SMA50
        self.assertIn("mean_reversion", [s for s, _ in shadow.signals(c)])

    def test_needs_history(self):
        self.assertEqual(shadow.signals(trend(n=40)), [])

    def test_stop_below_target_above(self):
        c = [100 + (i % 3) + i * 0.4 for i in range(60)]
        row = shadow.scan(bars({"SPY": c}))[0]
        self.assertLess(row["stop"], row["close"])
        self.assertGreater(row["target"], row["close"])


class ShadowBookTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg()

    def test_enters_within_caps_and_is_idempotent(self):
        sh = shadow.Shadow.new(self.cfg)
        b = bars({"SPY": trend(start=700), "NVDA": trend(start=200)})
        evs = sh.step(b, self.cfg)
        fills = [e for e in evs if e["kind"] == "shadow_fill"]
        self.assertEqual({e["symbol"] for e in fills}, {"SPY", "NVDA"})
        L = sh.ledger
        for s in ("SPY", "NVDA"):
            self.assertLessEqual(abs(L.market_value(s)), 0.05 * L.nav() + 1e-6)
        self.assertEqual(sh.step(b, self.cfg), [])  # same bars: nothing new

    def test_stop_exit(self):
        sh = shadow.Shadow.new(self.cfg)
        c = trend(start=700)
        sh.step(bars({"SPY": c}), self.cfg)
        stop = sh.meta["SPY"]["stop"]
        evs = sh.step(bars({"SPY": c + [stop - 1]}, last="2026-09-25"), self.cfg)
        self.assertEqual(evs[0]["kind"], "shadow_exit")
        self.assertEqual(evs[0]["why"], "stop")
        self.assertEqual(sh.ledger.qty("SPY"), 0)
        self.assertEqual(sh.summary()["closed_trades"], 1)

    def test_time_exit(self):
        sh = shadow.Shadow.new(self.cfg)
        c = trend(start=700, step=0.01)
        sh.step(bars({"SPY": trend(start=700)}), self.cfg)
        m = sh.meta["SPY"]
        m["stop"], m["target"] = 0, 1e9
        why = None
        for i, d in enumerate(["2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]):
            evs = sh.step(bars({"SPY": c + [c[-1]] * (i + 1)}, last=d), self.cfg)
            why = next((e["why"] for e in evs if e["kind"] == "shadow_exit"), why)
        self.assertEqual(why, "time")

    def test_group_cap_vetoes_extra_crypto(self):
        sh = shadow.Shadow.new(self.cfg)
        b = bars({"BTC/USD": trend(start=60000, step=300), "ETH/USD": trend(start=2000, step=10),
                  "SOL/USD": trend(start=80, step=0.5)})
        evs = sh.step(b, self.cfg)
        gross_crypto = sum(abs(sh.ledger.market_value(s)) for s in ("BTC/USD", "ETH/USD", "SOL/USD"))
        self.assertLessEqual(gross_crypto, 0.20 * sh.ledger.nav() + 1e-6)
        self.assertTrue(all(e["kind"] in ("shadow_fill", "shadow_veto") for e in evs))

    def test_roundtrip(self):
        sh = shadow.Shadow.new(self.cfg)
        sh.step(bars({"SPY": trend(start=700)}), self.cfg)
        again = shadow.Shadow.from_dict(sh.to_dict())
        self.assertEqual(again.summary(), sh.summary())


class AppendTests(unittest.TestCase):
    def test_appends_only_completed_newer_bars(self):
        c = cfg()
        b = bars({"SPY": trend(), "BTC/USD": trend()}, last="2026-09-24")
        now = datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)  # 17:00 ET Fri
        t = lambda y, m, d, h, mi=0: int(datetime(y, m, d, h, mi, tzinfo=timezone.utc).timestamp())
        raw = {"SPY": [[t(2026, 9, 24, 13, 30), 1.0], [t(2026, 9, 25, 13, 30), 130.0]],
               "BTC/USD": [[t(2026, 9, 24, 0), 1.0], [t(2026, 9, 25, 0), 131.0]]}
        added = shadow.append_bars(b, c, raw, now)
        self.assertEqual(added, {"SPY": ["2026-09-25"]})  # BTC 09-25 bar still open at 21:00 UTC
        self.assertEqual(b["SPY"]["closes"][-1], 130.0)
        self.assertEqual(b["BTC/USD"]["last"], "2026-09-24")


if __name__ == "__main__":
    unittest.main()


class VariantAndCostTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg()

    def test_scan_only_filters_signal_type(self):
        b = bars({"SPY": trend(start=700)})
        self.assertTrue(shadow.scan(b, "momentum"))
        self.assertEqual(shadow.scan(b, "mean_reversion"), [])

    def test_variant_roundtrip_keeps_filter(self):
        sh = shadow.Shadow.new(self.cfg, "breakout")
        self.assertEqual(shadow.Shadow.from_dict(sh.to_dict()).only, "breakout")

    def test_half_spread_is_charged(self):
        sh = shadow.Shadow.new(self.cfg)
        ev = sh.step(bars({"SPY": trend(start=700)}), self.cfg, quotes={"SPY": {"spread_bps": 20.0}})
        f = ev[0]
        self.assertAlmostEqual(f["cost"], round(f["qty"] * f["price"] * 10 / 1e4, 2))

    def test_wide_crypto_quote_is_vetoed(self):
        sh = shadow.Shadow.new(self.cfg)
        ev = sh.step(bars({"BTC/USD": trend(start=60000, step=300)}), self.cfg,
                     quotes={"BTC/USD": {"spread_bps": 50.0}})
        self.assertEqual(ev[0]["kind"], "shadow_veto")
        self.assertEqual(ev[0]["rule"], "spread")

    def test_wide_equity_quote_only_costs(self):
        # after-hours equity quotes price costs but never veto a close fill
        sh = shadow.Shadow.new(self.cfg)
        ev = sh.step(bars({"SPY": trend(start=700)}), self.cfg, quotes={"SPY": {"spread_bps": 50.0}})
        self.assertEqual(ev[0]["kind"], "shadow_fill")

    def test_spread_bps_rejects_crossed(self):
        self.assertIsNone(shadow.spread_bps(101.0, 100.0))
        self.assertAlmostEqual(shadow.spread_bps(99.95, 100.05), 10.0)
