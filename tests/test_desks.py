import unittest
from datetime import datetime, timedelta, timezone

import judge
import kalshi
import sportsbook
from fund import catalyst, preview
from kalshi import settlement
from sportsbook import cause
from tests.test_fund import OPEN, cfg, order
from fund.ledger import Ledger

T0 = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)


def live(value, p):
    return judge.Answer(value, p, live=True)


class JudgeTests(unittest.TestCase):
    def test_stub_is_default_and_never_confident(self):
        c = judge.from_env({})
        self.assertIsInstance(c, judge.StubClient)
        a = judge.ask(c, {}, catalyst.QUESTIONS)
        self.assertFalse(a["material"].confident(0.0))

    def test_live_needs_key_and_opt_in(self):
        self.assertIsInstance(judge.from_env({"TYPESAFE_API_KEY": "k", "TYPESAFE_API_URL": "u"}), judge.StubClient)
        c = judge.from_env({"TYPESAFE_API_KEY": "k", "TYPESAFE_LIVE": "1"})
        self.assertIsInstance(c, judge.HttpClient)
        self.assertEqual((c.base_url, c.model), ("https://api.typesafe.ai/v1/systemone", "jev-1.13.0"))

    def test_question_validation(self):
        with self.assertRaises(ValueError):
            judge.Question("x", "choice", "pick")
        with self.assertRaises(ValueError):
            judge.ask(judge.StubClient(), {}, [catalyst.QUESTIONS[0], catalyst.QUESTIONS[0]])

    def test_http_payload_shape(self):
        p = judge.HttpClient("k", "https://x").payload({"a": 1}, catalyst.QUESTIONS)
        self.assertEqual({k: q["type"] for k, q in p["questions"].items()}, {"material": "noul", "direction": "choice"})
        self.assertNotIn("criteria", p["questions"]["material"])
        self.assertIn("bullish", p["questions"]["direction"]["criteria"])
        self.assertEqual(p["state"], '{"a": 1}')
        self.assertEqual(p["model"], "jev-1.13.0")

    def test_http_parse_documented_shape(self):
        a = judge.HttpClient.parse({"answers": {
            "material": {"type": "noul", "noul": 0.91},
            "direction": {"type": "choice", "choice": "bearish", "confidence": 0.7,
                          "probabilities": {"bearish": 0.8, "bullish": 0.2}}}})
        self.assertTrue(a["material"].value and a["material"].confident(0.8))
        self.assertEqual((a["direction"].value, a["direction"].probability), ("bearish", 0.8))
        self.assertEqual(catalyst.veto(a)[0], "news_catalyst")
        with self.assertRaises(RuntimeError):
            judge.HttpClient.parse({"answers": {"x": {"type": "essay"}}})


class CatalystTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg()
        self.ledger = Ledger(self.cfg.starting_nav)

    def test_confident_material_news_blocks_opening(self):
        ans = judge.ask(judge.StubClient({"material": live(True, 0.93)}), {}, catalyst.QUESTIONS)
        with self.assertRaisesRegex(preview.GateError, "news_catalyst"):
            preview.build(order("SPY", "buy", 1, 500, OPEN), self.ledger, self.cfg, OPEN, catalyst=ans)

    def test_weak_or_stub_answers_do_not_block(self):
        for c in (judge.StubClient(), judge.StubClient({"material": live(True, 0.6)})):
            ans = catalyst.assess(c, "SPY", ["SPY closes flat"])
            p = preview.build(order("SPY", "buy", 1, 500, OPEN), self.ledger, self.cfg, OPEN, catalyst=ans)
            self.assertEqual(p["status"], "awaiting_approval")

    def test_exits_are_never_blocked(self):
        self.ledger.fill("SPY", "buy", 5, 500, OPEN)
        self.ledger.mark("SPY", 500, OPEN)
        ans = judge.ask(judge.StubClient({"material": live(True, 0.99)}), {}, catalyst.QUESTIONS)
        p = preview.build(order("SPY", "sell", 5, 500, OPEN), self.ledger, self.cfg, OPEN, catalyst=ans)
        self.assertTrue(p["reducing"])

    def test_no_headlines_no_call(self):
        self.assertIsNone(catalyst.assess(judge.StubClient(), "SPY", []))


class KalshiTests(unittest.TestCase):
    def test_quote_locks_edge(self):
        q = kalshi.quote(0.50, edge_c=2)
        self.assertEqual((q.yes_bid, q.no_bid, q.lock_c), (49, 49, 2))
        self.assertLess(q.yes_bid + q.no_bid, 100)

    def test_skew_and_bounds(self):
        q = kalshi.quote(0.60, edge_c=2, skew_c=1)
        self.assertEqual((q.yes_bid, q.no_bid), (60, 38))
        self.assertIsNone(kalshi.quote(1.0))
        self.assertIsNone(kalshi.quote(0.5, edge_c=0))

    def test_exposure_and_cut(self):
        q = kalshi.Quote(49, 49)
        self.assertEqual(kalshi.exposure(10, 10, q), -20)     # locked 2¢ × 10
        self.assertEqual(kalshi.exposure(10, 0, q), 490)
        self.assertTrue(kalshi.should_cut(10, 0, q, p_yes_now=0.42, secs_left=600))
        self.assertFalse(kalshi.should_cut(10, 0, q, p_yes_now=0.48, secs_left=600))
        self.assertTrue(kalshi.should_cut(10, 0, q, p_yes_now=0.50, secs_left=30))
        self.assertFalse(kalshi.should_cut(5, 5, q, p_yes_now=0.1, secs_left=10))

    def test_fee_and_modes(self):
        self.assertEqual(kalshi.taker_fee_cents(50, 100), 175)
        self.assertEqual(kalshi.require_mode("SHADOW"), "SHADOW")
        with self.assertRaises(kalshi.ModeError):
            kalshi.require_mode("LIVE")

    def test_settlement_needs_confident_live_yes_and_caches(self):
        m = {"ticker": "KXBTC15M-X", "asset": "BTC", "window_min": 15, "rules": "..."}
        cache = {}
        self.assertFalse(settlement.verify(judge.StubClient(), m, cache))
        self.assertIn("KXBTC15M-X", cache)
        ok = judge.StubClient({"cfb_settlement": live(True, 0.97)})
        self.assertTrue(settlement.verify(ok, m, {}))


class SportsbookTests(unittest.TestCase):
    def test_no_vig_and_ev(self):
        h, a = sportsbook.no_vig(-110, -110)
        self.assertAlmostEqual(h, 0.5)
        self.assertAlmostEqual(sportsbook.ev_pct(0.5, 100), 0.0)
        self.assertLess(sportsbook.ev_pct(0.5, -110), 0)

    def test_steam_compares_each_book_to_itself(self):
        old, new = T0 - timedelta(minutes=15), T0 - timedelta(minutes=2)
        snaps = [sportsbook.Snap(b, -3.0, old) for b in ("dk", "fd", "mgm")]
        snaps += [sportsbook.Snap(b, -4.5, new) for b in ("dk", "fd", "mgm")]
        self.assertEqual(sportsbook.steam(snaps, T0), ("home", ["dk", "fd", "mgm"]))
        flat = [sportsbook.Snap(b, -3.0, t) for b in ("dk", "fd", "mgm") for t in (old, new)]
        self.assertIsNone(sportsbook.steam(flat, T0))

    def test_reverse_and_volume(self):
        self.assertEqual(sportsbook.reverse_line_move(-3.0, -2.0, home_bet_pct=72), "away")
        self.assertIsNone(sportsbook.reverse_line_move(-3.0, -4.0, home_bet_pct=72))
        self.assertTrue(sportsbook.volume_anomaly(40, 62))

    def test_cause_gates_sharp_label(self):
        move = {"points": 1.5, "toward": "home", "from": "t0", "to": "t1"}
        injured = judge.StubClient({"cause": live("injury", 0.9)})
        self.assertEqual(cause.label(injured, {"id": "g"}, move, [{"t": "t0", "text": "QB out"}]), "injury")
        self.assertFalse(cause.is_sharp(("home", ["dk"]), "injury"))
        self.assertTrue(cause.is_sharp(("home", ["dk"]), cause.label(judge.StubClient(), {}, move, [])))


if __name__ == "__main__":
    unittest.main()
