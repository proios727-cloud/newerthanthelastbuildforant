import csv
import pathlib
import tempfile
import unittest

from verify import replicate as R, screen as SC


def bars(closes, gap=None):
    """Daily OHLC from closes; open = prior close unless a gap is set for that index."""
    t, o, h, l, c = [], [], [], [], []
    for i, x in enumerate(closes):
        op = closes[i - 1] if i else x
        if gap and i in gap:
            op = gap[i]
        t.append(1_600_000_000 + i * 86400)
        o.append(op)
        h.append(max(op, x) * 1.001)
        l.append(min(op, x) * 0.999)
        c.append(x)
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


def fam_fixed(enter_at, exit_at, stop=None):
    def f(b, p):
        n = len(b["c"])
        return [i == enter_at for i in range(n)], [i == exit_at for i in range(n)], stop or {}
    return f


class Fills(unittest.TestCase):
    def test_signal_fills_next_open(self):
        closes = [100.0] * 5 + [110.0, 120.0, 130.0, 140.0]
        b = bars(closes, gap={6: 115.0})
        eq, tr = R.simulate(b, fam_fixed(5, 7), {}, 0.0, 1.0, vol_scale=False)
        # bought at bar 6's open (115), sold at bar 8's open (130 = bar 7's close)
        self.assertAlmostEqual(tr[0], 130 / 115 - 1, places=9)
        self.assertAlmostEqual(eq[5], 1.0)

    def test_gap_through_stop_fills_at_open(self):
        # ATR trail with a wide multiple; the stop level comes from earlier bars only
        closes = [100.0 + i for i in range(30)] + [60.0]
        b = bars(closes, gap={30: 60.0})
        atr = [1.0] * len(closes)
        eq, tr = R.simulate(b, fam_fixed(3, -1, {"atr_trail": (atr, 3.0)}), {}, 0.0, 1.0, vol_scale=False)
        entry = b["o"][4]
        self.assertAlmostEqual(tr[0], 60.0 / entry - 1, places=9)       # the open, not the stop level

    def test_costs_lower_returns_monotonically(self):
        closes = [100 * (1.01 if i % 7 else 0.97) ** i for i in range(300)]
        data = {s: bars(closes) for s in R.SLEEVES}
        ends = [R.portfolio(data, R.fam_donchian, {"entry": 10, "exit": 5}, c)[1][-1] for c in (0.0, 0.0002, 0.00055)]
        self.assertGreater(ends[0], ends[1])
        self.assertGreater(ends[1], ends[2])

    def test_incumbent_matches_trendbook_signal(self):
        from fund import trendbook
        closes = [100 + 10 * ((i // 40) % 2) * (i % 40) - 3 * (i % 5) for i in range(260)]
        b = bars(closes)
        up, dn, _ = R.fam_incumbent(b, {"fast": 20, "slow": 100, "trail": 0.8})
        for i in range(120, 260, 13):
            ind = trendbook.indicators(closes[:i + 1])
            self.assertEqual(up[i], ind["up2"])
            self.assertEqual(dn[i], ind["down2"])


class Screen(unittest.TestCase):
    def rows(self, extra):
        base = {"id": "a", "name": "EMA trend", "symbol": "BTCUSDT", "timeframe": "1h", "net_pct": "80",
                "max_dd": "20", "win_rate_pct": "45", "profit_factor": "1.6", "sharpe": "1.2", "sortino": "1.8",
                "trades": "400", "from_ts": "1600000000000", "to_ts": str(1600000000000 + int(4 * 365.25 * 86400000)),
                "view_url": "u", "sort_source": "sharpe"}
        out = []
        for i, e in enumerate(extra):
            r = dict(base, id=str(i))
            r.update(e)
            out.append(r)
        d = pathlib.Path(tempfile.mkdtemp())
        with open(d / "rows.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(base))
            w.writeheader()
            w.writerows(out)
        return SC.parse(d / "rows.csv")

    def test_filters_and_dedupe(self):
        rows = self.rows([{}, {"name": "copy"}, {"trades": "100", "net_pct": "81"}, {"profit_factor": "", "net_pct": "82"},
                          {"sharpe": "6", "net_pct": "83"}, {"name": "LTC IS-only", "net_pct": "84"}])
        summary, surv = SC.screen(rows)
        self.assertEqual(summary["unique_backtests"], 5)            # the copy is merged
        self.assertEqual([r["id"] for r in surv], ["0"])
        self.assertEqual(summary["fail_reasons"]["trades<150"], 1)
        self.assertEqual(summary["fail_reasons"]["pf outside 1.2-4"], 1)
        self.assertIn("pf>4 or sharpe>5", summary["red_flags"])

    def test_timeframes(self):
        self.assertEqual([SC.tf_minutes(x) for x in ("60", "1h", "15m", "240", "1d")], [60, 60, 15, 240, 1440])


if __name__ == "__main__":
    unittest.main()
