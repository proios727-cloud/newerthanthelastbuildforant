import importlib.util
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backtest"))
spec = importlib.util.spec_from_file_location("olab", ROOT / "backtest" / "options_lab.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

DAYS, PX, VIX = lab.load()


class OptionsLabTests(unittest.TestCase):
    def test_vix_calendar_join(self):
        self.assertEqual(len(VIX), len(DAYS))
        self.assertEqual(VIX[-1], 16.07)

    def test_calibration_matches_live_spy(self):
        v = lab.Vol(PX, VIX)
        i = len(DAYS) - 1
        self.assertAlmostEqual(v.atm("SPY", i), 0.137, delta=0.003)
        self.assertAlmostEqual(v.iv("SPY", i, PX["SPY"][i], 730, 32 / 365), 0.1768, delta=0.005)

    def test_strike_hits_target_delta(self):
        v, i = lab.Vol(PX, VIX), 200
        for s, kind, tgt in (("SPY", "call", 0.5), ("NVDA", "put", 0.3)):
            S = PX[s][i]
            K = lab.strike_for_delta(v, s, i, S, 30 / 365, kind, tgt)
            d = abs(lab.greeks(S, K, 30 / 365, v.iv(s, i, S, K, 30 / 365), kind, r=lab.R).delta)
            self.assertAlmostEqual(d, tgt, delta=0.01)

    def test_put_call_parity_at_same_vol(self):
        S, K, T, sig = 100.0, 105.0, 0.1, 0.3
        c = lab.greeks(S, K, T, sig, "call", r=lab.R).price
        p = lab.greeks(S, K, T, sig, "put", r=lab.R).price
        self.assertAlmostEqual(c - p, S - K * math.exp(-lab.R * T), places=6)

    def test_no_lookahead(self):
        # changing prices after day e must not change anything up to day e
        p = {"delta": 0.3, "tp": 0.5, "stop": 1.0, "hold": 15}
        e = 180
        a, _ = lab.simulate(DAYS, PX, VIX, "short_put", p, 80, 200)
        px2 = {s: c[:e + 1] + [x * 1.3 for x in c[e + 1:]] for s, c in PX.items()}
        b, _ = lab.simulate(DAYS, px2, VIX, "short_put", p, 80, 200)
        self.assertEqual(a[: e - 80], b[: e - 80])

    def test_short_puts_stay_cash_secured(self):
        p = {"delta": 0.3, "tp": 0.5, "stop": 1.0, "hold": 15}
        navs, trades = lab.simulate(DAYS, PX, VIX, "short_put", p, 80)
        self.assertTrue(trades)
        self.assertTrue(all(n > 0 for _, n in navs))


if __name__ == "__main__":
    unittest.main()
