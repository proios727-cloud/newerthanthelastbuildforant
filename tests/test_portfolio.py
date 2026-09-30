import math
import random
import unittest

from backtest import portfolio as P, sleeves as S


def months(n, start=2010):
    return [f"{start + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


def streams(n=120, seed=1):
    rng = random.Random(seed)
    ms = months(n)
    return ({"A": {m: rng.gauss(0.008, 0.04) for m in ms}, "B": {m: rng.gauss(0.005, 0.015) for m in ms},
             "C": {m: rng.gauss(0.01, 0.08) for m in ms}}, {m: 0.003 for m in ms})


class Weights(unittest.TestCase):
    def test_risk_parity_equal_contributions(self):
        s, _ = streams()
        c = P.cov([list(s[k].values()) for k in sorted(s)])
        w = P.w_riskparity(c)
        cw = P.mv(c, w)
        rc = [a * b for a, b in zip(w, cw)]
        for x in rc:
            self.assertAlmostEqual(x / sum(rc), 1 / 3, places=4)
        self.assertAlmostEqual(sum(w), 1.0)

    def test_correlated_sleeves_share_one_budget(self):
        rng = random.Random(3)
        base = [rng.gauss(0, 0.04) for _ in range(60)]
        cols = [base, [x + rng.gauss(0, 0.004) for x in base], [rng.gauss(0, 0.04) for _ in range(60)]]
        c = P.cov(cols)
        self.assertEqual(len(set(P.clusters(c))), 2)
        w = P.w_riskparity_merged(c)
        self.assertGreater(w[2], max(w[0], w[1]))              # the independent sleeve gets about half the risk

    def test_max_sharpe_respects_cap(self):
        s, _ = streams()
        cols = [list(s[k].values()) for k in sorted(s)]
        w = P.w_maxsharpe(P.cov(cols), [P.mean(x) for x in cols])
        self.assertLessEqual(max(w), P.CAP + 1e-9)
        self.assertAlmostEqual(sum(w), 1.0)


class OutOfSample(unittest.TestCase):
    def test_no_lookahead_shift(self):
        """Changing a month's returns must not change the weights applied in that month or before it."""
        s, tb = streams()
        for method in ("risk_parity", "inverse_vol", "max_sharpe"):
            a = P.run(s, tb, method)
            k = 80
            m = a["months"][k - P.LOOKBACK]
            s2 = {n: dict(v) for n, v in s.items()}
            for n in s2:
                s2[n][m] *= -5
            b = P.run(s2, tb, method)
            i = a["months"].index(m)
            self.assertEqual(a["weights"][:i + 1], b["weights"][:i + 1], method)

    def test_vol_target_caps_leverage(self):
        s, tb = streams()
        r = P.run(s, tb, "equal")
        self.assertTrue(all(sum(w) <= 1.0 + 1e-9 for w in r["weights"]))

    def test_bootstrap_reproducible(self):
        s, tb = streams()
        a = list(s["A"].values())
        b = list(s["B"].values())
        t = list(tb.values())
        self.assertEqual(P.paired_sharpe_diff(a, b, t, n=200), P.paired_sharpe_diff(a, b, t, n=200))

    def test_costs_lower_returns(self):
        s, tb = streams()
        hi = P.run(s, tb, "risk_parity", cost=0.01)["ret"]
        lo = P.run(s, tb, "risk_parity", cost=0.0)["ret"]
        self.assertLess(sum(hi), sum(lo))


class Sleeves(unittest.TestCase):
    def test_returns_and_tbill_use_prior_month(self):
        self.assertEqual(S.returns({"2020-01": 100.0, "2020-02": 110.0}), {"2020-02": 0.10000000000000009})
        tb = S.tbill([["2020-01-01", 1.2], ["2020-02-01", 2.4]])
        self.assertAlmostEqual(tb["2020-02"], 0.001)

    def test_trend_weekly_flat_in_downtrend(self):
        t0 = 1_500_000_000
        down = [[t0 + i * 7 * 86400, 100 * 0.98 ** i] for i in range(80)]
        tb = {m: 0.003 for m in months(40, 2017)}
        r = S.trend_weekly({"BTC": down, "ETH": down, "SOL": []}, tb)
        self.assertTrue(all(v >= 0 for v in r.values()))            # never long, earns only T-bills

    def test_metrics_basic(self):
        m = P.metrics([0.01] * 24, [0.0] * 24)
        self.assertAlmostEqual(m["cagr"], 1.01 ** 12 - 1, places=4)
        self.assertEqual(m["max_dd"], 0.0)
        self.assertTrue(math.isfinite(m["end_500"]))


if __name__ == "__main__":
    unittest.main()
