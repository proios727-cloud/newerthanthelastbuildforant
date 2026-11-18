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
        wide = chain()
        wide["contracts"][2].update(bid=1.10, ask=1.25)            # 12.8% of mid on the short leg
        self.assertIn("thin", P.screen("T", wide, closes(), today="2026-11-02")["reason"])
        ok = chain()
        ok["contracts"][2]["oi"] = 150                              # OI 150 passes once quotes are tight
        self.assertEqual(P.screen("T", ok, closes(), today="2026-11-02")["status"], "pass")

    def test_short_delta_must_be_in_band(self):
        c = chain()
        c["contracts"] = [x for x in c["contracts"] if not (x["type"] == "put" and x["strike"] < 100)]
        c["contracts"].append(leg(98, "put", -0.40, 2.0, 2.1))
        c["contracts"].append(leg(97, "put", -0.35, 1.6, 1.7))
        self.assertIn("delta", P.screen("T", c, closes(), today="2026-11-02")["reason"])

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

    def test_cash_secured_put(self):
        r = P.screen_put("T", chain(), closes(), today="2026-11-02")
        self.assertEqual((r["status"], r["structure"], r["legs"]), ("pass", "cash-secured put", "P -95 (Δ0.22)"), r["reason"])
        self.assertEqual((r["credit"], r["cash_needed"], r["breakeven"]), (1.20, 9500, 93.8))
        self.assertAlmostEqual(r["annualized"], round(1.20 / 95 * 365 / 39, 4))

    def test_put_not_sold_in_downtrend(self):
        down = list(reversed(closes()))
        self.assertIn("downtrend", P.screen_put("T", chain(), down, today="2026-11-02")["reason"])


    def test_screen_uses_one_expiry(self):
        c = chain()
        later = [dict(x, expiry="2026-12-18", bid=x["bid"] * 3, ask=x["ask"] * 3) for x in c["contracts"]]
        c["contracts"] = later + c["contracts"]                      # a second, later expiry must be ignored
        r = P.screen_put("T", c, closes(), today="2026-11-02")
        self.assertEqual((r["expiry"], r["credit"], r["strike"]), ("2026-12-11", 1.20, 95))

    def test_open_picks_reads_close_records(self):
        rows = [{"id": "a", "ticker": "SPY", "expiry": "2026-12-11"}, {"id": "b", "ticker": "QQQ", "expiry": "2026-12-11"},
                {"close_of": "a", "date": "2026-11-20", "debit": 3.0, "rule": "take profit"}]
        self.assertEqual([r["id"] for r in P.open_picks(rows)], ["b"])

    def test_pick_expiry(self):
        self.assertEqual(P.pick_expiry(["2026-11-20", "2026-12-11", "2026-12-18"], "2026-11-02"), "2026-12-11")
        self.assertEqual(P.pick_expiry(["2026-11-20"], "2026-11-02"), "2026-11-20")   # nothing 30-45 out: earliest
        # closest to 38 days, not the earliest in the window: 12-11 is 32 days out, 12-18 is 39
        self.assertEqual(P.pick_expiry(["2026-12-11", "2026-12-18"], "2026-11-09"), "2026-12-18")


class ChainIndexTests(unittest.TestCase):
    def test_newest_snapshot_per_symbol_and_expiry(self):
        import json, pathlib, tempfile
        from options import chain_index
        with tempfile.TemporaryDirectory() as d:
            def snap(name, asof, expiries):
                cs = [leg(100, "put", -0.2, 1, 1.1, expiry=e) for e in expiries]
                pathlib.Path(d, name).write_text(json.dumps({"symbol": "T", "spot": 100, "asof": asof, "contracts": cs}))
            snap("T-1.json", "2026-11-02T15:00", ["2026-12-11", "2026-12-18"])
            snap("T-2.json", "2026-11-03T15:00", ["2026-12-18"])
            idx = chain_index(d)
            self.assertEqual(idx[("T", "2026-12-11")][0].name, "T-1.json")   # still marked from the older snapshot
            self.assertEqual(idx[("T", "2026-12-18")][0].name, "T-2.json")
            self.assertEqual({c["expiry"] for c in idx[("T", "2026-12-11")][1]["contracts"]}, {"2026-12-11"})


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

    def test_single_leg_debit(self):
        pick = {"legs": "P -95 (Δ0.22)", "expiry": "2026-12-11", "credit": 1.20}
        self.assertEqual(self.pm.legs(pick["legs"]), [("put", 95.0, None)])
        self.assertEqual(self.pm.debit(pick, chain()), 1.25)                  # buy back at the ask

    def test_exit_rules(self):
        pm = self.pm
        pick = {"expiry": "2026-12-11", "credit": 0.80}
        self.assertEqual(pm.decide(pick, 0.40, "2026-11-10"), "take profit")
        self.assertEqual(pm.decide(pick, 1.60, "2026-11-10"), "stop")
        self.assertEqual(pm.decide(pick, 0.70, "2026-11-25"), "time exit")
        self.assertEqual(pm.decide(pick, 0.70, "2026-11-10"), "")


if __name__ == "__main__":
    unittest.main()
