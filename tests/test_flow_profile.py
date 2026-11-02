import unittest

from chart import Bar
from chart.profile import profile
from options import flow


def chain(contracts, spot=100.0, asof="2026-11-02T17:00:00Z"):
    return {"symbol": "T", "spot": spot, "asof": asof, "contracts": contracts}


def c(strike, kind, oi, vol=0, gamma=0.05, iv=0.2, bid=1.0, ask=1.2, expiry="2026-11-03"):
    return {"strike": strike, "type": kind, "expiry": expiry, "oi": oi, "volume": vol, "iv": iv, "gamma": gamma,
            "bid": bid, "ask": ask}


class FlowTests(unittest.TestCase):
    def test_call_adds_put_subtracts_gex(self):
        rows = flow.strike_table(chain([c(100, "call", 1000), c(100, "put", 400)]))
        r = next(x for x in rows if x["expiry"] == "2026-11-03")
        expected = (1000 - 400) * 0.05 * 100 * 100 * 100 * 0.01
        self.assertAlmostEqual(r["net_gex"], round(expected))

    def test_premium_is_volume_times_mid(self):
        rows = flow.strike_table(chain([c(100, "call", 0, vol=10, bid=1.0, ask=1.2), c(100, "put", 0, vol=4, bid=2, ask=2)]))
        r = rows[0]
        self.assertEqual((r["call_premium"], r["put_premium"], r["net_premium"]), (1100, 800, 300))

    def test_all_rollup_and_expiry_table(self):
        rows = flow.strike_table(chain([c(100, "call", 100, vol=5), c(100, "call", 50, vol=5, expiry="2026-11-06"),
                                        c(95, "put", 80, vol=20)]))
        all100 = next(x for x in rows if x["expiry"] == "all" and x["strike"] == 100)
        self.assertEqual(all100["call_oi"], 150)
        exp = {e["expiry"]: e for e in flow.expiry_table(rows)}
        self.assertEqual(set(exp), {"all", "2026-11-03", "2026-11-06"})
        self.assertAlmostEqual(exp["all"]["put_call_volume"], 20 / 10)

    def test_vanna_sign_flips_across_the_money(self):
        T = 5 / 365
        self.assertGreater(flow.bs_vanna(100, 105, T, 0.2), 0)   # OTM call: delta rises with vol
        self.assertLess(flow.bs_vanna(100, 95, T, 0.2), 0)


def bars(rows):
    return [Bar(f"2026-11-02T{9 + i // 4:02d}:{(i % 4) * 15:02d}:00-05:00", o, h, l, cl, v)
            for i, (o, h, l, cl, v) in enumerate(rows)]


class ProfileTests(unittest.TestCase):
    def test_poc_and_nodes(self):
        rows = [(100, 101, 100, 100.5, 1000)] * 10 + [(103, 104, 103, 103.5, 1000)] * 10 + [(101, 103, 101, 102, 30)]
        p = profile(bars(rows), bin_size=0.5)
        self.assertIn(p["poc"], (100.25, 100.75, 103.25, 103.75))
        nodes = {r["price"]: r["node"] for r in p["bins"]}
        self.assertIn("LVN", [nodes[k] for k in nodes if 101.5 <= k <= 102.5])
        self.assertIn("HVN", nodes.values())

    def test_value_area_holds_70_percent(self):
        rows = [(100 + i % 5, 100.4 + i % 5, 100 + i % 5, 100.2 + i % 5, 100 + 900 * (i % 5 == 2)) for i in range(40)]
        p = profile(bars(rows), bin_size=0.5)
        inside = sum(r["volume"] for r in p["bins"] if p["val"] <= r["price"] <= p["vah"])
        self.assertGreaterEqual(inside, 0.7 * sum(r["volume"] for r in p["bins"]) - 1)


if __name__ == "__main__":
    unittest.main()
