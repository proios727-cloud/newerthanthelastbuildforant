import importlib.util
import pathlib
import unittest

from fund import config

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bt", ROOT / "backtest" / "run.py")
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)


class BacktestHarnessTests(unittest.TestCase):
    def test_data_joins_and_calendars(self):
        s = bt.load_series()  # asserts SPY overlap, join continuity and both calendars
        self.assertEqual(len(s["SPY"]), 300)
        self.assertEqual(len(s["BTC/USD"]), 299)
        self.assertEqual(s["SPY"][-1][0], "2026-09-28")

    def test_replay_is_deterministic_and_within_caps(self):
        cfg, s = config.load(), bt.load_series()
        a = bt.run(s, cfg)
        b = bt.run(s, cfg)
        self.assertEqual([n for _, n, _ in a[1]], [n for _, n, _ in b[1]])
        for _, nav, gross in a[1]:
            self.assertLessEqual(gross, cfg.limits.max_gross_pct / 100 * nav + 1e-6)

    def test_costs_only_hurt(self):
        cfg, s = config.load(), bt.load_series()
        r0 = bt.run(s, cfg)[1][-1][1]
        r10 = bt.run(s, cfg, slip_bps=10)[1][-1][1]
        self.assertLess(r10, r0)


if __name__ == "__main__":
    unittest.main()
