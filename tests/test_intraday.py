import unittest

from chart import Bar
from chart import intraday as I


def day(date, rows, start=(9, 30), ivl=15):
    """rows: (open, high, low, close[, volume]) per bar, timestamps every ivl minutes from 09:30 ET."""
    out, h, m = [], *start
    for r in rows:
        o, hi, lo, c, *v = r
        out.append(Bar(f"{date}T{h:02d}:{m:02d}:00-04:00", o, hi, lo, c, v[0] if v else 1000))
        m += ivl
        h, m = h + m // 60, m % 60
    return out


FLAT = (100, 100.1, 99.9, 100)


class OrbTests(unittest.TestCase):
    def test_breakout_fills_next_open_and_hits_target(self):
        # OR (first bar) = 99..101. Bar 1 closes 101.5 (signal). Bar 2 opens 101.6 (entry): R = 2.6, 1R target 104.2.
        rows = [(100, 101, 99, 100), (100, 101.8, 100, 101.5), (101.6, 102, 101.2, 101.9), (102, 104.5, 101.9, 104)]
        rows += [FLAT] * 22
        t = I.run(I.sessions(day("2026-03-02", rows)), "orb", dict(or_min=15, target_r=1.0, rvol=None))
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["side"], t[0]["entry"], t[0]["reason"]), (1, 101.6, "target"))
        self.assertAlmostEqual(t[0]["exit"], 101.6 + 2.6)

    def test_stop_wins_when_both_touched_in_one_bar(self):
        rows = [(100, 101, 99, 100), (100, 101.8, 100, 101.5), (101.6, 110, 98, 100)] + [FLAT] * 23
        t = I.run(I.sessions(day("2026-03-02", rows)), "orb", dict(or_min=15, target_r=1.0, rvol=None))
        self.assertEqual((t[0]["reason"], t[0]["exit"]), ("stop", 99))

    def test_gap_through_stop_fills_at_open(self):
        rows = [(100, 101, 99, 100), (100, 101.8, 100, 101.5), (101.6, 102, 101.2, 101.9), (97, 97.5, 96, 96.5)]
        rows += [FLAT] * 22
        t = I.run(I.sessions(day("2026-03-02", rows)), "orb", dict(or_min=15, target_r=None, rvol=None))
        self.assertEqual((t[0]["reason"], t[0]["exit"]), ("stop", 97))

    def test_no_target_holds_to_close_and_short_side(self):
        rows = [(100, 101, 99, 100), (100, 100, 98, 98.5), (98.4, 98.6, 98, 98.2)] + [FLAT] * 22 + [(98, 98, 97, 97)]
        t = I.run(I.sessions(day("2026-03-02", rows)), "orb", dict(or_min=15, target_r=None, rvol=None))
        self.assertEqual((t[0]["side"], t[0]["reason"], t[0]["exit"]), (-1, "close", 97))
        self.assertAlmostEqual(t[0]["gross"], -(97 / 98.4 - 1))

    def test_no_lookahead_signal_bar_close_only(self):
        # Changing bars after the entry bar never moves the entry.
        base = [(100, 101, 99, 100), (100, 101.8, 100, 101.5), (101.6, 102, 101.2, 101.9)]
        a = I.run(I.sessions(day("2026-03-02", base + [FLAT] * 23)), "orb", dict(or_min=15, target_r=None, rvol=None))
        b = I.run(I.sessions(day("2026-03-02", base + [(150, 151, 149, 150)] * 23)), "orb",
                  dict(or_min=15, target_r=None, rvol=None))
        self.assertEqual((a[0]["date"], a[0]["entry"]), (b[0]["date"], b[0]["entry"]))

    def test_no_entry_after_cutoff(self):
        # Breakout bar closes at 14:15 (bar starting 14:00) -> too late.
        rows = [(100, 101, 99, 100)] + [FLAT] * 17 + [(100, 102, 100, 101.5)] + [FLAT] * 7
        self.assertEqual(I.run(I.sessions(day("2026-03-02", rows)), "orb",
                               dict(or_min=15, target_r=None, rvol=None)), [])

    def test_rvol_filter_needs_history_and_volume(self):
        quiet = [(100, 101, 99, 100, 100)] + [FLAT] * 25
        loud = [(100, 101, 99, 100, 1000), (100, 101.8, 100, 101.5)] + [FLAT] * 24
        sess = I.sessions([b for i in range(20) for b in day(f"2026-03-{i + 1:02d}", quiet)] + day("2026-03-25", loud))
        t = I.run(sess, "orb", dict(or_min=15, target_r=None, rvol=1.2))
        self.assertEqual([x["date"] for x in t], ["2026-03-25"])
        loud_but_short_history = I.sessions(day("2026-03-25", loud))
        self.assertEqual(I.run(loud_but_short_history, "orb", dict(or_min=15, target_r=None, rvol=1.2)), [])


class GapTests(unittest.TestCase):
    def test_gap_up_fade_to_prior_close(self):
        d1 = day("2026-03-02", [FLAT] * 26)                     # prior close 100
        d2 = day("2026-03-03", [(101, 101.2, 100.8, 101), (100.9, 101, 99.8, 100.2)] + [FLAT] * 24)
        t = I.run(I.sessions(d1 + d2), "gap_fade", dict(gap_pct=0.5, stop_x=1.0))
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["side"], t[0]["entry"], t[0]["exit"], t[0]["reason"]), (-1, 100.9, 100, "target"))

    def test_small_gap_and_first_day_skipped(self):
        d1 = day("2026-03-02", [(101, 101, 101, 101)] + [FLAT] * 25)
        d2 = day("2026-03-03", [(100.2, 100.3, 100.1, 100.2)] + [FLAT] * 25)
        self.assertEqual(I.run(I.sessions(d1 + d2), "gap_fade", dict(gap_pct=0.5, stop_x=None)), [])


class StatsAndWalkForwardTests(unittest.TestCase):
    def test_costs_and_stats(self):
        trades = [dict(gross=0.01), dict(gross=-0.005)]
        s = I.stats(trades, 5.0, 10)                           # 10 bps a round trip
        self.assertEqual(s["n_trades"], 2)
        self.assertAlmostEqual(s["mean_bps"], (90 - 60) / 2)
        self.assertAlmostEqual(s["total_return"], 1.009 * 0.994 - 1)
        self.assertLess(s["max_drawdown"], 0)

    def test_test_the_test(self):
        s = I.stats([dict(gross=0.01)], 0.0, 1)
        self.assertNotAlmostEqual(s["mean_bps"], 99.0)

    def test_walk_forward_uses_only_earlier_months(self):
        up = [(100, 101, 99, 100), (100, 101.8, 100, 101.5), (101.6, 102, 101.2, 101.9)] + [FLAT] * 22 + [(103,) * 4]
        bars = []
        for m in (1, 2, 3):
            for d in range(1, 21):
                bars += day(f"2026-{m:02d}-{d:02d}", up)
        sess = I.sessions(bars)
        res = I.walk_forward(sess, strategies=("orb",))
        oos, picks, n_oos = res["orb"]
        self.assertEqual([p[0] for p in picks], ["2026-03"])     # Jan+Feb = 40 sessions of history first
        self.assertTrue(all(t["date"].startswith("2026-03") for t in oos))
        self.assertEqual(n_oos, 20)


if __name__ == "__main__":
    unittest.main()
