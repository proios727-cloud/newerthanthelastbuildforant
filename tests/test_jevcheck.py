import unittest

import judge
from fund import catalyst, jevcheck


def trade(pnl, credit=100.0, p=0.1, mode="live"):
    return {"pnl": pnl, "credit": credit, "jev_p": p, "jev_mode": mode}


def book(taken=(), ghosts=(), errors=0):
    return {"closed": list(taken), "ghost_closed": list(ghosts), "positions": {}, "ghosts": {},
            "log": [{"kind": "put_skip", "reason": "jev unavailable", "jev_mode": "error"}] * errors}


class JevCheckTests(unittest.TestCase):
    def test_bar_is_frozen(self):
        self.assertEqual((jevcheck.REGISTERED, jevcheck.MIN_TAKEN, jevcheck.MIN_GHOSTS, jevcheck.MIN_EDGE,
                          jevcheck.MAX_ERROR_RATE), ("2026-09-29", 20, 8, 0.25, 0.10))

    def test_insufficient_until_both_samples_fill(self):
        r = jevcheck.evaluate(book([trade(50)] * 19, [trade(-200, p=0.9)] * 8))
        self.assertEqual(r["verdict"], "insufficient")

    def test_keep_when_vetoed_sales_do_clearly_worse(self):
        r = jevcheck.evaluate(book([trade(50)] * 20, [trade(-100, p=0.9)] * 8))
        self.assertEqual((r["verdict"], r["edge"]), ("keep", 1.5))
        self.assertGreater(r["mean_p_losers"], r["mean_p_winners"])

    def test_drop_when_vetoes_would_have_won(self):
        r = jevcheck.evaluate(book([trade(10)] * 20, [trade(50, p=0.9)] * 8))
        self.assertEqual(r["verdict"], "drop")

    def test_inconclusive_then_drop_after_double_sample(self):
        self.assertEqual(jevcheck.evaluate(book([trade(30)] * 20, [trade(20)] * 8))["verdict"], "inconclusive")
        self.assertEqual(jevcheck.evaluate(book([trade(30)] * 20, [trade(20)] * 16))["verdict"], "drop")

    def test_stub_trades_do_not_count_and_errors_make_it_unreliable(self):
        r = jevcheck.evaluate(book([trade(50, mode="stub")] * 30))
        self.assertEqual((r["verdict"], r["taken_live"]), ("insufficient", 0))
        r = jevcheck.evaluate(book([trade(50)] * 20, [trade(-100)] * 8, errors=5))
        self.assertEqual(r["verdict"], "unreliable")

    def test_pools_both_books(self):
        r = jevcheck.evaluate(book([trade(50)] * 10, [trade(-100)] * 4), book([trade(5, credit=10)] * 10, [trade(-10, credit=10)] * 4))
        self.assertEqual((r["taken_live"], r["ghosts_closed"], r["verdict"]), (20, 8, "keep"))


class HeadlineCleaningTests(unittest.TestCase):
    def test_hidden_characters_are_removed_and_length_capped(self):
        self.assertEqual(catalyst.clean("AAPL​  beats‮ estimates\n"), "AAPL beats estimates")
        self.assertEqual(len(catalyst.clean("x" * 500)), 200)

    def test_only_clean_text_reaches_the_judge(self):
        seen = {}

        class Spy(judge.StubClient):
            def ask(self, state, questions):
                seen.update(state)
                return super().ask(state, questions)

        catalyst.assess(Spy(), "AAPL", ["ok​news", "​​"])
        self.assertEqual(seen["headlines"], ["ok news"])
        self.assertIsNone(catalyst.assess(Spy(), "AAPL", ["​"]))


if __name__ == "__main__":
    unittest.main()
