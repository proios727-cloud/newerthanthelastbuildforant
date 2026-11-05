import csv
import datetime as dt
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from zoneinfo import ZoneInfo

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class MergeTests(unittest.TestCase):
    def test_same_bar_in_utc_and_et_is_kept_once(self):
        m = load("tv_ohlcv_to_csv")
        old = [["2026-10-30T09:30:00-04:00", "1", "2", "0.5", "1.5", "100"]]       # ET file
        new = [("2026-10-30T13:30:00+00:00", 1, 2, 0.5, 1.6, 110),                # same bar, UTC
               ("2026-11-02T14:30:00+00:00", 2, 3, 1.5, 2.5, 120)]
        rows = m.merge_rows(old, new, ZoneInfo("America/New_York"))
        self.assertEqual([r[0] for r in rows], ["2026-10-30T09:30:00-04:00", "2026-11-02T09:30:00-05:00"])
        self.assertEqual(rows[0][4], 1.6)                                          # the new row wins

    def test_rows_sorted_by_instant_across_offsets(self):
        m = load("tv_ohlcv_to_csv")
        rows = m.merge_rows([], [("2026-11-02T00:00:00+00:00", 1, 1, 1, 1, 1),
                                 ("2026-11-01T22:00:00-04:00", 1, 1, 1, 1, 1)], dt.timezone.utc)
        self.assertEqual([r[0] for r in rows], ["2026-11-02T00:00:00+00:00", "2026-11-02T02:00:00+00:00"])


class RowsFormatTests(unittest.TestCase):
    def test_rows_and_columns_formats_agree(self):
        m = load("tv_ohlcv_to_csv")
        bars = [{"t": 1793889000, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10},
                {"t": 1793975400, "o": 1.5, "h": 2.5, "l": 1.0, "c": 2.0, "v": 20}]
        cols = {k: [b[k] for b in bars] for k in ("t", "o", "h", "l", "c", "v")}
        self.assertEqual(m.rows_from({"bars": bars}, True), m.rows_from({"bars": cols}, True))


class PositionsCsvTests(unittest.TestCase):
    def test_fill_without_instrument_id_does_not_crash(self):
        m = load("positions_csv")
        with tempfile.TemporaryDirectory() as d:
            j = pathlib.Path(d, "positions.jsonl")
            j.write_text("\n".join(json.dumps(r) for r in [
                {"id": "A", "event": "open", "ticker": "SPY", "instrument_id": "abc"},
                {"id": "B", "event": "open", "ticker": "QQQ", "source": "my paper fill"}]) + "\n")
            m.JOURNAL = j
            out, buf = pathlib.Path(d, "p.csv"), io.StringIO()
            with redirect_stdout(buf):
                m.main(["positions_csv.py", str(out)])
            self.assertIn('quote ids: ["abc"]', buf.getvalue())
            self.assertIn("no instrument_id", buf.getvalue())
            self.assertEqual(len(list(csv.DictReader(out.open()))), 2)


if __name__ == "__main__":
    unittest.main()
