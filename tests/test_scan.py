import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from fund import clock, config, scan
from fund.ledger import Ledger

ET = clock.ET
ROOT = pathlib.Path(__file__).resolve().parent.parent
DESK = json.loads((ROOT / "desk.json").read_text())
SC = scan.scan_config(DESK["fund"])
UNI = DESK["fund"]["universe"]
T0 = datetime(2026, 9, 24, 20, 0, tzinfo=ET)   # equities closed, crypto open


def wiggle(n, base=100.0, amp=0.3):
    return [base + (amp if i % 2 else -amp) for i in range(n)]


class SignalTests(unittest.TestCase):
    def test_needs_history(self):
        self.assertEqual(scan.signals_for("BTC/USD", wiggle(SC["min_obs"] - 1), SC), [])

    def test_range_break_is_trend_not_reversion(self):
        p = wiggle(25, amp=0.5) + [100.4, 99.6, 102.5]
        got = {s["setup"]: s["side"] for s in scan.signals_for("ETH/USD", p, SC)}
        self.assertEqual(got.get("breakout"), "buy")
        self.assertNotIn("mean_reversion", got)

    def test_quiet_series_has_no_signal(self):
        self.assertEqual(scan.signals_for("BTC/USD", wiggle(30), SC), [])

    def test_breakout_and_momentum_long(self):
        p = wiggle(25) + [101.0, 101.6, 102.2]
        got = {s["setup"]: s for s in scan.signals_for("BTC/USD", p, SC)}
        self.assertEqual(got["breakout"]["side"], "buy")
        self.assertEqual(got["momentum"]["side"], "buy")
        b = got["breakout"]
        self.assertLess(b["stop"], b["price"])
        self.assertAlmostEqual(b["target"] - b["price"], SC["reward_risk"] * (b["price"] - b["stop"]))

    def test_mean_reversion_short_targets_average(self):
        p = wiggle(25, amp=0.5) + [103.0, 100.4, 99.6, 100.4, 102.6]   # spike sets the range high; last stays inside it
        got = scan.signals_for("ETH/USD", p, SC)
        mr = [s for s in got if s["setup"] == "mean_reversion"]
        self.assertTrue(mr)
        self.assertNotIn("breakout", {s["setup"] for s in got})
        self.assertEqual(mr[0]["side"], "sell")
        self.assertLess(mr[0]["target"], mr[0]["price"])
        self.assertGreater(mr[0]["stop"], mr[0]["price"])

    def test_scan_ranks_and_filters(self):
        up = wiggle(25) + [101.0, 101.6, 102.2]
        down = wiggle(25) + [99.0, 98.4, 97.8]
        hist = {"BTC/USD": up, "ETH/USD": down, "SOL/USD": wiggle(30)}
        ranked = scan.scan(hist, UNI, {}, SC)
        self.assertEqual({s["symbol"] for s in ranked}, {"BTC/USD", "ETH/USD"})
        self.assertEqual(len({s["symbol"] for s in ranked}), len(ranked))   # one per symbol
        self.assertEqual(ranked, sorted(ranked, key=lambda s: -s["score"]))
        # no shorts when disallowed; no adding to an existing long
        self.assertNotIn("ETH/USD", {s["symbol"] for s in scan.scan(hist, UNI, {}, {**SC, "allow_short": False})})
        self.assertNotIn("BTC/USD", {s["symbol"] for s in scan.scan(hist, UNI, {"BTC/USD": {"qty": 1}}, SC)})


class BookTests(unittest.TestCase):
    def sig(self):
        return {"symbol": "BTC/USD", "side": "buy", "setup": "breakout", "score": 2.0, "price": 100.0,
                "stop": 98.0, "target": 104.0, "why": "test"}

    def test_lifecycle_and_timeouts(self):
        b = scan.new_book()
        s = scan.post(b, [self.sig()], T0, SC)[0]
        self.assertEqual(b["counts"]["scanned"], 1)
        with self.assertRaises(ValueError):
            scan.attach_thesis(b, s["id"], "  ", None, T0, SC)
        with self.assertRaises(ValueError):
            scan.attach_thesis(b, s["id"], "trend day", 101.0, T0, SC)   # invalidation on the wrong side
        scan.attach_thesis(b, s["id"], "trend day", 99.0, T0, SC)
        self.assertEqual(b["signals"][s["id"]]["status"], "thesis")
        scan.expire(b, T0 + timedelta(minutes=SC["thesis_ttl_min"] + 1), SC)
        self.assertEqual(b["signals"][s["id"]]["status"], "expired")

    def test_unthesised_signals_expire_and_get_replaced(self):
        b = scan.new_book()
        s1 = scan.post(b, [self.sig()], T0, SC)[0]
        s2 = scan.post(b, [self.sig()], T0 + timedelta(minutes=5), SC)[0]
        self.assertEqual(b["signals"][s1["id"]]["status"], "replaced")
        with self.assertRaises(ValueError):
            scan.attach_thesis(b, s2["id"], "late", None, T0 + timedelta(minutes=SC["signal_ttl_min"] + 6), SC)
        self.assertEqual(b["signals"][s2["id"]]["status"], "expired")

    def test_risk_qty_uses_invalidation(self):
        s = {**self.sig(), "thesis": {"invalidation": 99.0}}
        qty, stop = scan.risk_qty(s, 100000, SC)
        self.assertEqual(stop, 99.0)
        self.assertAlmostEqual(qty, SC["risk_per_trade_pct"] / 100 * 100000 / 1.0)

    def test_history_roundtrip_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            h = pathlib.Path(d) / "h.jsonl"
            ts = [(T0 + timedelta(minutes=i)).isoformat() for i in range(3)]
            scan.record(h, [{"symbol": "BTC/USD", "price": 1.0 + i, "ts": t} for i, t in enumerate(ts)])
            scan.record(h, [{"symbol": "BTC/USD", "price": 2.0, "ts": ts[1]}])
            self.assertEqual(scan.load_history(h)["BTC/USD"], [1.0, 2.0, 3.0])


class ChainTests(unittest.TestCase):
    """scan → thesis → preview-signal → approve, end to end through the CLI."""

    def test_chain(self):
        from fund import __main__ as cli
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            paths = {"DIR": d, "STATE": d / "state.json", "PREVIEWS": d / "previews.json", "EVENTS": d / "events.jsonl",
                     "FEED": d / "feed.json", "HISTORY": d / "history.jsonl", "SIGNALS": d / "signals.json"}
            prices = wiggle(25, base=84000, amp=60) + [84300, 84500, 84700]
            now = datetime(2026, 9, 25, 20, 0, tzinfo=ET)
            marks = [{"symbol": "BTC/USD", "price": p, "ts": (now - timedelta(minutes=len(prices) - i)).isoformat()}
                     for i, p in enumerate(prices)]
            with mock.patch.multiple(cli, **paths), mock.patch.object(cli, "cmd_sync_board"), \
                    mock.patch.object(clock, "now", return_value=now):
                cli.main(["init"])
                scan.record(d / "history.jsonl", marks)
                L = Ledger.load(d / "state.json")
                L.mark("BTC/USD", 84700, now - timedelta(seconds=30), 84695, 84705)
                L.save(d / "state.json")
                cfg = config.load()
                posted = cli.run_scan(cfg, now, sync=False)["posted"]
                self.assertEqual(posted[0]["symbol"], "BTC/USD")
                sid = posted[0]["id"]
                with self.assertRaises(SystemExit):          # no thesis, no preview
                    cli.main(["preview-signal", sid])
                cli.main(["thesis", sid, "Breakout on rising marks", "--invalidation", "84200"])
                cli.main(["preview-signal", sid])
                ps = json.loads((d / "previews.json").read_text())
                p = next(iter(ps.values()))
                self.assertEqual((p["symbol"], p["side"], p["stop"], p["signal_id"]), ("BTC/USD", "buy", 84200, sid))
                self.assertLessEqual(p["notional"], 0.05 * 100000 + 1)   # position cap binds before the risk budget
                book = json.loads((d / "signals.json").read_text())
                self.assertEqual(book["counts"], {"scanned": len(posted), "thesis": 1, "risk_passed": 1, "previewed": 1})
                self.assertEqual(book["signals"][sid]["status"], "previewed")
                cli.main(["approve", p["id"], "EXECUTE"])
                self.assertGreater(Ledger.load(d / "state.json").qty("BTC/USD"), 0)

    def test_stale_mark_vetoes_preview(self):
        from fund import __main__ as cli
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            paths = {"DIR": d, "STATE": d / "state.json", "PREVIEWS": d / "previews.json", "EVENTS": d / "events.jsonl",
                     "FEED": d / "feed.json", "HISTORY": d / "history.jsonl", "SIGNALS": d / "signals.json"}
            now = datetime(2026, 9, 25, 20, 0, tzinfo=ET)
            with mock.patch.multiple(cli, **paths), mock.patch.object(clock, "now", return_value=now):
                cli.main(["init"])
                L = Ledger.load(d / "state.json")
                L.mark("BTC/USD", 84700, now - timedelta(minutes=10), 84695, 84705)
                L.save(d / "state.json")
                b = scan.new_book()
                s = scan.post(b, [{"symbol": "BTC/USD", "side": "buy", "setup": "breakout", "score": 2, "price": 84700,
                                   "stop": 84400, "target": 85300, "why": "t"}], now, SC)[0]
                scan.attach_thesis(b, s["id"], "t", None, now, SC)
                scan.save_book(b, d / "signals.json")
                with self.assertRaises(SystemExit) as e:
                    cli.main(["preview-signal", s["id"]])
                self.assertIn("stale_quote", str(e.exception))
                self.assertEqual(json.loads((d / "signals.json").read_text())["signals"][s["id"]]["status"], "vetoed")


if __name__ == "__main__":
    unittest.main()
