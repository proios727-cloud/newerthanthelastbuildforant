import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "desk_ledger", pathlib.Path(__file__).resolve().parents[1] / "scripts/desk_ledger.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)


class DeskLedgerTests(unittest.TestCase):
    def test_book_of(self):
        self.assertEqual(L.book_of({"source": "my actual fill"}), "Real account")
        self.assertEqual(L.book_of({"source": "screener paper log"}), "Paper: premium screener")
        self.assertEqual(L.book_of({"source": "paper LEAP (owner request)"}), "Paper: other")

    def test_money(self):
        self.assertEqual(L.money(443), "+$443")
        self.assertEqual(L.money(-198), "−$198")
        self.assertEqual(L.money(None), "—")

    def test_mark_uses_bid_for_long_and_ask_for_short(self):
        idx = {("KO", "2026-12-18"): ("p", {"contracts": [
            {"type": "call", "strike": 100.0, "bid": 2.34, "ask": 2.42}]})}
        self.assertEqual(L.mark(idx, "KO", "2026-12-18", 100, "call", "long"), 2.34)
        self.assertEqual(L.mark(idx, "KO", "2026-12-18", 100, "call", "short"), 2.42)
        self.assertIsNone(L.mark(idx, "KO", "2027-01-15", 100, "call", "long"))


if __name__ == "__main__":
    unittest.main()
