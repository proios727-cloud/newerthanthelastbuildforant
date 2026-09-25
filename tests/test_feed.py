import json
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fund import clock, config, feed
from fund.ledger import Ledger

ET = clock.ET
ROOT = pathlib.Path(__file__).resolve().parent.parent
DESK = json.loads((ROOT / "desk.json").read_text())
FCFG = feed.feed_config(DESK["fund"])
UNI = DESK["fund"]["universe"]

OPEN = datetime(2026, 9, 24, 10, 0, tzinfo=ET)     # Thu, equities open
AFTER = datetime(2026, 9, 24, 20, 0, tzinfo=ET)    # Thu, equities closed


class FakeAV:
    """Mimics Alpha Vantage JSON for the HTTP layer."""
    def __init__(self, limit_after=None):
        self.calls, self.limit_after = [], limit_after

    def __call__(self, url):
        self.calls.append(url)
        if self.limit_after is not None and len(self.calls) > self.limit_after:
            return {"Information": "We have detected your API key ... 25 requests per day."}
        if "CURRENCY_EXCHANGE_RATE" in url:
            return {"Realtime Currency Exchange Rate": {
                "5. Exchange Rate": "84266.90", "6. Last Refreshed": "2026-09-25 00:05:00",
                "7. Time Zone": "UTC", "8. Bid Price": "84263.99", "9. Ask Price": "84267.30"}}
        return {"Global Quote": {"05. price": "767.18", "07. latest trading day": "2026-09-24"}}


def src(fake=None):
    return feed.AlphaVantage("k", http_get=fake or FakeAV())


class PlanTests(unittest.TestCase):
    def test_after_hours_crypto_only(self):
        st = feed.new_state()
        todo = feed.plan(UNI, set(), st, AFTER, FCFG)
        self.assertTrue(todo)
        self.assertTrue(all(UNI[s]["asset"] == "crypto" for s in todo))

    def test_pace_caps_early_day(self):
        early = datetime(2026, 9, 24, 0, 30, tzinfo=ET)
        self.assertEqual(feed.pace_allowance(25, early), 1)
        self.assertEqual(len(feed.plan(UNI, set(), feed.new_state(), early, FCFG)), 1)
        self.assertEqual(feed.pace_allowance(25, datetime(2026, 9, 24, 23, 59, tzinfo=ET)), 25)

    def test_held_first_then_stalest(self):
        st = feed.new_state()
        st["date"] = clock.fund_day(OPEN)
        st["last_fetch"] = {s: (OPEN - timedelta(hours=1)).isoformat() for s in UNI}
        st["last_fetch"]["AMD"] = (OPEN - timedelta(hours=5)).isoformat()
        todo = feed.plan(UNI, {"TSLA"}, st, OPEN, FCFG)
        self.assertEqual(todo[:2], ["TSLA", "AMD"])

    def test_cadence_and_budget(self):
        st = feed.new_state()
        st["date"] = clock.fund_day(OPEN)
        st["last_fetch"] = {"BTC/USD": (OPEN - timedelta(minutes=5)).isoformat()}
        self.assertNotIn("BTC/USD", feed.plan(UNI, set(), st, OPEN, FCFG))
        st["used"] = 25
        self.assertEqual(feed.plan(UNI, set(), st, OPEN, FCFG), [])

    def test_budget_resets_on_new_fund_day(self):
        st = {**feed.new_state(), "date": "2026-09-23", "used": 25}
        self.assertTrue(feed.plan(UNI, set(), st, OPEN, FCFG))
        self.assertEqual(st["used"], 0)


class SourceTests(unittest.TestCase):
    def test_parse_crypto_and_equity(self):
        s = src()
        q = s.quote("BTC/USD", "crypto", OPEN)
        self.assertEqual((q.price, q.bid, q.ask), (84266.90, 84263.99, 84267.30))
        self.assertEqual(q.ts, datetime(2026, 9, 25, 0, 5, tzinfo=timezone.utc))
        e = s.quote("SPY", "equity", OPEN)
        self.assertEqual((e.price, e.ts, e.bid), (767.18, OPEN, None))

    def test_errors(self):
        with self.assertRaises(feed.FeedError):
            feed.AlphaVantage("")
        with self.assertRaises(feed.RateLimited):
            src(lambda u: {"Note": "slow down"}).quote("SPY", "equity", OPEN)
        with self.assertRaises(feed.FeedError):
            src(lambda u: {"Global Quote": {}}).quote("SPY", "equity", OPEN)


class TickTests(unittest.TestCase):
    def test_tick_marks_and_counts(self):
        L, st, fake = Ledger(100000), feed.new_state(), FakeAV()
        noon = datetime(2026, 9, 24, 12, 0, tzinfo=ET)
        rep = feed.tick(L, st, src(fake), UNI, FCFG, noon, sleep=lambda s: None)
        self.assertEqual(len(fake.calls), len(rep["planned"]))
        self.assertEqual(st["used"], len(rep["planned"]))
        self.assertIn("SPY", L.marks)
        self.assertEqual(L.marks["SPY"]["price"], 767.18)
        # nothing due on an immediate re-run
        self.assertEqual(feed.tick(L, st, src(fake), UNI, FCFG, noon, sleep=lambda s: None)["planned"], [])

    def test_rate_limit_stops_tick_and_backs_off(self):
        L, st = Ledger(100000), feed.new_state()
        noon = datetime(2026, 9, 24, 12, 0, tzinfo=ET)
        rep = feed.tick(L, st, src(FakeAV(limit_after=1)), UNI, FCFG, noon, sleep=lambda s: None)
        self.assertTrue(rep["rate_limited"])
        self.assertEqual(len(rep["marked"]), 1)
        self.assertEqual(st["used"], 2)
        self.assertEqual(feed.plan(UNI, set(), st, noon + timedelta(seconds=30), FCFG), [])
        self.assertTrue(feed.plan(UNI, set(), st, noon + timedelta(seconds=61), FCFG))

    def test_apply_skips_unknown_and_older(self):
        L = Ledger(100000)
        L.mark("SPY", 700, OPEN)
        qs = feed.load_quotes({"SPY": {"price": 690, "ts": (OPEN - timedelta(minutes=1)).isoformat()},
                               "DOGE/USD": {"price": 1}}, OPEN)
        marked, skipped = feed.apply(L, qs, UNI)
        self.assertEqual(marked, [])
        self.assertEqual({s["symbol"] for s in skipped}, {"SPY", "DOGE/USD"})
        self.assertEqual(L.marks["SPY"]["price"], 700)

    def test_load_quotes_validation(self):
        with self.assertRaises(feed.FeedError):
            feed.load_quotes({"SPY": {"price": -1}}, OPEN)
        with self.assertRaises(feed.FeedError):
            feed.load_quotes([{"symbol": "SPY", "price": 1, "ts": "2026-09-24T10:00:00"}], OPEN)


class CliTests(unittest.TestCase):
    def test_ingest_and_tick_via_cli(self):
        from fund import __main__ as cli
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            paths = {"DIR": d, "STATE": d / "state.json", "PREVIEWS": d / "previews.json",
                     "EVENTS": d / "events.jsonl", "FEED": d / "feed.json",
                     "HISTORY": d / "history.jsonl", "SIGNALS": d / "signals.json"}
            with mock.patch.multiple(cli, **paths), mock.patch.object(cli, "cmd_sync_board") as sync:
                cli.main(["init"])
                qf = d / "q.json"
                qf.write_text(json.dumps({"ETH/USD": {"price": 2500.5, "bid": 2500, "ask": 2501}}))
                cli.main(["ingest", str(qf)])
                self.assertEqual(Ledger.load(d / "state.json").marks["ETH/USD"]["price"], 2500.5)
                rep = cli.run_tick(config.load(), src(), datetime(2026, 9, 24, 12, tzinfo=ET), sleep=lambda s: None)
                self.assertTrue(rep["marked"])
                self.assertEqual(sync.call_count, 2)
                self.assertEqual(json.loads((d / "feed.json").read_text())["used"], len(rep["planned"]))


if __name__ == "__main__":
    unittest.main()
