import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fund import battery, killswitch, limits  # noqa: E402


class Limits(unittest.TestCase):
    def test_yaml_loads(self):
        L = limits.load()
        self.assertEqual(L["fund"]["dd_kill"], 0.10)
        self.assertEqual(L["floors"], {"putbook": 0.90, "spreadbook": 0.70})
        self.assertEqual(killswitch.AUTO_FLOORS, L["floors"])
        self.assertEqual(L["jev"]["escalate_below"], battery.ESCALATE_BELOW)

    def test_fund_drawdown_tracks_peak(self):
        ks = {}
        starts = {"a": 100.0, "b": 100.0}
        self.assertIsNone(limits.fund_drawdown(ks, {"a": 110.0, "b": 110.0}, starts, 0.10))
        self.assertIsNone(limits.fund_drawdown(ks, {"a": 100.0, "b": 100.0}, starts, 0.10))   # -9.1%
        self.assertIn("below peak", limits.fund_drawdown(ks, {"a": 98.0, "b": 99.0}, starts, 0.10))
        self.assertAlmostEqual(ks["fund_peak"], 1.10)


class Schemas(unittest.TestCase):
    def test_exported_schemas_match_code(self):
        import export_jev_schemas as E
        for v, s in E.schemas().items():
            on_disk = (ROOT / "jev" / "schemas" / f"{v}.json").read_text(encoding="utf-8")
            self.assertEqual(on_disk, E.render(s), f"run scripts/export_jev_schemas.py ({v} drifted)")

    def test_verdicts_carry_schema(self):
        self.assertEqual(battery.verdict({}, False)["schema"], battery.SCHEMA)
        self.assertEqual(battery.trend_verdict({})["schema"], battery.TREND_SCHEMA)


if __name__ == "__main__":
    unittest.main()
