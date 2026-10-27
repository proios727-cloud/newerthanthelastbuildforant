import os
import tempfile
import unittest

import chart
from chart import Bar, backtest

ROUND = 9


def bars_from(closes, opens=None):
    opens = opens or closes
    return [Bar(f"2026-01-{i + 1:02d}", o, max(o, c), min(o, c), c) for i, (o, c) in enumerate(zip(opens, closes))]


def r(xs):
    return [None if v is None else round(v, ROUND) for v in xs]


class IndicatorTests(unittest.TestCase):
    def test_constant_series(self):
        x = [5.0] * 30
        self.assertEqual(chart.sma(x, 5)[-1], 5.0)
        self.assertEqual(chart.ema(x, 5)[-1], 5.0)
        self.assertEqual(chart.rma(x, 5)[-1], 5.0)
        mid, up, lo = chart.bollinger(x, 20)
        self.assertEqual(up[-1], lo[-1])

    def test_hand_values(self):
        x = [1.0, 2, 3, 4, 5]
        self.assertEqual(r(chart.sma(x, 3)), [None, None, 2.0, 3.0, 4.0])
        self.assertEqual(r(chart.ema(x, 3)), [None, None, 2.0, 3.0, 4.0])
        self.assertEqual(r(chart.rsi([1.0, 2, 3, 2, 3], 2)), [None, None, 100.0, 50.0, 75.0])
        self.assertEqual(chart.rsi(list(range(1, 40)), 14)[-1], 100.0)

    def test_warmup_indices(self):
        x = [float(i) for i in range(60)]
        line, sig, hist = chart.macd(x, 12, 26, 9)
        self.assertIsNone(line[24])
        self.assertIsNotNone(line[25])
        self.assertIsNone(sig[32])
        self.assertIsNotNone(sig[33])
        self.assertEqual(len(hist), 60)

    def test_true_range_and_atr(self):
        bs = [Bar("a", 10, 12, 9, 11), Bar("b", 11, 15, 10, 14), Bar("c", 14, 14, 8, 9)]
        self.assertEqual(chart.true_range(bs), [3, 5, 6])
        self.assertEqual(chart.atr(bs, 2)[1], 4.0)
        self.assertEqual(chart.atr(bs, 2)[2], 5.0)

    def test_test_the_test(self):
        with self.assertRaises(AssertionError):
            self.assertEqual(r(chart.sma([1.0, 2, 3], 3)), [None, None, 2.5])


class BacktestTests(unittest.TestCase):
    def test_fills_next_open_and_tracks_price(self):
        closes = [100.0, 110, 121, 133.1]
        opens = [100.0, 105, 115, 125]
        res = backtest(bars_from(closes, opens), [1, None, None, None], start_cash=1000)
        self.assertEqual(res.trades[0][3], 105)               # entered at bar 1 open
        self.assertAlmostEqual(res.equity[-1], 1000 * 133.1 / 105)
        self.assertEqual(res.equity[0], 1000)                  # flat on the signal bar

    def test_fees_reduce_equity(self):
        b = bars_from([100.0, 100, 100])
        res = backtest(b, [1, 0, None], fee_bps=10, start_cash=1000)
        self.assertLess(res.equity[-1], 1000)
        self.assertEqual(res.stats["n_trades"], 1)
        self.assertLess(res.trades[0][5], 0)

    def test_no_lookahead(self):
        a = bars_from([100.0, 101, 102, 103])
        b = list(a)
        b[2] = Bar(b[2].ts, b[2].open, 500, 1, 500)            # change a future close
        sig = [1, None, None, None]
        self.assertEqual(backtest(a, sig).trades[0][3], backtest(b, sig).trades[0][3])

    def test_losing_round_trip_drawdown(self):
        res = backtest(bars_from([100.0, 100, 80, 80]), [1, None, 0, None], start_cash=1000)
        self.assertLess(res.trades[0][5], 0)
        self.assertLess(res.stats["max_drawdown"], 0)
        self.assertEqual(res.stats["win_rate"], 0.0)

    def test_shorts_need_opt_in(self):
        b = bars_from([100.0, 100, 90, 90])
        self.assertEqual(backtest(b, [-1, None, None, None]).stats["n_trades"], 0)
        res = backtest(b, [-1, None, None, None], allow_short=True, start_cash=1000)
        self.assertAlmostEqual(res.equity[-1], 1100)

    def test_last_bar_signal_ignored_and_length_checked(self):
        b = bars_from([100.0, 101])
        self.assertEqual(backtest(b, [None, 1]).stats["n_trades"], 0)
        with self.assertRaises(ValueError):
            backtest(b, [1])

    def test_strategies(self):
        closes = [float(i) for i in range(1, 50)]
        self.assertEqual(chart.sma_cross(closes, 3, 5)[-1], 1)
        down = [float(i) for i in range(50, 0, -1)]
        self.assertEqual(chart.rsi_revert(down, 14)[-1], 1)


class CsvTests(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_load(self):
        p = self.write("Date,Open,High,Low,Close,Volume\n2026-01-01,1,2,0.5,1.5,10\n2026-01-02,1.5,2,1,2,12\n")
        bs = chart.load_csv(p)
        self.assertEqual(len(bs), 2)
        self.assertEqual(bs[1].close, 2.0)

    def test_rejects_unsorted_and_missing(self):
        with self.assertRaises(ValueError):
            chart.load_csv(self.write("date,open,high,low,close\n2026-01-02,1,1,1,1\n2026-01-01,1,1,1,1\n"))
        with self.assertRaises(ValueError):
            chart.load_csv(self.write("date,open,close\n2026-01-01,1,1\n"))


if __name__ == "__main__":
    unittest.main()
