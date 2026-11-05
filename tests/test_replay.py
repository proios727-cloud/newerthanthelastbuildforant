import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReplayTests(unittest.TestCase):
    def test_replay_runs_on_repo_bars_and_conserves_money(self):
        spec = importlib.util.spec_from_file_location("rp", ROOT / "scripts/replay_daytrade.py")
        rp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rp)
        trades, days = rp.replay(ROOT / "chart/data/intraday/15m", n_sessions=10, start=2000.0)
        self.assertEqual(len(days), 10)
        self.assertAlmostEqual(days[-1]["equity"], round(2000 + sum(t["pnl"] for t in trades), 2), delta=0.05)
        self.assertTrue(all(t["side"] == "long" or t["cash_account_ok"].startswith("no") for t in trades))
        longs = sum(t["pnl"] for t in trades if t["side"] == "long")
        self.assertLessEqual(abs(days[-1]["equity_long_only"] - 2000 - longs), 1.0)   # long-only sleeves compound separately


if __name__ == "__main__":
    unittest.main()
