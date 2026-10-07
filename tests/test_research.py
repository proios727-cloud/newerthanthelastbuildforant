import contextlib
import copy
import io
import json
import math
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta

from fund import clock
from fund.ledger import Ledger
from research import gates, review
from research.__main__ import main as cli

ET = clock.ET
ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 7, 21, 0, tzinfo=ET)


def report(**over):
    """A summary that clears every gate; tests break one field at a time."""
    r = {
        "strategy": "eth-4h-breakout", "version": 3, "book": "directional",
        "settings": {"venue_fees": True, "slippage_bps": 10},
        "closed_trades": 140, "years": 3.0, "variants_tested": 5,
        "sharpe": 1.4, "profit_factor": 1.5,
        "win_rate": 0.42, "avg_win": 300.0, "avg_loss": 150.0,
        "max_drawdown_pct": 12.0, "return_pct": 41.0, "buy_hold_return_pct": 30.0,
        "beta": 0.6,
        "stress": {"return_2x_costs_pct": 9.0, "neighbor_sharpes": [1.2, 1.3, 1.1, 1.25]},
        "return_last_1y_pct": 6.0,
        "risk_verdict": "KEEP",
        "paper": {"days": 28, "sharpe": 1.1},
    }
    r.update(over)
    return r


def failed(result):
    return [c.name for c in result.checks if not c.ok]


class GateTests(unittest.TestCase):
    def test_clean_report_is_deployable(self):
        res = gates.check(report())
        self.assertEqual(res.status, "DEPLOYABLE", failed(res))
        self.assertEqual(failed(res), [])

    def test_each_gate_blocks_on_its_own(self):
        cases = {
            "settings": {"settings": {"venue_fees": False, "slippage_bps": 10}},
            "sample": {"closed_trades": 99},
            "quality": {"profit_factor": 1.3},
            "expectancy": {"win_rate": 0.3, "avg_win": 100.0, "avg_loss": 100.0},
            "pain": {"max_drawdown_pct": 25.0},
            "benchmark": {"buy_hold_return_pct": 41.0},
            "luck": {"variants_tested": 100_000, "years": 1.0},
            "risk_officer": {"risk_verdict": "KILL"},
            "costs": {"stress": {"return_2x_costs_pct": -1.0, "neighbor_sharpes": [1.2]}},
            "plateau": {"stress": {"return_2x_costs_pct": 9.0, "neighbor_sharpes": [1.3, 0.4]}},
            "recent": {"return_last_1y_pct": -0.5},
            "forward": {"paper": {"days": 10, "sharpe": 1.1}},
        }
        for name, over in cases.items():
            with self.subTest(gate=name):
                res = gates.check(report(**over))
                self.assertEqual(res.status, "BLOCKED")
                self.assertEqual(failed(res), [name])

    def test_paper_must_track_backtest(self):
        res = gates.check(report(paper={"days": 40, "sharpe": 0.3}))
        self.assertEqual(failed(res), ["forward"])

    def test_missing_field_blocks_instead_of_crashing(self):
        r = report()
        del r["risk_verdict"]
        del r["paper"]
        res = gates.check(r)
        self.assertEqual(res.status, "BLOCKED")
        self.assertEqual(sorted(failed(res)), ["forward", "risk_officer"])
        self.assertIn("missing", next(c.detail for c in res.checks if c.name == "forward"))

    def test_wrong_types_block(self):
        res = gates.check(report(sharpe="1.4", closed_trades=True))
        self.assertEqual(res.status, "BLOCKED")
        self.assertIn("sample", failed(res))
        self.assertIn("quality", failed(res))

    def test_not_a_dict(self):
        res = gates.check(["nope"])
        self.assertEqual(res.status, "BLOCKED")

    def test_beta_only_gates_long_short_books(self):
        self.assertEqual(gates.check(report(beta=0.6)).status, "DEPLOYABLE")
        res = gates.check(report(book="long_short", beta=0.6))
        self.assertEqual(failed(res), ["neutral"])
        self.assertEqual(gates.check(report(book="long_short", beta=-0.05)).status, "DEPLOYABLE")
        self.assertEqual(failed(gates.check(report(book="pairs"))), ["neutral"])

    def test_luck_threshold(self):
        self.assertEqual(gates.luck_threshold(1, 3.0), 0.0)
        self.assertAlmostEqual(gates.luck_threshold(1000, 1.0), math.sqrt(2 * math.log(1000)))
        self.assertAlmostEqual(gates.luck_threshold(1000, 4.0), math.sqrt(2 * math.log(1000)) / 2)

    def test_stress_costs_must_survive_not_just_stay_positive_sharpe(self):
        res = gates.check(report(stress={"return_2x_costs_pct": 0.0, "neighbor_sharpes": [1.2]}))
        self.assertEqual(failed(res), ["costs"])

    def test_desk_json_scorecard_loads_and_overrides(self):
        card = gates.load_scorecard(ROOT / "desk.json")
        self.assertEqual(card["min_closed_trades"], 100)
        strict = dict(card, min_closed_trades=500)
        self.assertEqual(failed(gates.check(report(), strict)), ["sample"])

    def test_scorecard_rejects_unknown_keys(self):
        with self.assertRaises(ValueError):
            gates.scorecard({"min_sharp": 2})


class GateCliTests(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            cli(list(argv))
        return cm.exception.code, out.getvalue()

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            good, bad = pathlib.Path(d, "good.json"), pathlib.Path(d, "bad.json")
            good.write_text(json.dumps(report()))
            bad.write_text(json.dumps(report(closed_trades=12)))
            code, text = self.run_cli("gate", str(good))
            self.assertEqual(code, 0)
            self.assertIn("DEPLOYABLE", text)
            code, text = self.run_cli("gate", str(bad), "--json")
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(text)["status"], "BLOCKED")
            code, _ = self.run_cli("gate", str(pathlib.Path(d, "missing.json")))
            self.assertEqual(code, 2)


class FakeModel:
    def __init__(self, text):
        self.text, self.calls = text, []

    def create(self, system, user):
        self.calls.append((system, user))
        return self.text


def ledger_with_trades(path):
    L = Ledger(100_000)
    t0 = NOW - timedelta(days=3)
    L.fill("ETH/USD", "buy", 2, 2500, t0, fee=5, ref="p1")
    L.fill("ETH/USD", "sell", 2, 2400, t0 + timedelta(hours=4), fee=5, ref="p2")   # loser
    L.fill("SPY", "buy", 10, 700, t0 + timedelta(days=1), fee=0, ref="p3")
    L.fill("SPY", "sell", 10, 710, t0 + timedelta(days=1, hours=2), fee=0, ref="p4")  # winner
    L.fill("SPY", "buy", 1, 650, NOW - timedelta(days=30), ref="old")               # outside window
    L.save(path)
    return L


MODEL_JSON = json.dumps({
    "lessons": [
        {"pattern": "crypto breakout into funding spike", "rule": "Skip ETH longs when funding > 0.05%/8h",
         "evidence": "p2 lost 200 after entering at peak funding"},
        {"pattern": "no evidence", "rule": "", "evidence": ""},
    ],
    "proposals": [
        {"strategy": "eth-4h-breakout", "change": "Add funding filter", "why": "p2"},
        {"strategy": "eth-4h-breakout", "change": "Widen stop", "why": "guess"},
    ],
})


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        self.state, self.spec = d / "state.json", d / "strategy.md"
        self.lessons, self.out = d / "lessons.md", d / "reviews"
        ledger_with_trades(self.state)
        self.spec.write_text("# eth-4h-breakout\nBacktest: 140 trades, Sharpe 1.4, win rate 42%.\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_review(self, model):
        return review.run(self.state, self.spec, self.lessons, self.out, now=NOW, days=7, model=model)

    def test_window_and_stats(self):
        trades = review.recent_fills(json.loads(self.state.read_text())["fills"], NOW, 7)
        self.assertEqual([t["ref"] for t in trades], ["p1", "p2", "p3", "p4"])
        s = review.stats(trades)
        self.assertEqual((s["closed"], s["losers"], s["winners"]), (2, 1, 1))
        self.assertAlmostEqual(s["realized"], -200 + 100)
        self.assertAlmostEqual(s["fees"], 10)

    def test_ledger_is_never_written(self):
        before = self.state.read_bytes()
        self.run_review(FakeModel(MODEL_JSON))
        self.assertEqual(self.state.read_bytes(), before)

    def test_one_proposal_and_only_evidenced_lessons(self):
        model = FakeModel(MODEL_JSON)
        r = self.run_review(model)
        self.assertEqual(len(model.calls), 1)
        self.assertIn("TRADES", model.calls[0][1])
        self.assertIn("p2", model.calls[0][1])
        self.assertEqual(r.proposal["change"], "Add funding filter")
        self.assertEqual(len(r.added_lessons), 1)
        text = self.lessons.read_text()
        self.assertIn("2026-10-07", text)
        self.assertIn("Skip ETH longs when funding > 0.05%/8h", text)
        self.assertIn("evidence: p2 lost 200", text)
        report_md = (self.out / "2026-10-07.md").read_text()
        self.assertIn("Add funding filter", report_md)
        self.assertNotIn("Widen stop", report_md)
        self.assertIn("dropped 1 extra proposal", report_md)

    def test_duplicate_lessons_not_appended_twice(self):
        self.run_review(FakeModel(MODEL_JSON))
        r = self.run_review(FakeModel(MODEL_JSON))
        self.assertEqual(r.added_lessons, [])
        self.assertEqual(self.lessons.read_text().count("Skip ETH longs"), 1)

    def test_malformed_model_output_changes_nothing(self):
        r = self.run_review(FakeModel("I think you should buy more ETH."))
        self.assertFalse(self.lessons.exists())
        self.assertIsNone(r.proposal)
        self.assertIn("could not parse", (self.out / "2026-10-07.md").read_text())

    def test_offline_writes_stats_only(self):
        r = self.run_review(None)
        self.assertFalse(self.lessons.exists())
        md = (self.out / "2026-10-07.md").read_text()
        self.assertIn("no model run", md)
        self.assertIn("Losing trades", md)
        self.assertIn("p2", md)
        self.assertEqual(r.stats["losers"], 1)

    def test_model_json_inside_code_fence(self):
        r = self.run_review(FakeModel("Here you go:\n```json\n" + MODEL_JSON + "\n```"))
        self.assertEqual(r.proposal["change"], "Add funding filter")


if __name__ == "__main__":
    unittest.main()
