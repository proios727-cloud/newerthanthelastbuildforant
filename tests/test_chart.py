import json
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
        from chart.validate import check
        d = os.path.join(os.path.dirname(__file__), "..", "chart", "data")
        dates = set()
        for sym in ("SPY", "QQQ", "IWM", "NVDA", "AMD", "AAPL", "MSFT", "TSLA"):
            r = check(os.path.join(d, f"{sym}.csv"))
            self.assertTrue(r["ok"], (sym, r["problems"]))
            self.assertGreaterEqual(r["bars"], 750)
            dates.add(tuple(b.ts for b in chart.load_csv(os.path.join(d, f"{sym}.csv"))))
        self.assertEqual(len(dates), 1)                                    # every file covers the same sessions


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


class ValidateTests(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_clean_file_passes_and_matches_reference(self):
        from chart.validate import check
        a = self.write("date,open,high,low,close\n2026-01-01,10,11,9,10.5\n2026-01-02,10.5,11,10,10.8\n")
        ref = self.write("date,open,high,low,close\n2026-01-02,1,1,1,10.8\n")
        r = check(a, ref)
        self.assertTrue(r["ok"])
        self.assertEqual((r["reference_overlap"], r["reference_matched"]), (1, 1))

    def test_catches_bad_rows(self):
        from chart.validate import check
        bad = self.write("date,open,high,low,close\n2026-01-01,10,9,8,10\n2026-01-02,10,30,10,25\n")
        probs = " ".join(check(bad)["problems"])
        self.assertIn("OHLC out of order", probs)
        self.assertIn("in one day", probs)
        ref = self.write("date,open,high,low,close\n2026-01-02,1,1,1,24\n")
        self.assertIn("vs reference", " ".join(check(bad, ref)["problems"]))
        self.assertFalse(check(self.write("date,open,high,low,close\n2026-01-02,1,1,1,1\n2026-01-01,1,1,1,1\n"))["ok"])


class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir))
        self.log = os.path.join(self.dir, "signals.jsonl")
        self.data = os.path.join(self.dir, "data")
        os.mkdir(self.data)

    def scan_result(self, as_of, signal="long"):
        return {"signal_list": [
            {"symbol": "SPY", "strategy": "bollinger_revert", "params": {}, "as_of": as_of, "signal": signal, "candidate": False},
            {"symbol": "QQQ+SPY", "strategy": "momentum_rotation", "params": {}, "as_of": as_of, "signal": "hold CASH", "candidate": False},
        ]}

    def test_record_is_once_per_as_of(self):
        from chart import forward
        self.assertIsNotNone(forward.record(self.scan_result("2026-01-05"), self.log))
        self.assertIsNone(forward.record(self.scan_result("2026-01-05"), self.log))
        self.assertIsNotNone(forward.record(self.scan_result("2026-01-06"), self.log))
        rows = open(self.log).read().splitlines()
        self.assertEqual(len(rows), 2)
        import json
        self.assertIsNone(json.loads(rows[0])["entries"][1]["long"])   # basket in cash is not long

    def test_report_scores_from_next_open_and_waits_for_data(self):
        from chart import forward
        with open(os.path.join(self.data, "SPY.csv"), "w") as f:
            f.write("date,open,high,low,close\n2026-01-05,100,101,99,100\n2026-01-06,100,111,100,110\n"
                    "2026-01-07,110,111,104,105\n")
        forward.record(self.scan_result("2026-01-05"), self.log)
        forward.record(self.scan_result("2026-01-07"), self.log)            # no bar after this yet
        r = forward.report(self.log, self.data, horizons=(1, 2, 5))
        s = r["by_strategy"]["bollinger_revert"]
        self.assertAlmostEqual(s["1d"]["mean"], 0.10)                      # 2026-01-06 open 100 → close 110
        self.assertAlmostEqual(s["2d"]["mean"], 0.05)                      # → 2026-01-07 close 105
        self.assertEqual(s["5d"]["n"], 0)                                  # horizon not elapsed
        self.assertEqual(r["signals_waiting_for_next_bar"], 1)
        self.assertEqual(r["scans_logged"], 2)


class UpdateTests(unittest.TestCase):
    AV = "timestamp,open,high,low,close,volume\r\n2026-01-07,12,13,11,12.5,300\r\n2026-01-06,11,12,10,11.5,200\r\n2026-01-05,10,11,9,10.5,100\r\n"

    class Resp:
        def __init__(self, text):
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.text.encode()

    def test_merge_appends_only_newer_rows(self):
        from chart.update import merge, parse_av_csv
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        p = os.path.join(d, "SPY.csv")
        with open(p, "w") as f:
            f.write("date,open,high,low,close,volume\n2026-01-05,10,11,9,10.5,100\n")
        rows = parse_av_csv(self.AV)
        self.assertEqual([r[0] for r in rows], ["2026-01-05", "2026-01-06", "2026-01-07"])
        self.assertEqual(merge(p, rows), 2)
        self.assertEqual(merge(p, rows), 0)
        bars = chart.load_csv(p)
        self.assertEqual([b.close for b in bars], [10.5, 11.5, 12.5])

    def test_update_skips_crypto_and_reports_errors(self):
        from chart.update import update
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d))
        calls = []

        def opener(url, timeout=None):
            calls.append(url)
            if "symbol=BAD" in url:
                return self.Resp('{"Information": "rate limit"}')
            return self.Resp(self.AV)

        uni = {"SPY": {"asset": "equity"}, "BAD": {"asset": "equity"}, "BTC/USD": {"asset": "crypto"}}
        rep = update(d, uni, key="k", pause=0, opener=opener)
        self.assertEqual(rep["SPY"], 3)
        self.assertTrue(rep["BAD"].startswith("error: rate limit"))
        self.assertNotIn("BTC/USD", rep)
        self.assertEqual(len(calls), 2)


class AdjustTests(unittest.TestCase):
    def test_split_adjust_divides_only_earlier_bars(self):
        from chart.adjust import split_adjust
        bs = [Bar("2024-06-07", 1200, 1210, 1190, 1208.8, 100), Bar("2024-06-10", 120, 123, 117, 121.8, 1000)]
        out = split_adjust(bs, [("2024-06-10", 10.0)])
        self.assertAlmostEqual(out[0].close, 120.88)
        self.assertAlmostEqual(out[0].volume, 1000)
        self.assertEqual(out[1], bs[1])

    def test_correction_caps_bad_high_and_is_reported(self):
        from chart.adjust import correct
        bs = [Bar("2024-06-10", 120.45, 195.95, 117.01, 121.79, 1)]
        fixed, applied = correct(bs, "NVDA")
        self.assertEqual(fixed[0].high, 121.79)
        self.assertEqual(applied[0]["high"], [195.95, 121.79])
        self.assertEqual(correct(bs, "AMD")[1], [])

    def test_prepare_passes_validator_on_split_day(self):
        from chart.adjust import prepare, write_csv
        from chart.validate import check
        bs = [Bar("2024-06-07", 1200, 1210, 1190, 1208.8, 100), Bar("2024-06-10", 120.45, 195.95, 117.01, 121.79, 1000)]
        raw = os.path.join(tempfile.mkdtemp(), "NVDA.csv")
        write_csv(raw, bs)
        self.assertFalse(check(raw)["ok"])
        out, applied = prepare(bs, "NVDA")
        write_csv(raw, out)
        self.assertTrue(check(raw)["ok"], check(raw)["problems"])
        self.assertEqual(len(applied), 1)

    def test_wick_check(self):
        from chart.validate import check
        p = os.path.join(tempfile.mkdtemp(), "X.csv")
        with open(p, "w") as f:
            f.write("date,open,high,low,close\n2026-02-02,690,696.9,69.005,694\n")
        self.assertIn("wick", " ".join(check(p)["problems"]))


class RiskFilterTests(unittest.TestCase):
    HOLD = {"max_drawdown": -0.54, "calmar": 0.48, "sharpe": 0.7}

    def oos(self, **kw):
        base = {"max_drawdown": -0.23, "calmar": 1.14, "exposure": 0.38, "sharpe": 0.9, "n_trades": 26}
        base.update(kw)
        return base

    def test_much_shallower_drawdown_passes(self):
        from chart.scan import _risk_verdict
        self.assertEqual(_risk_verdict(self.oos(), self.HOLD), [])

    def test_barely_shallower_drawdown_fails(self):
        from chart.scan import _risk_verdict
        r = _risk_verdict(self.oos(max_drawdown=-0.50), self.HOLD)     # only 7% shallower
        self.assertTrue(any("drawdown" in x for x in r))

    def test_needs_calmar_exposure_and_trades(self):
        from chart.scan import _risk_verdict
        r = " ".join(_risk_verdict(self.oos(calmar=0.3, exposure=0.1, n_trades=1), self.HOLD))
        self.assertIn("Calmar", r)
        self.assertIn("invested only 10%", r)
        self.assertIn("fewer than 3", r)

    def test_cagr_and_calmar_in_stats(self):
        from chart.backtest import _stats
        eq = [100.0, 120.0, 90.0, 121.0]
        s = _stats(eq, [], 4, 100.0, 4)                                 # 4 bars = 1 year
        self.assertAlmostEqual(s["cagr"], 0.21)
        self.assertAlmostEqual(s["max_drawdown"], -0.25)
        self.assertAlmostEqual(s["calmar"], 0.84)


class EtfDataTests(unittest.TestCase):
    D = os.path.join(os.path.dirname(__file__), "..", "chart", "data", "etf")

    def test_drops_remove_rows_and_are_reported(self):
        from chart.adjust import prepare
        bs = [Bar("2026-10-05", 50, 51, 49, 50), Bar("2026-10-06", 0.0002, 0.0002, 0.0002, 0.0002), Bar("2026-10-07", 50, 51, 49, 50.5)]
        out, applied = prepare(bs, "XLF")
        self.assertEqual([b.ts for b in out], ["2026-10-05", "2026-10-07"])
        self.assertTrue(applied[0]["dropped"])

    def test_etf_files_validate_and_splits_are_adjusted(self):
        from chart.validate import check
        files = sorted(f for f in os.listdir(self.D) if f.endswith(".csv"))
        self.assertEqual(len(files), 13)
        for f in files:
            r = check(os.path.join(self.D, f))
            self.assertTrue(r["ok"], (f, r["problems"]))
        xlk = {b.ts: b.close for b in chart.load_csv(os.path.join(self.D, "XLK.csv"))}
        self.assertLess(abs(xlk["2025-12-05"] / xlk["2025-12-04"] - 1), 0.1)   # no fake -50% split day


class RobustTests(unittest.TestCase):
    def basket(self):
        import math
        mk = lambda f: bars_from([100 + f(i) for i in range(320)])
        return {"A": mk(lambda i: i * 0.3), "B": mk(lambda i: 10 * math.sin(i / 9)), "C": mk(lambda i: -i * 0.05),
                "D": mk(lambda i: 5 * math.sin(i / 4) + i * 0.1)}

    def test_top1_reproduces_rotate(self):
        from chart import robust, rotate
        al = rotate.align(self.basket())
        a = rotate.rolling(al, min_train=120, test=20, fee_bps=1, slippage_bps=2)
        b = robust.rolling_multi(al, min_train=120, test=20, top=1, fee_bps=1, slippage_bps=2)
        self.assertAlmostEqual(a["oos"]["total_return"], b["oos"]["total_return"], places=10)
        self.assertEqual(a["windows_beat_hold"], b["beat"])

    def test_picks_top_offsets_and_cash(self):
        from chart import robust, rotate
        al = rotate.align(self.basket())
        p = robust.picks_top(al, lookback=20, hold=10, top=2, offset=3)
        days = [i for i, t in enumerate(p) if t is not None]
        self.assertEqual(days[0], 23)
        self.assertTrue(all((d - 23) % 10 == 0 for d in days))
        self.assertTrue(all(len(t) <= 2 for t in p if t is not None))
        down = rotate.align({"X": bars_from([100.0 - i for i in range(40)]), "Y": bars_from([50.0 - i * 0.1 for i in range(40)])})
        self.assertEqual(robust.picks_top(down, lookback=5, top=2)[-1], ())

    def test_changes_only_trades_less_and_matches_top1(self):
        from chart import robust, rotate
        al = rotate.align(self.basket())
        t3 = robust.picks_top(al, lookback=20, hold=5, top=3)
        full = robust.run_multi(al, t3, 0, None, fee_bps=10, slippage_bps=10)
        diff = robust.run_multi(al, t3, 0, None, fee_bps=10, slippage_bps=10, trade_changes_only=True)
        self.assertLess(len(diff.trades), len(full.trades))
        t1 = robust.picks_top(al, lookback=20, hold=5, top=1)
        self.assertAlmostEqual(robust.run_multi(al, t1, 0, None, fee_bps=5).equity[-1],
                               robust.run_multi(al, t1, 0, None, fee_bps=5, trade_changes_only=True).equity[-1])

    def test_day_sweep_covers_every_day(self):
        from chart import robust, rotate
        r = robust.day_sweep(rotate.align(self.basket()), lookback=20, hold=7, top=2, min_train=120)
        self.assertEqual(r["days"], 7)
        self.assertLessEqual(r["cagr"]["min"], r["cagr"]["median"])
        self.assertLessEqual(r["cagr"]["median"], r["cagr"]["max"])

    def test_buffer_keeps_a_held_fund_until_it_leaves_top_plus_buffer(self):
        from chart import robust, rotate
        al = rotate.align({"A": bars_from([100, 110, 111, 112]), "B": bars_from([100, 101, 113, 114]),
                           "C": bars_from([100, 99, 98, 97])})
        self.assertEqual(robust.picks_top(al, lookback=1, top=1)[1:3], [("A",), ("B",)])
        self.assertEqual(robust.picks_top(al, lookback=1, top=1, buffer=1)[1:3], [("A",), ("A",)])
        big = rotate.align(self.basket())
        self.assertEqual(robust.picks_top(big, lookback=20, hold=5, top=2),
                         robust.picks_top(big, lookback=20, hold=5, top=2, buffer=0))

    def test_trend_filter_goes_to_cash_below_basket_average(self):
        from chart import robust, rotate
        al = rotate.align({"X": bars_from([100, 110, 120, 130, 140, 100, 101])})
        self.assertEqual(robust.picks_top(al, lookback=1)[-1], ("X",))
        self.assertEqual(robust.picks_top(al, lookback=1, trend=5)[-1], ())
        self.assertEqual(robust.picks_top(al, lookback=1, trend=5)[3], ("X",))     # above its average: unfiltered


class RotationForwardTests(unittest.TestCase):
    def basket(self):
        # Business days across Jan-Apr 2026; A trends up, B flat, C down, D up slowly.
        from datetime import date, timedelta
        days, d = [], date(2026, 1, 2)
        while len(days) < 90:
            if d.weekday() < 5:
                days.append(d.isoformat())
            d += timedelta(days=1)
        mk = lambda f: [Bar(t, f(i), f(i) + 1, f(i) - 1, f(i)) for i, t in enumerate(days)]
        return {"A": mk(lambda i: 100 + i), "B": mk(lambda i: 100.0), "C": mk(lambda i: 200 - i), "D": mk(lambda i: 100 + 0.2 * i)}

    def test_signal_only_on_first_session_of_month(self):
        from chart.forward import rotation_signal
        b = self.basket()
        first_of_month = [i for i in range(1, 90) if b["A"][i].ts[:7] != b["A"][i - 1].ts[:7]]
        for i in range(70, 90):
            cut = {s: v[:i + 1] for s, v in b.items()}
            sig = rotation_signal(cut, lookback=60, top=2)
            self.assertEqual(sig is not None, i in first_of_month)
        i = [k for k in first_of_month if k >= 60][0]
        sig = rotation_signal({s: v[:i + 1] for s, v in b.items()}, lookback=60, top=2)
        self.assertEqual(sig["picks"], ["A", "D"])             # B is flat (momentum 0, not > 0), C is falling

    def test_record_once_and_report_scores_next_open(self):
        from chart.forward import record_rotation, report_rotation
        b = self.basket()
        log = os.path.join(tempfile.mkdtemp(), "rot.jsonl")
        decided = []
        for i in range(60, 90):
            cut = {s: v[:i + 1] for s, v in b.items()}
            if record_rotation(cut, log, lookback=60, top=2):
                decided.append(b["A"][i].ts)
            self.assertIsNone(record_rotation(cut, log, lookback=60, top=2) if decided and decided[-1] == b["A"][i].ts else None)
        r = report_rotation(b, log)
        self.assertEqual(r["decisions_logged"], len(decided))
        p = r["periods"][0]
        start = next(x.ts for x in b["A"] if x.ts > decided[0])
        self.assertEqual(p["from"], start)
        a = {x.ts: x for x in b["A"]}; dd = {x.ts: x for x in b["D"]}
        self.assertAlmostEqual(p["rule"], round(((a[p["to"]].close / a[start].open - 1) + (dd[p["to"]].close / dd[start].open - 1)) / 2, 5))

    def test_late_decision_day_bar_is_still_recorded_and_flagged(self):
        from chart.forward import record_rotation
        b = self.basket()
        i = [k for k in range(61, 90) if b["A"][k].ts[:7] != b["A"][k - 1].ts[:7]][0]
        d = tempfile.mkdtemp()
        on_time, late = os.path.join(d, "a.jsonl"), os.path.join(d, "b.jsonl")
        record_rotation({s: v[:i + 1] for s, v in b.items()}, on_time, lookback=60, top=2)
        self.assertIsNone(record_rotation({s: v[:i] for s, v in b.items()}, late, lookback=60, top=2))
        sig = record_rotation({s: v[:i + 2] for s, v in b.items()}, late, lookback=60, top=2)   # day i arrives with i+1
        ref = json.loads(open(on_time).read())
        self.assertEqual((sig["as_of"], sig["picks"], sig["momentum"]), (ref["as_of"], ref["picks"], ref["momentum"]))
        self.assertTrue(sig["late"])
        self.assertIsNone(record_rotation({s: v[:i + 3] for s, v in b.items()}, late, lookback=60, top=2))
        from chart.forward import rotation_brief
        self.assertIn("Recorded late", rotation_brief(b, late, os.path.join(d, "none.jsonl")))
        far = os.path.join(d, "c.jsonl")                                     # more than CATCH_UP sessions late: skipped
        self.assertIsNone(record_rotation({s: v[:i + 7] for s, v in b.items()}, far, lookback=60, top=2))

    def test_replay_matches_live_record_path(self):
        from chart.forward import record_rotation, replay_rotation, report_rotation
        b = self.basket()
        log = os.path.join(tempfile.mkdtemp(), "rot.jsonl")
        for i in range(90):
            record_rotation({s: v[:i + 1] for s, v in b.items()}, log, lookback=60, top=2)
        live = report_rotation(b, log)
        rep = replay_rotation(b, lookback=60, top=2)
        self.assertEqual(live["periods"], rep["periods"])

    def test_signal_buffer_uses_previous_picks_and_trend_can_go_to_cash(self):
        from chart.forward import rotation_signal
        b = self.basket()
        i = [k for k in range(61, 90) if b["A"][k].ts[:7] != b["A"][k - 1].ts[:7]][0]
        cut = {s: v[:i + 1] for s, v in b.items()}
        self.assertEqual(rotation_signal(cut, lookback=60, top=1)["picks"], ["A"])
        self.assertEqual(rotation_signal(cut, lookback=60, top=1, buffer=1, prev=("D",))["picks"], ["D"])
        self.assertEqual(rotation_signal(cut, lookback=60, top=1, buffer=0, prev=("D",))["picks"], ["A"])
        px = lambda k: 100.0 + k if k <= i - 3 else 100.0 + (i - 3) - 8 * (k - (i - 3))   # up, then a sharp 3-day drop
        flat = {s: [Bar(x.ts, px(k), px(k) + 1, px(k) - 1, px(k)) for k, x in enumerate(v[:i + 1])] for s, v in b.items()}
        self.assertEqual(len(rotation_signal(flat, lookback=60, top=2)["picks"]), 2)        # momentum still positive
        sig = rotation_signal(flat, lookback=60, top=2, trend=20)
        self.assertEqual(sig["picks"], [])
        self.assertLess(sig["basket_vs_trend"], 0)

    def test_tickets_trade_only_changes_and_are_written_once(self):
        from chart.forward import rotation_tickets
        b = self.basket()
        d = tempfile.mkdtemp()
        log, tix = os.path.join(d, "rot.jsonl"), os.path.join(d, "tix.jsonl")
        self.assertIsNone(rotation_tickets(b, log, tix))
        t0, t1 = b["A"][70].ts, b["A"][80].ts
        with open(log, "w") as f:
            f.write(json.dumps({"as_of": t0, "picks": ["A", "D"]}) + "\n")
        first = rotation_tickets(b, log, tix, nav=100_000, weight_pct=5)
        self.assertEqual([(t["symbol"], t["side"], t["qty"]) for t in first["tickets"]],
                         [("A", "buy", int(5000 // b["A"][70].close)), ("D", "buy", int(5000 // b["D"][70].close))])
        self.assertIsNone(rotation_tickets(b, log, tix))
        with open(log, "a") as f:
            f.write(json.dumps({"as_of": t1, "picks": ["A", "B"]}) + "\n")
        second = rotation_tickets(b, log, tix, nav=100_000, weight_pct=5)
        self.assertEqual([(t["symbol"], t["side"]) for t in second["tickets"]], [("D", "sell"), ("B", "buy")])
        self.assertEqual(second["tickets"][0]["qty"], first["tickets"][1]["qty"])
        self.assertEqual(second["kept"], ["A"])
        self.assertLess(second["tickets"][0]["limit"], second["tickets"][0]["ref_close"])
        self.assertGreater(second["tickets"][1]["limit"], second["tickets"][1]["ref_close"])


class DoctorTests(unittest.TestCase):
    def test_dates(self):
        from datetime import date
        from chart.doctor import next_decision, weekdays_between
        self.assertEqual(next_decision(date(2026, 10, 28)), date(2026, 11, 2))
        self.assertEqual(next_decision(date(2026, 11, 2)), date(2026, 11, 2))
        self.assertEqual(next_decision(date(2026, 8, 1)), date(2026, 8, 3))      # Saturday the 1st → Monday
        self.assertEqual(weekdays_between(date(2026, 10, 23), date(2026, 10, 26)), 1)   # Fri → Mon
        self.assertEqual(weekdays_between(date(2026, 10, 26), date(2026, 10, 26)), 0)

    def test_flags_missing_key_stale_and_lagging_files(self):
        from datetime import date
        from chart.doctor import check
        d = tempfile.mkdtemp()
        for sym, last in (("AAA", "2026-10-26"), ("BBB", "2026-10-23")):
            with open(os.path.join(d, f"{sym}.csv"), "w") as f:
                f.write(f"date,open,high,low,close,volume\n2026-10-22,1,1,1,1,0\n{last},1,1,1,1,0\n")
        ok = check([d], today=date(2026, 10, 27), env={"ALPHAVANTAGE_API_KEY": "x"})
        self.assertEqual(ok["data"][d]["weekdays_behind"], 1)
        self.assertEqual(len(ok["problems"]), 1)
        self.assertIn("BBB", ok["problems"][0])
        bad = check([d], today=date(2026, 11, 6), env={})
        self.assertFalse(bad["ok"])
        self.assertEqual(len(bad["problems"]), 3)
        self.assertEqual(bad["next_rotation_decision"], "2026-12-01")


class LongrunTests(unittest.TestCase):
    def periods(self):
        p = lambda d0, d1, picks, r, b: {"decided": d0, "from": d0, "to": d1, "picks": picks, "complete": True,
                                         "rule": r, "basket": b, "excess": r - b}
        return [p("2008-01-02", "2008-12-31", ["A", "B", "C"], -0.10, -0.30),
                p("2009-01-02", "2009-12-31", ["A", "B", "D"], 0.20, 0.25),
                p("2010-01-04", "2010-12-31", ["A", "E", "F"], 0.10, 0.10)]

    def test_summarize_drawdown_turnover_and_cost_drag(self):
        from chart.longrun import summarize
        s = summarize(self.periods(), cost_bps=(10,))
        self.assertAlmostEqual(s["drawdown"], -0.10)
        self.assertAlmostEqual(s["basket_drawdown"], -0.30)
        self.assertEqual(s["months_ahead"], 1)
        self.assertEqual(s["swaps_per_month"], 1.5)                       # 1 then 2 names changed
        self.assertAlmostEqual(s["cagr"] - s["net_cagr"]["10bp"], 1.5 * 12 * 2 / 3 * 10 / 1e4, places=4)

    def test_regimes_and_years(self):
        from chart.longrun import by_year, regimes
        r = regimes(self.periods(), (("crash", "2008-01-01", "2008-12-31"), ("none", "2001-01-01", "2001-12-31")))
        self.assertEqual(r, [{"regime": "crash", "rule": -0.1, "basket": -0.3, "months": 1}])
        self.assertEqual([y["year"] for y in by_year(self.periods())], ["2008", "2009", "2010"])


class BriefTests(unittest.TestCase):
    def test_brief_lists_picks_changes_tickets_and_blockers(self):
        from chart.forward import record_rotation, rotation_brief, rotation_tickets
        b = RotationForwardTests().basket()
        d = tempfile.mkdtemp()
        log, tix, tr = (os.path.join(d, n) for n in ("rot.jsonl", "tix.jsonl", "tr.jsonl"))
        self.assertIsNone(rotation_brief(b, log, tix))
        for i in range(90):
            cut = {s: v[:i + 1] for s, v in b.items()}
            if record_rotation(cut, log, lookback=60, top=2):
                rotation_tickets(cut, log, tix)
            record_rotation(cut, tr, lookback=60, top=2, trend=20)
        text = rotation_brief(b, log, tix, tr, {"problems": ["key missing"]},
                              {"hold": False, "decided": "2026-03-31", "close_vs_average_now": -0.02})
        self.assertIn("Below: cash as of 2026-03-31", text)
        self.assertIn("**Hold: A, D**", text)
        self.assertIn("## Paper tickets", text)
        self.assertIn("## Defensive variant", text)
        self.assertIn("- key missing", text)
        self.assertIn("| 1 | A |", text)


class DividendTests(unittest.TestCase):
    def test_back_adjustment_puts_the_dividend_into_returns(self):
        from chart.dividends import total_return
        bars = bars_from([100.0, 100.0, 99.0, 99.0])          # pays 1.0 on day 3: price drops, holder is whole
        tr = total_return(bars, [(bars[2].ts, 1.0)])
        self.assertAlmostEqual(tr[2].close / tr[1].close, 1.0)
        self.assertEqual([b.close for b in tr[2:]], [99.0, 99.0])  # latest prices stay as traded
        self.assertAlmostEqual(tr[0].open, 99.0)
        self.assertEqual(total_return(bars, [("1999-01-01", 1.0), (bars[0].ts, 1.0)]), bars)   # outside / first bar

    def test_load_split_adjusts_and_apply_writes_copies(self):
        from chart import dividends
        d = tempfile.mkdtemp()
        table = os.path.join(d, "div.csv")
        with open(table, "w") as f:
            f.write("symbol,week_ending,ex_date,amount\nXLK,2025-09-26,2025-09-22,0.40\nXLK,2025-12-26,2025-12-22,0.22\n")
        self.assertEqual(dividends.load(table)["XLK"], [("2025-09-22", 0.2), ("2025-12-22", 0.22)])
        src, dst = os.path.join(d, "src"), os.path.join(d, "dst")
        os.mkdir(src)
        with open(os.path.join(src, "XLK.csv"), "w") as f:
            f.write("date,open,high,low,close,volume\n2025-09-19,100,101,99,100,1\n2025-09-22,99.8,100,99,99.8,1\n")
        self.assertEqual(dividends.apply(src, dst, table), {"XLK": 1})
        out = chart.load_csv(os.path.join(dst, "XLK.csv"))
        self.assertAlmostEqual(out[0].close, 99.8)


class OverlayTests(unittest.TestCase):
    def weekly(self, closes, start="2020-01-03"):
        from datetime import date, timedelta
        d = date.fromisoformat(start)
        return [Bar((d + timedelta(weeks=k)).isoformat(), c, c, c, c) for k, c in enumerate(closes)]

    def test_decisions_month_end_average_and_unfinished_month(self):
        from chart.overlay import decisions
        bars = self.weekly([100 + k for k in range(30)])                        # steady rise: always above average
        d = decisions(bars, months=3)
        self.assertTrue(d and all(v == 1 for v in d.values()))
        self.assertTrue(all(bars[i].ts[:7] != bars[i + 1].ts[:7] for i in d if i + 1 < len(bars)))  # month-end bars
        self.assertNotIn(len(bars) - 1, d)            # 2020-07-24: July isn't over, so no decision on the last bar
        falling = self.weekly([200 - 3 * k for k in range(30)])
        self.assertTrue(all(v == 0 for v in decisions(falling, months=3).values()))

    def test_run_goes_to_cash_and_earns_cash_rate(self):
        from chart.overlay import run, verdict
        up = [100 + k for k in range(26)]
        down = [125 - 4 * k for k in range(1, 26)]
        bars = self.weekly(up + down)
        r0 = run(bars, months=2, start=0, fee_bps=0, slippage_bps=0)
        r2 = run(bars, months=2, start=0, fee_bps=0, slippage_bps=0, cash_rate=0.05)
        self.assertGreater(r0["stats"]["max_drawdown"], r0["hold"]["max_drawdown"])   # shallower than holding
        self.assertGreater(r2["equity"][-1], r0["equity"][-1])                        # cash yield adds while out
        self.assertLess(r0["stats"]["exposure"], 1.0)
        self.assertIn("risk_filter", verdict(r0))

    def test_status_reports_last_completed_decision(self):
        from chart.overlay import status
        s = status(self.weekly([100 + k for k in range(30)]), months=3)
        self.assertTrue(s["hold"])
        self.assertLess(s["decided"], s["last_bar"])
        self.assertGreater(s["close_vs_average_now"], 0)
