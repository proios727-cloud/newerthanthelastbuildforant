import base64
import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gex_plan", ROOT / "scripts" / "gex_plan.py")
gp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gp)


class GexPlanTests(unittest.TestCase):
    def test_tonight_capture(self):
        p = gp.make_plan(732.38, 3, 10, dt.date(2026, 11, 18))
        self.assertEqual((p["strike_lo"], p["strike_hi"]), (723, 742))
        self.assertEqual(p["cursor"], "cD03MTkuMDAwMA==")
        self.assertEqual(base64.b64decode(p["cursor"]).decode(), "p=719.0000")
        self.assertEqual(p["expiries"], ["2026-11-18", "2026-11-19", "2026-11-20"])

    def test_weekend_skipped(self):
        self.assertEqual(gp.next_weekdays(dt.date(2026, 11, 20), 3), ["2026-11-20", "2026-11-23", "2026-11-24"])
        self.assertEqual(gp.next_weekdays(dt.date(2026, 11, 21), 1), ["2026-11-23"])

    def test_shape(self):
        p = gp.make_plan(500.2, 2, 5, dt.date(2026, 11, 18))
        self.assertEqual(set(p), {"spot", "expiries", "cursor", "strike_lo", "strike_hi", "calls_per_expiry", "total_calls"})
        self.assertEqual(p["calls_per_expiry"], {"instrument_pages": 2, "quote_calls": 2})
        self.assertEqual((p["strike_lo"], p["strike_hi"]), (496, 505))
        self.assertEqual(len(gp.steps(p)), 4)


if __name__ == "__main__":
    unittest.main()
