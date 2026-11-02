import unittest

from chart import Bar
from chart import breakout as B


def series(rows, start=0):
    """rows: (open, high, low, close); 4h timestamps in UTC."""
    out = []
    for k, (o, h, l, c) in enumerate(rows, start):
        day, hour = divmod(k, 6)
        out.append(Bar(f"2024-{1 + day // 28:02d}-{1 + day % 28:02d}T{hour * 4:02d}:00:00+00:00", o, h, l, c))
    return out


FLAT = (100, 101, 99, 100)


def setup(after):
    """220 flat bars (EMA and ATR warm up, ATR = 2), a breakout bar closing at 105, then `after`."""
    return series([FLAT] * 220 + [(100, 106, 100, 105)] + after)


class BreakoutTests(unittest.TestCase):
    def test_entry_next_open_and_reachable_channel_exit(self):
        after = [(105.5, 107, 105, 106)] * 10 + [(106, 106, 103.5, 104)] + [(104, 104.5, 103.8, 104)] * 3
        eq, tr = B.run(setup(after), fee_bps=0, slip_bps=0)
        self.assertEqual(tr[0]["entry"], 105.5)
        self.assertEqual(tr[0]["reason"], "10-bar low")
        self.assertEqual(tr[0]["exit"], 104)            # 104 < prior 10-bar low (105) -> fills next open at 104

    def test_stop_fills_at_stop_or_gap_open(self):
        atr_at_signal = None
        bars = setup([(105.5, 106, 105, 105.5), (90, 91, 89, 90)] + [FLAT] * 3)
        from chart.indicators import atr
        atr_at_signal = atr(bars, 14)[220]
        eq, tr = B.run(bars, fee_bps=0, slip_bps=0)
        self.assertEqual(tr[0]["reason"], "stop")
        self.assertEqual(tr[0]["exit"], 90)              # opened below the stop -> fills at the open
        self.assertLess(90, 105.5 - 2 * atr_at_signal)

    def test_costs_reduce_return(self):
        after = [(105.5, 107, 105, 106)] * 10 + [(106, 106, 103.5, 104)] + [(104, 104.5, 103.8, 104)] * 3
        _, free = B.run(setup(after), fee_bps=0, slip_bps=0)
        _, paid = B.run(setup(after), fee_bps=10, slip_bps=10)
        self.assertAlmostEqual(free[0]["ret"], 104 / 105.5 - 1)
        self.assertLess(paid[0]["ret"], free[0]["ret"] - 0.003)

    def test_no_entry_below_trend(self):
        rows = [(200, 201, 199, 200)] * 220 + [(100, 101, 99, 100)] * 30 + [(100, 106, 100, 105)] + [FLAT] * 3
        _, tr = B.run(series(rows))
        self.assertEqual(tr, [])

    def test_no_lookahead(self):
        a = setup([(105.5, 107, 105, 106)] + [FLAT] * 5)
        b = setup([(105.5, 107, 105, 106)] + [(300, 301, 299, 300)] * 5)
        self.assertEqual(B.run(a)[1][0]["entry"], B.run(b)[1][0]["entry"])

    def test_test_the_test(self):
        _, tr = B.run(setup([(105.5, 107, 105, 106)] * 3), fee_bps=0, slip_bps=0)
        self.assertNotEqual(tr[0]["entry"], 105.0)


if __name__ == "__main__":
    unittest.main()
