import unittest

import options


class GreeksTests(unittest.TestCase):
    def test_put_call_parity_and_textbook_value(self):
        c = options.greeks(100, 100, 1, 0.2, "call", r=0.05)
        p = options.greeks(100, 100, 1, 0.2, "put", r=0.05)
        self.assertAlmostEqual(c.price, 10.4506, places=3)          # Hull's standard example
        self.assertAlmostEqual(c.price - p.price, 100 - 100 * 2.718281828 ** -0.05, places=6)
        self.assertAlmostEqual(c.delta - p.delta, 1.0, places=9)
        self.assertAlmostEqual(c.gamma, p.gamma, places=12)
        self.assertLess(c.theta, 0)

    def test_expired_is_intrinsic(self):
        self.assertEqual(options.greeks(105, 100, 0, 0.2, "call").price, 5)
        self.assertEqual(options.greeks(105, 100, 0, 0.2, "put").delta, 0.0)
        with self.assertRaises(ValueError):
            options.greeks(100, 100, 1, 0.2, "straddle")

    def test_implied_vol_round_trips(self):
        for kind in ("call", "put"):
            px = options.greeks(750, 755, 7 / 365, 0.18, kind).price
            self.assertAlmostEqual(options.implied_vol(px, 750, 755, 7 / 365, kind), 0.18, places=4)
        self.assertIsNone(options.implied_vol(0.0, 750, 700, 7 / 365, "call"))   # below intrinsic

    def test_matches_recorded_broker_delta(self):
        ch = options.load_chain("SPY-2026-08-03T1506.json")
        c = next(x for x in ch["contracts"] if x["strike"] == 752.0 and x["option_type"] == "call")
        T = 5 / (365 * 24)   # ~5 trading hours left on the 0DTE at 11:06 ET
        g = options.greeks(ch["spot"], c["strike"], T, c["iv"], "call", r=0.0)
        self.assertAlmostEqual(g.delta, c["delta"], delta=0.06)


class GexTests(unittest.TestCase):
    def test_map_on_recorded_chain(self):
        ch = options.load_chain("SPY-2026-08-03T1506.json")
        m = options.gex_map(ch)
        strikes = {c["strike"] for c in ch["contracts"]}
        self.assertIn(m.king, strikes)
        self.assertIn(m.call_wall, strikes)
        self.assertIn(m.put_wall, strikes)
        self.assertIn(options.regime(m), ("positive_gamma", "negative_gamma"))

    def test_flip_and_walls_on_synthetic_chain(self):
        ch = {"spot": 100.0, "contracts": [
            {"strike": 95, "option_type": "put", "gamma": 0.05, "open_interest": 1000},
            {"strike": 100, "option_type": "call", "gamma": 0.02, "open_interest": 1000},
            {"strike": 105, "option_type": "call", "gamma": 0.06, "open_interest": 1000},
        ]}
        m = options.gex_map(ch)
        self.assertEqual((m.put_wall, m.call_wall, m.king, m.flip), (95.0, 105.0, 105.0, 105.0))
        self.assertEqual(options.regime(m), "positive_gamma")
        with self.assertRaises(ValueError):
            options.gex_map({"spot": 1, "contracts": []})


if __name__ == "__main__":
    unittest.main()
