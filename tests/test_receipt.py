import unittest

from fund import receipt
from fund.ledger import Ledger
from tests.test_fund import AFTER, OPEN, cfg


def ev(kind, ts, **kw):
    return {"kind": kind, "ts": ts.isoformat(), **kw}


class ReceiptTests(unittest.TestCase):
    def test_flat_book_is_clean(self):
        L = Ledger(100_000)
        L.mark("SPY", 700.0, OPEN)
        r = receipt.build(L, cfg(), [ev("mark", OPEN), ev("veto", OPEN)], AFTER, "close")
        self.assertTrue(r["clean"])
        self.assertEqual(r["fund_day"], "2026-09-24")
        self.assertEqual(r["counts"]["mark"], 1)
        self.assertEqual(r["counts"]["veto"], 1)  # a veto is the rules working, not a breach

    def test_other_days_not_counted(self):
        L = Ledger(100_000)
        L.mark("SPY", 700.0, OPEN)
        old = OPEN.replace(day=23)
        r = receipt.build(L, cfg(), [ev("mark", old)], AFTER)
        self.assertEqual(r["counts"]["mark"], 0)

    def test_oversized_position_is_breach(self):
        L = Ledger(100_000)
        L.fill("SPY", "buy", 20, 700.0, OPEN)  # 14% of NAV > 5% cap + 1pt drift
        r = receipt.build(L, cfg(), [], AFTER)
        self.assertFalse(r["clean"])
        self.assertEqual(r["breaches"][0]["rule"], "position_cap")

    def test_drift_allowance(self):
        L = Ledger(100_000)
        L.fill("SPY", "buy", 8, 700.0, OPEN)  # 5.6%: inside the 1-point drift allowance
        self.assertTrue(receipt.build(L, cfg(), [], AFTER)["clean"])

    def test_opening_fill_on_halted_day_is_breach(self):
        L = Ledger(100_000)
        L.fill("SPY", "buy", 7, 700.0, OPEN)
        L.mark("SPY", 700.0, OPEN)
        L.cash -= 4_000  # day P&L -4% (past the -3% halt)
        events = [ev("fill", OPEN, reducing=False)]
        rules = [b["rule"] for b in receipt.build(L, cfg(), events, AFTER)["breaches"]]
        self.assertIn("halted_entry", rules)
        exits = [ev("fill", OPEN, reducing=True)]
        rules = [b["rule"] for b in receipt.build(L, cfg(), exits, AFTER)["breaches"]]
        self.assertNotIn("halted_entry", rules)


if __name__ == "__main__":
    unittest.main()
