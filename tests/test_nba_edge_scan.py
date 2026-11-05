import importlib.util
import os
import unittest

_P = os.path.join(os.path.dirname(__file__), "..", "skills", "nba-edge-scan", "scripts", "nba_edge_scan.py")
_spec = importlib.util.spec_from_file_location("nba_edge_scan", _P)
nes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nes)


def mk(ticker, event, bid, ask, size=100):
    return {"ticker": ticker, "event_ticker": event, "title": ticker, "status": "active",
            "yes_bid_dollars": f"{bid:.4f}", "yes_ask_dollars": f"{ask:.4f}",
            "yes_bid_size_fp": str(size), "yes_ask_size_fp": str(size)}


class TestNbaEdgeScan(unittest.TestCase):
    def test_fee_matches_kalshi_schedule(self):
        self.assertAlmostEqual(nes.kalshi_fee(0.5), 0.02)
        self.assertAlmostEqual(nes.kalshi_fee(0.95), 0.01)

    def test_ladder_keys(self):
        ev = "KXNBATOTAL-26NOV05MIAGSW"
        self.assertEqual(nes.ladder_key("KXNBATOTAL", mk(ev + "-221", ev, .4, .5)), ((("KXNBATOTAL", ev, "over")), 220.5))
        ev = "KXNBASPREAD-26NOV05MIAGSW"
        self.assertEqual(nes.ladder_key("KXNBASPREAD", mk(ev + "-GSW5", ev, .4, .5))[1], 4.5)
        ev = "KXNBAPTS-26NOV05MIAGSW"
        key, k = nes.ladder_key("KXNBAPTS", mk(ev + "-GSWSCURRY30-25", ev, .4, .5))
        self.assertEqual((key[2], k), ("GSWSCURRY30", 24.5))

    def test_lock_found_only_when_ladder_breaks(self):
        ev = "KXNBATOTAL-26NOV05MIAGSW"
        rungs = [dict(nes.quote(mk(ev + "-220", ev, .55, .57)), k=219.5),
                 dict(nes.quote(mk(ev + "-224", ev, .60, .62)), k=223.5)]   # higher line priced higher: broken
        locks = nes.find_locks({("t", ev, "over"): rungs})
        self.assertEqual(len(locks), 1)
        self.assertAlmostEqual(locks[0]["gain"], 0.03)
        rungs[1].update(bid=.40, ask=.42)
        self.assertEqual(nes.find_locks({("t", ev, "over"): rungs}), [])

    def test_book_edge_net_of_fee(self):
        markets = {"KXNBAGAME": [mk("KXNBAGAME-26NOV05MIAGSW-GSW", "KXNBAGAME-26NOV05MIAGSW", .60, .61)]}
        books = [{"kalshi_event_suffix": "26NOV05MIAGSW", "ml_fair": {"GSW": 0.66}}]
        e = nes.book_edges(markets, books)
        self.assertEqual(e[0]["side"], "YES")
        self.assertAlmostEqual(e[0]["edge"], 0.66 - 0.61 - nes.kalshi_fee(0.61))
        books[0]["ml_fair"]["GSW"] = 0.615
        self.assertEqual(nes.book_edges(markets, books), [])


if __name__ == "__main__":
    unittest.main()
