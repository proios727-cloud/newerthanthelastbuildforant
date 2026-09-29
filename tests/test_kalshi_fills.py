import unittest

from kalshi import fills


def t(side, yes, qty):
    return {"taker_side": side, "yes_price_dollars": f"{yes / 100:.4f}",
            "no_price_dollars": f"{(100 - yes) / 100:.4f}", "count_fp": str(qty)}


class FillTests(unittest.TestCase):
    def test_vwap_only_counts_takers_buying_the_side(self):
        trades = [t("yes", 96, 10), t("yes", 98, 30), t("no", 97, 500)]
        self.assertEqual(fills.taker_vwap(trades, "yes"), (98, 40.0))   # (96·10 + 98·30)/40 = 97.5 → 98
        self.assertEqual(fills.taker_vwap(trades, "no"), (3, 500.0))

    def test_price_entry_uses_print_not_candle(self):
        snap = {"ticker": "X", "side": "yes", "ask": 95, "won": True}
        r = fills.price_entry(snap, [t("yes", 98, 5)])
        self.assertEqual((r["fill"], r["pnl_c"]), (98, 1))              # 100 − 98 − 1¢ fee
        r = fills.price_entry({**snap, "won": False}, [t("yes", 98, 5)])
        self.assertEqual(r["pnl_c"], -99)

    def test_no_prints_means_unfilled(self):
        r = fills.price_entry({"side": "no", "won": True}, [t("yes", 50, 5)])
        self.assertIsNone(r["fill"])
        self.assertIsNone(r["pnl_c"])


if __name__ == "__main__":
    unittest.main()
