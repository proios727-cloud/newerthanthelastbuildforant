import tempfile
import unittest
from datetime import date
from pathlib import Path

import judge
from fund import battery, calibration, killswitch, putbook, spreadbook

from tests.test_putbook import BARS, D, row
from tests.test_spreadbook import chain


def live(value, p, dist=None):
    return judge.Answer(value, p, dist or {}, live=True)


def answers(material=0.1, crisis=0.05, setup0=0.05, liq0=0.05, conf=0.9):
    return {"material": live(material >= 0.5, material),
            "regime": live("calm_trend", conf, {"calm_trend": conf, "crisis": crisis}),
            "setup": live(2.1, conf, {"0": setup0, "2": 1 - setup0}),
            "liquidity": live(2.4, conf, {"0": liq0, "3": 1 - liq0})}


class BatteryTests(unittest.TestCase):
    def test_each_question_vetoes_only_past_its_threshold(self):
        self.assertIsNone(battery.verdict(answers(), True)["veto"])
        self.assertEqual(battery.verdict(answers(material=0.85), True)["veto"][0], "news_catalyst")
        self.assertEqual(battery.verdict(answers(crisis=0.72), True)["veto"][0], "regime_crisis")
        self.assertEqual(battery.verdict(answers(setup0=0.75), True)["veto"][0], "setup_poor")
        self.assertEqual(battery.verdict(answers(liq0=0.9), True)["veto"][0], "illiquid")
        self.assertIsNone(battery.verdict(answers(setup0=0.69), True)["veto"])

    def test_stub_battery_never_vetoes_and_records_bad_probabilities(self):
        ans = battery.assess(judge.StubClient(), "AAPL", ["AAPL halted"], {"market": {}, "trade": {}})
        v = battery.verdict(ans, False)
        self.assertIsNone(v["veto"])
        self.assertEqual(set(v["answers"]), {"material", "regime", "setup", "liquidity"})
        self.assertEqual(v["escalate"], [])

    def test_low_confidence_is_escalated_not_acted_on(self):
        v = battery.verdict(answers(conf=0.45), True)
        self.assertIsNone(v["veto"])
        self.assertEqual(sorted(v["escalate"]), ["liquidity", "regime", "setup"])

    def test_state_is_structured_and_clean(self):
        s = battery.state("AAPL", ["ok​news"], {"market": {"rv20": 0.2}, "trade": {"dte": 30}})
        self.assertEqual((s["headlines"], s["market"]["rv20"], s["trade"]["dte"]), (["ok news"], 0.2, 30))

    def test_http_payload_for_battery_is_valid(self):
        p = judge.HttpClient("k").payload(battery.state("AAPL", [], {}), battery.QUESTIONS)
        self.assertEqual(p["questions"]["regime"]["type"], "choice")
        self.assertEqual(len(p["questions"]["setup"]["criteria"]), 4)


class BookFieldsTests(unittest.TestCase):
    def test_entries_carry_ids_expected_price_slippage_and_answers(self):
        st = putbook.new_state()
        verdict = {"veto": None, "p": 0.1, "mode": "live", "answers": {"material": 0.1, "setup": 0.05},
                   "escalate": ["setup"], "model": "jev-latest"}
        seen = {}

        def jev(s, h, c=None):
            seen.update(c or {})
            return verdict

        putbook.apply(st, BARS, {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9, iid="x")]}}, D, judge_fn=jev)
        p = st["positions"]["AAPL"]
        self.assertEqual((p["strategy_id"], p["decision_id"]), ("put30d-v1", "put30d-v1:2026-09-28:AAPL"))
        self.assertAlmostEqual(p["entry_slip"], 4.725 - 4.55, places=4)
        self.assertEqual((p["jev_answers"]["setup"], p["jev_escalate"], p["model_version"]), (0.05, ["setup"], "jev-latest"))
        self.assertEqual(seen["trade"]["structure"], "sell 1 cash-secured put")
        self.assertEqual(seen["trade"]["dte"], 32)
        putbook.apply(st, BARS, {"marks": {"x": {"bid": 2.0, "ask": 2.2}}}, date(2026, 9, 29))
        c = st["closed"][0]
        self.assertAlmostEqual(c["exit_slip"], 0.1, places=4)
        self.assertEqual(c["decision_id"], "put30d-v1:2026-09-28:AAPL")
        self.assertIsNotNone(putbook.summary(st)["slippage_pct_of_credit"])

    def test_spread_context_has_both_legs(self):
        st, seen = spreadbook.new_state(), {}
        spreadbook.apply(st, BARS, {"chains": {"AAPL": chain()}}, D,
                         judge_fn=lambda s, h, c=None: seen.update(c) or None)
        self.assertEqual(seen["trade"]["strikes"], [325, 324])
        self.assertEqual(st["positions"]["AAPL"]["strategy_id"], "pcs12-v1")


class KillSwitchTests(unittest.TestCase):
    def test_armed_switch_blocks_entries_but_not_exits(self):
        st = putbook.new_state()
        putbook.apply(st, BARS, {"chains": {"AAPL": [row(325, -0.28, 4.55, 4.9, iid="x")]}}, D)
        putbook.apply(st, BARS, {"marks": {"x": {"bid": 2.0, "ask": 2.2}},
                                 "chains": {"SPY": [row(730, -0.3, 3.37, 3.40)]}}, date(2026, 9, 29), kill="test")
        self.assertEqual(st["closed"][0]["why"], "target")
        self.assertEqual(st["positions"], {})
        self.assertEqual(st["log"][-1]["reason"], "kill switch: test")
        sp = spreadbook.new_state()
        spreadbook.apply(sp, BARS, {"chains": {"AAPL": chain()}}, D, kill="test")
        self.assertEqual(sp["positions"], {})

    def test_arm_disarm_and_floors(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "kill.json"
            ks = killswitch.load(path)
            self.assertTrue(killswitch.arm(ks, "breach"))
            self.assertFalse(killswitch.arm(ks, "again"))
            killswitch.save(ks, path)
            ks = killswitch.load(path)
            with self.assertRaises(ValueError):
                killswitch.disarm(ks, "yes")
            self.assertTrue(killswitch.disarm(ks, "DISARM"))
            self.assertEqual([h["action"] for h in ks["history"]], ["arm", "disarm"])
        self.assertEqual(killswitch.floor_breaches({"putbook": 95_000, "spreadbook": 349}, {"putbook": 100_000, "spreadbook": 500}),
                         [("spreadbook", 349, 350.0)])


class CalibrationTests(unittest.TestCase):
    def test_brier_and_bins_from_live_trades_and_ghosts(self):
        book = {"closed": [{"pnl": 50, "jev_mode": "live", "jev_answers": {"setup": 0.1}},
                           {"pnl": -80, "jev_mode": "live", "jev_answers": {"setup": 0.3}},
                           {"pnl": 40, "jev_mode": "stub", "jev_answers": {"setup": 0.9}}],
                "ghost_closed": [{"pnl": -120, "jev_mode": "live", "jev_answers": {"setup": 0.9}}]}
        r = calibration.report(book)
        q = r["questions"]["setup"]
        self.assertEqual((r["trades_scored"], q["n"]), (3, 3))
        self.assertAlmostEqual(q["brier"], round(((0.1) ** 2 + (0.3 - 1) ** 2 + (0.9 - 1) ** 2) / 3, 4))
        self.assertEqual(q["loss_rate"], round(2 / 3, 3))
        self.assertEqual(sum(b["n"] for b in q["bins"]), 3)


if __name__ == "__main__":
    unittest.main()
