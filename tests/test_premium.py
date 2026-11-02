import math
import unittest

from options import premium as P


def leg(strike, kind, delta, bid, ask, oi=1000, iv=0.30, expiry="2026-12-11"):
    return {"strike": strike, "type": kind, "expiry": expiry, "delta": delta, "bid": bid, "ask": ask, "oi": oi, "iv": iv}


def chain(iv=0.30):
    c = [leg(100, "put", -0.50, 3.0, 3.1, iv=iv), leg(100, "call", 0.50, 3.0, 3.1, iv=iv),
         leg(95, "put", -0.22, 1.20, 1.25), leg(92.5, "put", -0.12, 0.36, 0.40), leg(90, "put", -0.08, 0.30, 0.33),
         leg(105, "call", 0.21, 1.10, 1.15), leg(107.5, "call", 0.11, 0.55, 0.58)]
    return {"spot": 100.0, "contracts": c}


def closes(vol=0.15, n=260, drift=0.001):
    out, p = [], 80.0
    for i in range(n):
        p *= math.exp(drift + (vol / math.sqrt(252)) * (1 if i % 2 else -1))
        out.append(p)
    return out


class PremiumTests(unittest.TestCase):
    def test_rv_of_alternating_series(self):
        r = P.rv(closes(vol=0.15, drift=0.0))
        self.assertAlmostEqual(r, 0.15 * math.sqrt(20 / 19), places=3)

    def test_uptrend_put_credit_spread_natural_fill(self):
        r = P.screen("T", chain(), closes(), today="2026-11-02")
        self.assertEqual((r["status"], r["structure"], r["trend"]), ("pass", "put credit spread", "up"), r["reason"])
        self.assertEqual(r["credit"], round(1.20 - 0.40, 2))      # sell 95 at bid, buy 92.5 at ask
        self.assertEqual(r["width"], 2.5)
        self.assertAlmostEqual(r["pop"], 0.78)

    def test_filters(self):
        self.assertIn("earnings", P.screen("T", chain(), closes(), earnings="2026-11-20", today="2026-11-02")["reason"])
        self.assertIn("IV/RV", P.screen("T", chain(iv=0.10), closes(), today="2026-11-02")["reason"])
        thin = chain()
        thin["contracts"][2]["oi"] = 10
        self.assertIn("thin", P.screen("T", thin, closes(), today="2026-11-02")["reason"])

    def test_mixed_trend_iron_condor(self):
        flat = closes(drift=0.0)
        r = P.screen("T", chain(), flat, today="2026-11-02")
        self.assertEqual(r["structure"], "iron condor")
        self.assertEqual(r["width"], 2.5)
        self.assertAlmostEqual(r["credit"], round((1.20 - 0.40) + (1.10 - 0.58), 2))

    def test_rank_orders_passes_first(self):
        a = {"status": "pass", "score": 1.0}
        b = {"status": "pass", "score": 2.0}
        c = {"status": "fail", "score": None}
        self.assertEqual(P.rank([a, c, b]), [b, a, c])


class MarkTests(unittest.TestCase):
    def setUp(self):
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location("pm", pathlib.Path(__file__).resolve().parents[1] / "scripts/premium_mark.py")
        self.pm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.pm)

    def test_legs_parse_and_natural_debit(self):
        pm = self.pm
        self.assertEqual(pm.legs("P -95 +92.5 (Δ0.22) / C -105 +107.5 (Δ0.21)"),
                         [("put", 95.0, 92.5), ("call", 105.0, 107.5)])
        pick = {"legs": "P -95 +92.5 (Δ0.22)", "expiry": "2026-12-11", "credit": 0.80, "max_loss": 1.70}
        c = chain()
        self.assertEqual(pm.debit(pick, c), round(1.25 - 0.36, 2))   # buy 95 at ask, sell 92.5 at bid

    def test_exit_rules(self):
        pm = self.pm
        pick = {"expiry": "2026-12-11", "credit": 0.80}
        self.assertEqual(pm.decide(pick, 0.40, "2026-11-10"), "take profit")
        self.assertEqual(pm.decide(pick, 1.60, "2026-11-10"), "stop")
        self.assertEqual(pm.decide(pick, 0.70, "2026-11-25"), "time exit")
        self.assertEqual(pm.decide(pick, 0.70, "2026-11-10"), "")


if __name__ == "__main__":
    unittest.main()
