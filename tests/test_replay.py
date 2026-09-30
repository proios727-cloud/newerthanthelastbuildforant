import json
import unittest

import research
from research import replay, tournament


class ReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars, _ = research.load_bars()
        cls.r = {k: replay.build(m, cls.bars) for k, m in replay.MODES.items()}

    def test_matches_tournament(self):
        board = {b["name"]: b for b in tournament.run()["leaderboard"]}
        for m in self.r.values():
            b = board[m["name"]]
            self.assertEqual(len(m["trades"]), b["out_of_sample"]["trades"])
            self.assertAlmostEqual(m["final"]["equity"], b["snowball"]["equity"], places=2)

    def test_no_lookahead(self):
        for m in self.r.values():
            for f in m["frames"]:
                done = m["trades"][:f["n"]]
                self.assertTrue(all(t["exit"] <= f["d"] for t in done))

    def test_frames_monotone_and_end_on_final(self):
        for m in self.r.values():
            ns = [f["n"] for f in m["frames"]]
            self.assertEqual(ns, sorted(ns))
            self.assertEqual(m["frames"][-1]["eq"], m["final"]["equity"])

    def test_tradingview_crosscheck(self):
        self.assertLess(replay.crosscheck(self.bars), 0.01)


if __name__ == "__main__":
    unittest.main()
