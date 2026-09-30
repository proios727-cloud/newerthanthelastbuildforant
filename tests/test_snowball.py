import unittest

import judge
import research
from fund.snowball import Snowball
from handoff import jev
from research import tournament


class SnowballTests(unittest.TestCase):
    def test_wins_compound_and_bank(self):
        sb = Snowball(start=500, warmup=100)             # fixed 10% size during warmup
        sb.take(0.10)
        self.assertAlmostEqual(sb.equity, 505.0)         # 10% of 500 staked, +10%
        self.assertAlmostEqual(sb.banked, 1.0)           # 20% of the $5 new high banked
        stake_before = sb.risked * sb.min_frac
        sb.take(0.10)
        self.assertGreater(sb.risked * sb.min_frac, stake_before)   # rollover grows next stake

    def test_banked_money_is_never_risked(self):
        sb = Snowball(start=500, warmup=100, max_dd=0.99, window=1000)
        sb.take(0.5)
        banked = sb.banked
        for _ in range(30):
            sb.take(-1.0)
        self.assertEqual(sb.banked, banked)
        self.assertGreater(sb.equity, banked - 1e-9)

    def test_kill_switch_on_negative_expectancy(self):
        sb = Snowball(start=500, window=5, warmup=100, max_dd=0.99)
        sb.run([("t", -0.01)] * 10)
        self.assertIn("expectancy", sb.halted)
        self.assertEqual(len(sb.history), 5)
        self.assertEqual(sb.take(0.5), 0.0)              # halted: no more trades

    def test_kill_switch_on_drawdown(self):
        sb = Snowball(start=500, warmup=100, min_frac=0.5, max_dd=0.15, window=1000)
        sb.run([("t", -0.2)] * 5)
        self.assertIn("drawdown", sb.halted)

    def test_quarter_kelly_is_bounded(self):
        sb = Snowball(warmup=2)
        sb.history = [0.1, -0.05, 0.1, -0.05]
        self.assertTrue(sb.min_frac <= sb.fraction() <= sb.max_frac)


class TournamentTests(unittest.TestCase):
    def test_walk_forward_scores_only_out_of_sample_entries(self):
        bars, _ = research.load_bars()
        r = research.walk_forward(tournament.meanrev, bars)
        self.assertTrue(all(t.entry_date >= r["split_date"] for t in r["oos_trades"]))

    def test_gates(self):
        self.assertFalse(tournament.qualifies({"expectancy": 0.1, "trades": 10, "max_dd": 0.05})[0])
        self.assertFalse(tournament.qualifies({"expectancy": -0.1, "trades": 99, "max_dd": 0.05})[0])
        self.assertTrue(tournament.qualifies({"expectancy": 0.01, "trades": 40, "max_dd": 0.05})[0])


class JevHandoffTests(unittest.TestCase):
    def ask(self, **over):
        return judge.ask(judge.StubClient(over), {}, jev.QUESTIONS)

    def test_stub_never_vetoes(self):
        self.assertEqual(jev.policy(self.ask())[0], "take")

    def test_confident_news_dip_skips(self):
        a = self.ask(news_driven_dip=judge.Answer(True, 0.9, live=True))
        self.assertEqual(jev.policy(a)[0], "skip")

    def test_event_pending_halves(self):
        a = self.ask(regime=judge.Answer("event_pending", 0.8, live=True))
        self.assertEqual(jev.policy(a)[0], "half_size")


if __name__ == "__main__":
    unittest.main()
