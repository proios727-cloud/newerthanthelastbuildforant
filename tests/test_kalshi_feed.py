import unittest

import judge
from kalshi import feed, settlement

PAGE1 = {"markets": [
    {"ticker": "KXBTC15M-26SEP281215-15", "close_time": "2026-09-28T16:15:00Z", "yes_bid": 47, "no_bid": 48,
     "rules_primary": "Settles on CF Benchmarks BRTI ..."},
    {"ticker": "KXBTC15M-26SEP281230-30", "close_time": "2026-09-28T16:30:00Z",
     "yes_bid_dollars": "0.5100", "no_bid_dollars": "0.4800"},
], "cursor": "c2"}
PAGE2 = {"markets": [{"ticker": "KXBTC15M-EMPTY", "yes_bid": 0, "no_bid": 55}], "cursor": ""}


def fake(path, params):
    assert path == "/markets" and params["status"] == "open"
    return PAGE2 if params.get("cursor") == "c2" else PAGE1


class FeedTests(unittest.TestCase):
    def test_paginates_and_normalises_prices(self):
        ms = feed.open_markets("KXBTC15M", fake)
        self.assertEqual(len(ms), 3)
        self.assertEqual(feed._cents(ms[1], "yes_bid"), 51)

    def test_unverified_markets_are_never_quoted(self):
        rows = feed.scan(["KXBTC15M"], fetch=fake)
        self.assertEqual([r.ticker for r in rows], ["KXBTC15M-26SEP281215-15", "KXBTC15M-26SEP281230-30"])
        self.assertTrue(all(r.proposal is None and not r.settlement_ok for r in rows))
        self.assertEqual(rows[0].book_lock_c, 5)

    def test_verified_market_gets_inside_pair(self):
        rows = feed.scan(["KXBTC15M"], fetch=fake, verify=lambda m: True)
        self.assertEqual((rows[0].proposal.yes_bid, rows[0].proposal.no_bid), (48, 49))
        self.assertIsNone(rows[1].proposal)          # 51/48 locks 1¢ < 2¢ edge

    def test_propose_falls_back_to_joining(self):
        self.assertEqual(feed.propose(48, 49), feed.Quote(49, 49))
        self.assertIsNone(feed.propose(50, 49))

    def test_settlement_gate_with_live_answer(self):
        ok = judge.StubClient({"cfb_settlement": judge.Answer(True, 0.97, live=True)})
        m = {"ticker": "T", "asset": "BTC", "window_min": 15, "rules": "..."}
        self.assertTrue(settlement.verify(ok, m, {}))
        self.assertIn("unverified", feed.render(feed.scan(["KXBTC15M"], fetch=fake)))


if __name__ == "__main__":
    unittest.main()
