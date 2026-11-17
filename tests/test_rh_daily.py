import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location(
    "rh_daily", pathlib.Path(__file__).resolve().parents[1] / "scripts/rh_daily_from_transcript.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


class RhDailyTests(unittest.TestCase):
    def body(self, interp=False):
        return {"data": {"results": [{"symbol": "ko", "interval": "day", "bars": [
            {"begins_at": "2026-11-13T00:00:00Z", "open_price": "98.18", "high_price": "99.3", "low_price": "97.96",
             "close_price": "99.25", "volume": 18037684},
            {"begins_at": "2026-07-15T00:00:00Z", "open_price": "1", "high_price": "1", "low_price": "1",
             "close_price": "1", "volume": 1, "interpolated": interp}]}]}}

    def test_stamps_match_tradingview_daily_open(self):
        rows = R.daily_rows(self.body())["KO"]
        self.assertEqual(rows[0][0], "2026-11-13T14:30:00+00:00")  # EST
        self.assertEqual(rows[1][0], "2026-07-15T13:30:00+00:00")  # EDT
        self.assertEqual(rows[0][4], 99.25)

    def test_skips_interpolated_and_merges_without_duplicates(self):
        rows = R.daily_rows(self.body(interp=True))["KO"]
        self.assertEqual(len(rows), 1)
        old = [["2026-11-13T14:30:00+00:00", "98", "99", "97", "98.5", "1"]]
        merged = R.merge_rows(old, rows, R.dt.timezone.utc)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][4], 99.25)  # the new bar wins


if __name__ == "__main__":
    unittest.main()
