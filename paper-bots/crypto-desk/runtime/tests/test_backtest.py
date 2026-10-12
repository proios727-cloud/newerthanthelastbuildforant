import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backtest


class ReplayTests(unittest.TestCase):
    def test_stop_precedes_target_on_entry_bar(self):
        rows=[[i*3600,100,101,99,100] for i in range(60)]
        rows[52]=[52*3600,100,120,80,100]
        fast=[99.]*60;slow=[100.]*60;fast[51]=101
        result=backtest.simulate((rows,fast,slow,[True]*60),52,54,"ema_cross",cap=.02)
        self.assertEqual(result["closed_trades"],1)
        self.assertEqual(result["trade_log"][0]["reason"],"entry_bar_stop")
        self.assertLess(result["net_profit"],0)

    def test_signal_uses_prior_bar_and_cap_blocks(self):
        rows=[[i*3600,100,101,99,100] for i in range(60)]
        fast=[99.]*60;slow=[100.]*60;fast[52]=101
        prepared=(rows,fast,slow,[True]*60)
        self.assertEqual(backtest.simulate(prepared,52,53,"ema_cross",cap=.02)["closed_trades"],0)
        report=backtest.simulate(prepared,52,54,"ema_cross",cap=.005)
        self.assertEqual(report["closed_trades"],0)
        self.assertEqual(report["cost_blocked_candidates"],1)

    def test_intrabar_exit_never_reenters_at_earlier_open(self):
        rows=[[i*3600,100,101,99,100] for i in range(60)]
        rows[51]=[51*3600,100,103,99,102]
        rows[52]=[52*3600,102,105,100,104]
        rows[53]=[53*3600,104,120,80,104]
        result=backtest.simulate((rows,[102.]*60,[100.]*60,[True]*60),52,54,"breakout",cap=.02)
        self.assertEqual(result["closed_trades"],1)
        self.assertEqual(result["trade_log"][0]["reason"],"stop_first_if_both_touched")


if __name__=="__main__":unittest.main()
