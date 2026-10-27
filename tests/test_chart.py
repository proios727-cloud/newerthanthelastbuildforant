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


class SweepTests(unittest.TestCase):
    def setUp(self):
        import math
        closes = [100 + 10 * math.sin(i / 6) + i * 0.1 for i in range(120)]
        self.bars = bars_from(closes)

    def test_combos_skip_invalid(self):
        from chart.sweep import combos
        self.assertTrue(all(p["fast"] < p["slow"] for p in combos("sma_cross")))
        self.assertTrue(all(p["lo"] < p["hi"] for p in combos("rsi_revert")))

    def test_sweep_ranked_by_sharpe(self):
        from chart.sweep import sweep
        rows = sweep(self.bars, "sma_cross")
        sharpes = [s["sharpe"] for _, s in rows]
        self.assertEqual(sharpes, sorted(sharpes, reverse=True))

    def test_walk_forward_picks_on_train_only(self):
        from chart.sweep import sweep, walk_forward
        wf = walk_forward(self.bars, "sma_cross", train_frac=0.7)
        self.assertEqual(wf["params"], sweep(self.bars[:84], "sma_cross")[0][0])
        self.assertEqual(wf["test"]["bars"], 36)
        self.assertAlmostEqual(wf["edge_vs_hold"], wf["test"]["total_return"] - wf["buy_hold_test"]["total_return"])

    def test_walk_forward_ignores_test_slice_when_choosing(self):
        from chart.sweep import walk_forward
        changed = list(self.bars)
        for i in range(84, 120):          # wreck the test slice
            b = changed[i]
            changed[i] = Bar(b.ts, b.open * 3, b.high * 3, b.low * 3, b.close * 3)
        self.assertEqual(walk_forward(self.bars, "sma_cross")["params"],
                         walk_forward(changed, "sma_cross")["params"])

    def test_walk_forward_needs_test_bars(self):
        from chart.sweep import walk_forward
        with self.assertRaises(ValueError):
            walk_forward(self.bars[:20], "sma_cross", train_frac=0.9)


class ScanTests(unittest.TestCase):
    UNIVERSE = {"SPY": {}, "BTC/USD": {}}

    def test_symbol_mapping(self):
        from chart.scan import symbol_for
        self.assertEqual(symbol_for("data/spy.csv", self.UNIVERSE), "SPY")
        self.assertEqual(symbol_for("data/BTC-USD.csv", self.UNIVERSE), "BTC/USD")
        self.assertIsNone(symbol_for("data/DOGE.csv", self.UNIVERSE))

    def test_scan_skips_unknown_and_explains_rejections(self):
        import math
        from chart.scan import scan
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        rows = "\n".join(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d},{c},{c + 1},{c - 1},{c},1"
                         for i, c in enumerate(100 + 5 * math.sin(i / 5) for i in range(100)))
        for name in ("SPY", "DOGE"):
            with open(os.path.join(d, f"{name}.csv"), "w") as f:
                f.write("date,open,high,low,close,volume\n" + rows + "\n")
        res = scan([os.path.join(d, n) for n in os.listdir(d)], self.UNIVERSE)
        self.assertEqual({e["symbol"] for e in res["signal_list"]}, {"SPY"})
        self.assertEqual(res["skipped"][0]["reason"], "not in desk.json universe")
        for e in res["signal_list"]:
            self.assertEqual(e["candidate"], not e["why_not"])

    def test_real_data_files_load(self):
        for sym in ("SPY", "QQQ"):
            bs = chart.load_csv(os.path.join(os.path.dirname(__file__), "..", "chart", "data", f"{sym}.csv"))
            self.assertEqual(len(bs), 100)


def wave(n=120, amp=10.0, period=6.0, drift=0.1):
    import math
    return bars_from([100 + amp * math.sin(i / period) + i * drift for i in range(n)])


class StrategyTests(unittest.TestCase):
    def test_regime(self):
        from chart.strategies import regime
        self.assertEqual(regime([1.0, 2, 3, 2.5], 2), [None, True, True, False])

    def test_rsi_dip_trend_exits_when_trend_breaks(self):
        from chart.strategies import rsi_dip_trend
        down = [float(100 - i) for i in range(40)]
        sig = rsi_dip_trend(down, n=3, lo=30, hi=60, trend=10)
        self.assertTrue(all(s in (0, None) for s in sig))      # never buys a dip in a downtrend
        self.assertEqual(sig[-1], 0)

    def test_bollinger_revert(self):
        from chart.strategies import bollinger_revert
        x = [100.0] * 20 + [90.0, 100.0]
        sig = bollinger_revert(x, n=20, k=2.0)
        self.assertEqual(sig[20], 1)                           # well below the lower band
        self.assertEqual(sig[21], 0)                           # back at the middle band

    def test_donchian_uses_prior_bars_only(self):
        from chart.strategies import donchian_breakout
        bs = [Bar(str(i), 10, 11, 9, 10) for i in range(5)] + [Bar("5", 10, 13, 10, 12), Bar("6", 9, 9, 7, 8)]
        sig = donchian_breakout(bs, n=5, exit_n=3)
        self.assertEqual(sig[5], 1)                            # close 12 > prior 5-bar high 11
        self.assertEqual(sig[6], 0)                            # close 8 < prior 3-bar low 9

    def test_macd_trend_flat_in_downtrend(self):
        from chart.strategies import macd_trend
        sig = macd_trend([float(200 - i) for i in range(80)], 8, 17, 9, 20)
        self.assertEqual(sig[-1], 0)

    def test_every_grid_combo_runs(self):
        from chart.sweep import GRIDS, combos, signals
        bars = wave(80)
        for s in GRIDS:
            for p in combos(s):
                self.assertEqual(len(signals(s, bars, p)), 80)


class RollingTests(unittest.TestCase):
    def test_blocks_cover_the_test_span(self):
        from chart.sweep import rolling_walk_forward
        r = rolling_walk_forward(wave(120), "sma_cross", min_train=40, test=10)
        self.assertEqual(len(r["windows"]), 8)
        self.assertEqual(r["oos"]["bars"], 80)
        self.assertLessEqual(r["windows_beat_hold"], 8)

    def test_future_blocks_cannot_change_past_choices(self):
        from chart.sweep import rolling_walk_forward
        a = wave(120)
        b = list(a)
        for i in range(90, 120):
            x = b[i]
            b[i] = Bar(x.ts, x.open * 2, x.high * 2, x.low * 2, x.close * 2)
        wa = rolling_walk_forward(a, "rsi_revert")["windows"]
        wb = rolling_walk_forward(b, "rsi_revert")["windows"]
        self.assertEqual([w["params"] for w in wa[:5]], [w["params"] for w in wb[:5]])
        self.assertEqual([w["return"] for w in wa[:5]], [w["return"] for w in wb[:5]])
        self.assertNotEqual([w["return"] for w in wa[5:]], [w["return"] for w in wb[5:]])   # the change did bite

    def test_rolling_mode_and_size_check(self):
        from chart.sweep import rolling_walk_forward
        self.assertEqual(rolling_walk_forward(wave(80), "sma_cross", anchored=False)["mode"], "rolling")
        with self.assertRaises(ValueError):
            rolling_walk_forward(wave(45), "sma_cross")


class RotationTests(unittest.TestCase):
    def basket(self):
        up = bars_from([100.0 + i for i in range(60)])
        flat = bars_from([100.0] * 60)
        return {"UP": up, "FLAT": flat}

    def test_align_keeps_common_dates(self):
        from chart import rotate
        b = self.basket()
        b["FLAT"] = b["FLAT"][5:]
        syms, dates, aligned = rotate.align(b)
        self.assertEqual(len(dates), 55)
        self.assertEqual(aligned["UP"][0].ts, dates[0])

    def test_picks_leader_or_cash(self):
        from chart import rotate
        al = rotate.align(self.basket())
        self.assertEqual(rotate.picks(al, lookback=5)[-1], "UP")
        down = {"A": bars_from([100.0 - i * 0.5 for i in range(30)]), "B": bars_from([50.0 - i * 0.1 for i in range(30)])}
        self.assertEqual(rotate.picks(rotate.align(down), lookback=5)[-1], "CASH")

    def test_run_fills_next_open(self):
        from chart import rotate
        al = rotate.align(self.basket())
        t = [None] * 60
        t[10] = "UP"
        r = rotate.run(al, t, start_cash=1000)
        self.assertEqual(r.trades[0][0], al[1][11])
        self.assertAlmostEqual(r.equity[-1], 1000 * 159 / 111)

    def test_rolling_scores_blocks(self):
        from chart import rotate
        r = rotate.rolling(rotate.align(self.basket()), min_train=30, test=10)
        self.assertEqual(len(r["windows"]), 3)
        self.assertEqual(r["latest_target"], "UP")
        self.assertIn("windows_beat_hold", r)

    def test_scan_includes_basket(self):
        from chart.scan import scan
        d = os.path.join(os.path.dirname(__file__), "..", "chart", "data")
        res = scan([os.path.join(d, f) for f in os.listdir(d) if f.endswith(".csv")],
                   {"SPY": {}, "QQQ": {}, "NVDA": {}}, strategies=("sma_cross",))
        self.assertTrue(any(e["strategy"] == "momentum_rotation" for e in res["signal_list"]))
        for e in res["signal_list"]:
            self.assertEqual(e["candidate"], not e["why_not"])
