import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta

from fund import clock, config, preview, risk
from fund.ledger import Ledger

ET = clock.ET
ROOT = pathlib.Path(__file__).resolve().parent.parent


def et(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


# Thu 2026-09-24 10:00 ET — equity session open
OPEN = et(2026, 9, 24, 10)
# Thu 2026-09-24 20:00 ET — equities closed, crypto open
AFTER = et(2026, 9, 24, 20)


def cfg(mode="PAPER"):
    desk = json.loads((ROOT / "desk.json").read_text())
    desk["mode"] = mode
    return config.from_dict(desk)


def order(sym, side, qty, px, ts, spread_bps=2.0, **kw):
    half = px * spread_bps / 2e4
    return risk.Order(sym, side, qty, px, ts, bid=px - half, ask=px + half, **kw)


class ClockTests(unittest.TestCase):
    def test_equity_session(self):
        self.assertTrue(clock.equity_session_open(OPEN))
        self.assertFalse(clock.equity_session_open(et(2026, 9, 24, 9, 29)))
        self.assertTrue(clock.equity_session_open(et(2026, 9, 24, 9, 30)))
        self.assertFalse(clock.equity_session_open(et(2026, 9, 24, 16, 0)))
        self.assertFalse(clock.equity_session_open(et(2026, 9, 26, 11)))  # Saturday

    def test_crypto_always(self):
        self.assertTrue(clock.can_trade("crypto", et(2026, 9, 26, 3)))

    def test_naive_rejected(self):
        with self.assertRaises(ValueError):
            clock.equity_session_open(datetime(2026, 9, 24, 10))


class LedgerTests(unittest.TestCase):
    def test_buy_mark_sell_realized(self):
        L = Ledger(100_000)
        L.fill("SPY", "buy", 10, 700, OPEN, fee=1)
        self.assertEqual(L.cash, 100_000 - 7000 - 1)
        L.mark("SPY", 710, OPEN + timedelta(minutes=5))
        self.assertAlmostEqual(L.nav(), 100_000 - 1 + 100)
        L.fill("SPY", "sell", 4, 720, OPEN + timedelta(minutes=10))
        p = L.positions["SPY"]
        self.assertEqual(p["qty"], 6)
        self.assertEqual(p["avg_cost"], 700)
        self.assertAlmostEqual(p["realized"], 4 * 20 - 1)

    def test_avg_cost_and_flip(self):
        L = Ledger(100_000)
        L.fill("NVDA", "buy", 10, 100, OPEN)
        L.fill("NVDA", "buy", 10, 120, OPEN)
        self.assertEqual(L.positions["NVDA"]["avg_cost"], 110)
        L.fill("NVDA", "sell", 25, 130, OPEN)   # close 20 @ +20, open short 5 @ 130
        p = L.positions["NVDA"]
        self.assertEqual(p["qty"], -5)
        self.assertEqual(p["avg_cost"], 130)
        self.assertAlmostEqual(p["realized"], 400)

    def test_short_pnl(self):
        L = Ledger(100_000)
        L.fill("TSLA", "sell", 10, 300, OPEN)
        L.mark("TSLA", 280, OPEN)
        self.assertAlmostEqual(L.nav(), 100_200)
        self.assertAlmostEqual(L.gross(), 2800)

    def test_equity_mark_holds_after_hours_while_crypto_moves(self):
        L = Ledger(100_000)
        L.fill("SPY", "buy", 10, 700, OPEN)
        L.fill("BTC/USD", "buy", 0.1, 80_000, OPEN)
        L.mark("SPY", 710, et(2026, 9, 24, 15, 59))       # last equity mark of the session
        L.mark("BTC/USD", 82_000, AFTER)                   # crypto moves overnight
        self.assertEqual(L.price("SPY"), 710)
        self.assertAlmostEqual(L.nav(), 100_000 + 100 + 200)

    def test_day_roll_at_midnight_et(self):
        L = Ledger(100_000)
        L.fill("BTC/USD", "buy", 1, 80_000, et(2026, 9, 24, 23, 0))
        L.mark("BTC/USD", 81_000, et(2026, 9, 24, 23, 59))
        self.assertEqual(L.day["date"], "2026-09-24")
        self.assertAlmostEqual(L.day_pnl(), 1000)
        L.mark("BTC/USD", 79_000, et(2026, 9, 25, 0, 1))   # roll snapshots NAV at 81k first
        self.assertEqual(L.day["date"], "2026-09-25")
        self.assertAlmostEqual(L.day["start_nav"], 101_000)
        self.assertAlmostEqual(L.day_pnl(), -2000)

    def test_peak_and_drawdown(self):
        L = Ledger(100_000)
        L.fill("BTC/USD", "buy", 1, 80_000, AFTER)
        L.mark("BTC/USD", 90_000, AFTER)
        self.assertEqual(L.peak_nav, 110_000)
        L.mark("BTC/USD", 79_000, AFTER)
        self.assertAlmostEqual(L.drawdown_pct(), 100 * 11_000 / 110_000)

    def test_persistence_roundtrip(self):
        L = Ledger(100_000)
        L.fill("ETH/USD", "buy", 2, 3000, AFTER, fee=6)
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "state.json"
            L.save(p)
            M = Ledger.load(p)
        self.assertEqual(M.to_dict(), L.to_dict())

    def test_rejects_bad_fill(self):
        with self.assertRaises(ValueError):
            Ledger(1).fill("SPY", "hold", 1, 1, OPEN)
        with self.assertRaises(ValueError):
            Ledger(1).fill("SPY", "buy", 0, 1, OPEN)


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.c = cfg()
        self.L = Ledger(self.c.starting_nav)

    def test_position_cap_sizes_down(self):
        v = risk.check(order("SPY", "buy", 100, 700, OPEN), self.L, self.c, OPEN)
        self.assertTrue(v.passed)
        self.assertEqual(v.max_qty, 7)            # 5% of 100k = 5000 / 700 → 7 shares
        self.assertEqual(v.rules[0][0], "sized_down")

    def test_crypto_fractional(self):
        v = risk.check(order("BTC/USD", "buy", 1, 80_000, AFTER), self.L, self.c, AFTER)
        self.assertTrue(v.passed)
        self.assertAlmostEqual(v.max_qty, 0.0625)

    def test_universe(self):
        v = risk.check(order("DOGE/USD", "buy", 1, 0.1, AFTER), self.L, self.c, AFTER)
        self.assertEqual(v.rules[0][0], "universe")

    def test_equity_after_hours_vetoed(self):
        v = risk.check(order("SPY", "buy", 1, 700, AFTER), self.L, self.c, AFTER)
        self.assertEqual(v.rules[0][0], "session")

    def test_stale_quote(self):
        v = risk.check(order("SPY", "buy", 1, 700, OPEN - timedelta(minutes=5)), self.L, self.c, OPEN)
        self.assertEqual(v.rules[0][0], "stale_quote")

    def test_wide_spread(self):
        v = risk.check(order("SPY", "buy", 1, 700, OPEN, spread_bps=25), self.L, self.c, OPEN)
        self.assertEqual(v.rules[0][0], "spread")

    def test_position_cap_full_vetoes(self):
        for s in ("SPY", "QQQ", "IWM"):
            self.L.fill(s, "buy", 10, 500, OPEN)        # 5% each; SPY is already at its 5% cap
        v = risk.check(order("SPY", "buy", 5, 500, OPEN), self.L, self.c, OPEN)
        self.assertEqual(v.rules[0][0], "position_cap")
        self.assertFalse(v.passed)

    def test_group_cap_binds_before_position_cap(self):
        self.c = cfg()
        object.__setattr__(self.c.limits, "max_position_pct", 15)
        self.L.fill("SPY", "buy", 30, 500, OPEN)      # 15k = 15% of the Index ETF group
        v = risk.check(order("QQQ", "buy", 100, 500, OPEN), self.L, self.c, OPEN)
        self.assertTrue(v.passed)
        self.assertEqual(v.max_qty, 10)               # 20% − 15% = 5k → 10 shares
        self.assertIn("group_cap", v.rules[0][1])

    def test_gross_cap(self):
        object.__setattr__(self.c.limits, "max_position_pct", 100)
        object.__setattr__(self.c.limits, "max_group_pct", 100)
        self.L.fill("BTC/USD", "buy", 1, 80_000, AFTER)
        self.L.fill("ETH/USD", "buy", 20, 3000, AFTER)   # gross 140k
        v = risk.check(order("SOL/USD", "buy", 1000, 100, AFTER), self.L, self.c, AFTER)
        self.assertTrue(v.passed)
        self.assertAlmostEqual(v.max_qty, 100)           # 150k − 140k = 10k → 100 SOL
        self.assertIn("gross_cap", v.rules[0][1])

    def test_adv_cap(self):
        v = risk.check(order("SPY", "buy", 5, 700, OPEN, adv=200), self.L, self.c, OPEN)
        self.assertEqual(v.max_qty, 2)                    # 1% of 200

    def test_day_loss_halt_blocks_entries_not_exits(self):
        self.L.fill("BTC/USD", "buy", 0.5, 80_000, et(2026, 9, 24, 19))
        self.L.mark("BTC/USD", 73_000, AFTER)             # −3500 = −3.5% day
        v = risk.check(order("ETH/USD", "buy", 1, 3000, AFTER), self.L, self.c, AFTER)
        self.assertEqual(v.rules[0][0], "day_loss_halt")
        exit_ = risk.check(order("BTC/USD", "sell", 0.5, 73_000, AFTER), self.L, self.c, AFTER)
        self.assertTrue(exit_.passed and exit_.reducing)

    def test_drawdown_halt(self):
        self.L.fill("BTC/USD", "buy", 1, 80_000, et(2026, 9, 23, 20))
        self.L.mark("BTC/USD", 69_000, et(2026, 9, 23, 23))   # −11k on the 23rd
        self.L.mark("BTC/USD", 69_100, AFTER)                  # new day, day P&L ~0
        v = risk.check(order("ETH/USD", "buy", 1, 3000, AFTER), self.L, self.c, AFTER)
        self.assertEqual(v.rules[0][0], "drawdown_halt")

    def test_event_blackout(self):
        ev = OPEN + timedelta(minutes=10)
        v = risk.check(order("SPY", "buy", 1, 700, OPEN), self.L, self.c, OPEN, events=[ev])
        self.assertEqual(v.rules[0][0], "event_blackout")
        later = OPEN + timedelta(minutes=30)
        self.assertTrue(risk.check(order("SPY", "buy", 1, 700, OPEN), self.L, self.c, OPEN, events=[later]).passed)

    def test_short_entry_capped(self):
        v = risk.check(order("TSLA", "sell", 100, 250, OPEN), self.L, self.c, OPEN)
        self.assertEqual(v.max_qty, 20)
        self.assertFalse(v.reducing)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.c = cfg()
        self.L = Ledger(self.c.starting_nav)

    def test_preview_then_execute_fills_paper(self):
        p = preview.build(order("SPY", "buy", 5, 700, OPEN), self.L, self.c, OPEN, stop=690, target=720)
        self.assertEqual(p["status"], "awaiting_approval")
        self.assertEqual(self.L.fills, [])                 # nothing happens before approval
        rec = preview.approve(p, "EXECUTE", self.L, self.c, OPEN + timedelta(minutes=2))
        self.assertEqual(p["status"], "filled_paper")
        self.assertEqual(rec["qty"], 5)
        self.assertEqual(self.L.qty("SPY"), 5)

    def test_wrong_word(self):
        p = preview.build(order("SPY", "buy", 5, 700, OPEN), self.L, self.c, OPEN)
        for w in ("execute", "yes", "EXECUTE "):
            with self.assertRaises(preview.GateError):
                preview.approve(p, w, self.L, self.c, OPEN)
        self.assertEqual(self.L.fills, [])

    def test_stale_preview(self):
        p = preview.build(order("SPY", "buy", 5, 700, OPEN), self.L, self.c, OPEN)
        with self.assertRaises(preview.GateError):
            preview.approve(p, "EXECUTE", self.L, self.c, OPEN + timedelta(minutes=6))
        self.assertEqual(p["status"], "stale")

    def test_vetoed_order_gets_no_preview(self):
        with self.assertRaises(preview.GateError):
            preview.build(order("SPY", "buy", 5, 700, AFTER), self.L, self.c, AFTER)

    def test_recheck_catches_book_change(self):
        p = preview.build(order("SPY", "buy", 7, 700, OPEN), self.L, self.c, OPEN)
        self.L.fill("SPY", "buy", 7, 700, OPEN)            # another fill fills the cap first
        with self.assertRaises(preview.GateError):
            preview.approve(p, "EXECUTE", self.L, self.c, OPEN + timedelta(minutes=1))
        self.assertEqual(p["status"], "vetoed")

    def test_live_mode_refuses(self):
        c = cfg("LIVE")
        p = preview.build(order("SPY", "buy", 1, 700, OPEN), self.L, c, OPEN)
        with self.assertRaises(preview.GateError):
            preview.approve(p, "EXECUTE", self.L, c, OPEN)
        self.assertEqual(self.L.fills, [])

    def test_crypto_fee(self):
        p = preview.build(order("ETH/USD", "buy", 1, 3000, AFTER), self.L, self.c, AFTER)
        self.assertAlmostEqual(p["est_fee"], round(p["limit"] * 0.001, 2))


if __name__ == "__main__":
    unittest.main()
