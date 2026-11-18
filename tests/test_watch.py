import unittest

from options.watch import board, liquidity, pace, score, session_frac


def snap(sym="X", asof="2026-11-17T16:30:00Z", spot=100.0, cs=None):
    return {"symbol": sym, "asof": asof, "spot": spot, "contracts": cs or []}


def c(strike, kind="call", bid=1.0, ask=1.04, oi=1000, vol=100, iv=0.30, delta=0.5):
    return {"strike": strike, "type": kind, "bid": bid, "ask": ask, "oi": oi, "volume": vol, "iv": iv, "delta": delta}


class WatchTest(unittest.TestCase):
    def test_session_frac(self):
        self.assertAlmostEqual(session_frac("2026-11-17T17:45:00Z"), 0.5)  # 12:45 ET, halfway
        self.assertEqual(session_frac("2026-11-17T21:30:00Z"), 1.0)        # after the close
        self.assertEqual(session_frac("2026-11-17T14:31:00Z"), 0.1)        # floored early

    def test_liquidity_grades(self):
        self.assertEqual(liquidity(snap(cs=[c(100)]))[0], "A")
        self.assertEqual(liquidity(snap(cs=[c(100, bid=1.0, ask=1.09, oi=600, vol=30)]))[0], "B")
        self.assertEqual(liquidity(snap(cs=[c(100, bid=1.0, ask=1.5)]))[0], "F")

    def test_pace_is_per_open_interest(self):
        # Same activity on twice the strikes reads the same.
        self.assertAlmostEqual(pace(snap(cs=[c(100)])), pace(snap(cs=[c(100), c(105)])))

    def test_relative_volume_and_lean(self):
        hist = [snap(asof=f"2026-11-1{d}T21:00:00Z", cs=[c(100), c(100, "put")]) for d in range(0, 6)]
        now = snap(asof="2026-11-17T21:00:00Z", cs=[c(100, vol=500), c(100, "put", vol=100)])
        r = score(now, hist)
        self.assertAlmostEqual(r["rel_volume"], 3.0)
        self.assertAlmostEqual(r["call_share"], 500 / 600)
        self.assertIn("3.0x volume", r["signals"])
        self.assertIn("call-heavy", r["signals"])

    def test_lean_blank_when_one_sided(self):
        r = score(snap(cs=[c(100, "put"), c(95, "put"), c(90, "put"), c(100)]), [])
        self.assertIsNone(r["call_share"])

    def test_board_drops_illiquid_and_tags(self):
        rows = [dict(ticker="A", liq="A", action=1.0), dict(ticker="B", liq="F", action=9.0),
                dict(ticker="C", liq="B", action=2.0)]
        b = board(rows, held={"A"}, new={"C"})
        self.assertEqual([r["ticker"] for r in b], ["C", "A"])
        self.assertEqual((b[0]["source"], b[1]["held"]), ("new", "yes"))


class HeldTest(unittest.TestCase):
    def test_only_real_account_counts(self):
        import csv, tempfile, pathlib, sys
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
        import watchlist
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "ledger.csv"
            with open(p, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["book", "ticker", "status"])
                w.writeheader()
                w.writerows([{"book": "Paper: swing buyer", "ticker": "KO", "status": "open"},
                             {"book": "Real account", "ticker": "SPY", "status": "open"},
                             {"book": "Real account", "ticker": "QQQ", "status": "closed"}])
            self.assertEqual(watchlist.held_tickers(p), {"SPY"})


if __name__ == "__main__":
    unittest.main()
