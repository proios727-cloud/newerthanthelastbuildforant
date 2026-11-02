import pathlib
import unittest

from chart import Bar
from chart import signals as S


def day(date, rows, vol=1000):
    out, h, m = [], 9, 30
    for o, hi, lo, c in rows:
        out.append(Bar(f"{date}T{h:02d}:{m:02d}:00-05:00", o, hi, lo, c, vol))
        m += 15
        h, m = h + m // 60, m % 60
    return out


FLAT = (100, 100.2, 99.8, 100)


def sig(**kw):
    s = {"id": "x", "date": "2026-03-02", "ticker": "SPY", "side": "short",
         "trigger": {"kind": "reject_below", "level": 101, "after": "09:45", "before": "14:00"},
         "stop": {"level": 101, "basis": "close"}, "target": 99}
    s.update(kw)
    return s


def sessions(rows, date="2026-03-02"):
    from chart.intraday import sessions as to_s
    return to_s(day(date, rows))


class SignalScoreTests(unittest.TestCase):
    def test_reject_below_short_hits_target(self):
        # 09:30 bar ignored (before 09:45). 09:45 bar pokes 101.2, closes 100.5 -> trigger; fill at 10:00 open 100.4.
        rows = [(100, 101.5, 99.9, 100.2), (100.2, 101.2, 100.1, 100.5), (100.4, 100.6, 99.5, 99.7),
                (99.7, 99.8, 98.8, 99.0)] + [FLAT] * 22
        r = S.score(sig(), sessions(rows))
        self.assertEqual((r["status"], r["entry"], r["exit"], r["trigger_time"]), ("target", 100.4, 99, "10:00"))
        self.assertAlmostEqual(r["r"], (100.4 - 99) / (101 - 100.4))

    def test_close_basis_stop_exits_at_close(self):
        rows = [FLAT, (100.2, 101.2, 100.1, 100.5), (100.4, 101.6, 100.3, 101.4)] + [FLAT] * 23
        r = S.score(sig(), sessions(rows))
        self.assertEqual((r["status"], r["exit"]), ("stop", 101.4))
        self.assertLess(r["r"], -1)

    def test_stop_wins_tie_on_touch_basis(self):
        rows = [FLAT, (100.2, 101.2, 100.1, 100.5), (100.4, 101.5, 98.5, 100)] + [FLAT] * 23
        r = S.score(sig(stop={"level": 101, "basis": "touch"}), sessions(rows))
        self.assertEqual((r["status"], r["exit"]), ("stop", 101))
        self.assertAlmostEqual(r["r"], -1.0)

    def test_not_triggered_and_no_trade(self):
        self.assertEqual(S.score(sig(), sessions([FLAT] * 26))["status"], "not triggered")
        self.assertEqual(S.score(sig(side="none"), sessions([FLAT] * 26))["status"], "no trade")
        self.assertEqual(S.score(sig(date="2026-03-03"), sessions([FLAT] * 26))["status"], "no data")

    def test_long_close_above_runs_to_close(self):
        s = sig(side="long", trigger={"kind": "close_above", "level": 100.5, "after": "09:45"},
                stop={"level": 99.5, "basis": "touch"}, target=None)
        rows = [FLAT, (100, 100.8, 100, 100.7), (100.7, 101, 100.6, 100.9)] + [(100.9, 101.2, 100.8, 101)] * 23
        r = S.score(s, sessions(rows))
        self.assertEqual((r["status"], r["entry"], r["exit"]), ("close", 100.7, 101))

    def test_incomplete_session_is_in_progress(self):
        self.assertEqual(S.score(sig(), sessions([FLAT] * 10))["status"], "in progress")
        rows = [FLAT, (100.2, 101.2, 100.1, 100.5), (100.4, 100.6, 99.9, 100.1)] + [FLAT] * 5
        self.assertEqual(S.score(sig(target=None), sessions(rows))["status"], "open")

    def test_rvol_gate_blocks_thin_volume(self):
        from chart.intraday import sessions as to_s
        bars = []
        for d in range(1, 11):
            bars += day(f"2026-03-{d:02d}", [FLAT] * 26, vol=1000)
        bars += day("2026-03-11", [FLAT, (100.2, 101.2, 100.1, 100.5)] + [FLAT] * 24, vol=500)
        s = sig(date="2026-03-11", trigger={"kind": "reject_below", "level": 101, "after": "09:45", "rvol_min": 1.4})
        r = S.score(s, to_s(bars))
        self.assertEqual(r["status"], "not triggered")
        self.assertAlmostEqual(r["rvol"], 0.5)

    def test_no_lookahead_entry(self):
        a = [FLAT, (100.2, 101.2, 100.1, 100.5), (100.4, 100.6, 99.5, 99.7)] + [FLAT] * 23
        b = [FLAT, (100.2, 101.2, 100.1, 100.5), (100.4, 100.6, 99.5, 99.7)] + [(150, 151, 149, 150)] * 23
        self.assertEqual(S.score(sig(target=None), sessions(a))["entry"], S.score(sig(target=None), sessions(b))["entry"])

    def test_go_no_go_check(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("hc", pathlib.Path(__file__).resolve().parents[1] / "scripts/heatseeker_check.py")
        hc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hc)
        rows = [(100, 100.2, 99.8, 100), (100, 100.8, 100, 100.7), (100.7, 101, 100.6, 100.9)] + [FLAT] * 23
        s = sig(side="long", tier="B", contract="SPY 2026-03-03 100C, delta 0.5",
                trigger={"kind": "close_above", "level": 100.5, "after": "09:45"}, stop={"level": 100.2, "basis": "close"},
                target=101.5)
        partner = sessions([(50, 50.5, 50, 50.4)] * 26)
        r = hc.check(s, sessions(rows), partner, bid=1.00, ask=1.04, buying_power=20000, now="10:20")
        self.assertEqual(r["verdict"], "GO", r["gates"])
        self.assertEqual(r["contracts"], 2)               # 2.5% of 20,000 = 500, half for tier B = 250; 250 // 104
        self.assertIn("LIMIT 1.03", r["ticket"])
        late = hc.check(s, sessions(rows), partner, bid=1.00, ask=1.04, buying_power=20000, now="15:40")
        self.assertEqual(late["verdict"], "NO-GO")
        wide = hc.check(s, sessions(rows), partner, bid=0.80, ask=1.04, buying_power=20000, now="10:20")
        self.assertFalse(dict((g[0], g[1]) for g in wide["gates"])["spread"])

    def test_test_the_test(self):
        rows = [FLAT, (100.2, 101.2, 100.1, 100.5), (100.4, 100.6, 99.5, 99.7)] + [FLAT] * 23
        self.assertNotEqual(S.score(sig(), sessions(rows))["entry"], 100.5)


if __name__ == "__main__":
    unittest.main()
