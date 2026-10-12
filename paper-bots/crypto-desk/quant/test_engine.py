import math
from decimal import Decimal
import tempfile
from pathlib import Path
import unittest

from engine import (Rejected, fair_value_gate, no_vig, empirical_joint_probability,
                    quarter_kelly, kalshi_depth_ask, PaperLedger)


class GateTests(unittest.TestCase):
    def gate(self, **overrides):
        data = dict(p_lower=.65, bid=.48, ask=.50, fee_per_contract=.015,
                    slippage_per_contract=.005, quote_timestamp=99,
                    source_timestamp=95, now=100)
        data.update(overrides)
        return fair_value_gate(**data)

    def test_conservative_edge_includes_both_execution_costs(self):
        result = self.gate()
        self.assertTrue(result.accepted)
        self.assertAlmostEqual(result.effective_cost, .52)
        self.assertAlmostEqual(result.edge, .13)
        self.assertFalse(self.gate(p_lower=.53).accepted)

    def test_wide_and_crossed_book(self):
        self.assertFalse(self.gate(bid=.45).accepted)
        with self.assertRaises(Rejected):
            self.gate(bid=.51)

    def test_stale_quote_or_source_and_future_timestamp(self):
        for change in ({"quote_timestamp":97}, {"source_timestamp":69},
                       {"quote_timestamp":101}, {"source_timestamp":101}):
            with self.subTest(change=change), self.assertRaises(Rejected):
                self.gate(**change)

    def test_invalid_numbers_and_missing_fee(self):
        for change in ({"p_lower":math.nan}, {"ask":math.inf},
                       {"fee_per_contract":None}, {"slippage_per_contract":-.01},
                       {"p_lower":1.1}, {"now":math.nan}):
            with self.subTest(change=change), self.assertRaises(Rejected):
                self.gate(**change)

    def test_effective_cost_reaches_payout(self):
        self.assertFalse(self.gate(ask=.99, bid=.98).accepted)


class ProbabilityTests(unittest.TestCase):
    def test_no_vig(self):
        result = no_vig({"home":1.80, "away":2.10}, complete=True, mutually_exclusive=True)
        self.assertAlmostEqual(sum(result.values()), 1)
        self.assertAlmostEqual(result["home"], 2.1 / 3.9)

    def test_no_vig_requires_exhaustive_exclusive_outcomes(self):
        for complete, exclusive in ((False, True), (True, False)):
            with self.assertRaises(Rejected):
                no_vig({"home":1.8,"away":2.1}, complete=complete, mutually_exclusive=exclusive)
        with self.assertRaises(Rejected):
            no_vig({"home":1.8,"away":math.nan}, complete=True, mutually_exclusive=True)

    def test_correlated_joint_is_not_product_of_marginals(self):
        correlated = [[True, True, False, False], [True, True, False, False]]
        self.assertEqual(empirical_joint_probability(correlated), .5)
        anti_correlated = [[True, True, False, False], [False, False, True, True]]
        self.assertEqual(empirical_joint_probability(anti_correlated), 0)

    def test_joint_rejects_unaligned_or_non_boolean(self):
        for legs in ([], [[]], [[True], [True, False]], [[1], [True]]):
            with self.subTest(legs=legs), self.assertRaises(Rejected):
                empirical_joint_probability(legs)


class RiskTests(unittest.TestCase):
    def test_quarter_kelly_formula_and_ceiling(self):
        size = quarter_kelly(p_lower=.65, effective_cost=.5, bankroll=1000)
        self.assertAlmostEqual(size.quarter_kelly_fraction, .075)
        self.assertEqual(size.contracts, 20)
        self.assertEqual(size.spend, 10)

    def test_aggregate_exposure_and_negative_edge(self):
        size = quarter_kelly(p_lower=.65, effective_cost=.5, bankroll=1000, current_exposure=49)
        self.assertEqual(size.contracts, 2)
        self.assertEqual(quarter_kelly(p_lower=.4, effective_cost=.5, bankroll=1000).contracts, 0)
        self.assertEqual(quarter_kelly(p_lower=.8, effective_cost=.5, bankroll=1000, current_exposure=60).contracts, 0)

    def test_invalid_risk_inputs(self):
        for overrides in ({"effective_cost":1}, {"bankroll":0}, {"current_exposure":-1}, {"bankroll":math.inf}):
            params = dict(p_lower=.65, effective_cost=.5, bankroll=1000)
            params.update(overrides)
            with self.assertRaises(Rejected):
                quarter_kelly(**params)


class DepthTests(unittest.TestCase):
    def test_opposing_bid_complement_and_decimal_weighted_depth(self):
        book = {"yes_dollars":[["0.45","10"]], "no_dollars":[["0.40","4"], ["0.50","3"]]}
        fill = kalshi_depth_ask(book, side="yes", quantity="5", quote_timestamp=99, now=100)
        self.assertEqual(fill.total_cost, Decimal("2.70"))
        self.assertEqual(fill.average_ask, Decimal(".54"))
        self.assertEqual(fill.worst_ask, Decimal(".60"))
        no = kalshi_depth_ask(book, side="no", quantity="2", quote_timestamp=99, now=100)
        self.assertEqual(no.average_ask, Decimal(".55"))

    def test_insufficient_or_invalid_depth_and_stale(self):
        for book in ({"no_dollars":[]}, {"no_dollars":[[".5","1"]]},
                     {"no_dollars":[["NaN","20"]]}, {"no_dollars":[[".5","-1"]]}):
            with self.subTest(book=book), self.assertRaises(Rejected):
                kalshi_depth_ask(book, side="yes", quantity=5, quote_timestamp=99, now=100)
        with self.assertRaises(Rejected):
            kalshi_depth_ask({"no_dollars":[[".5","20"]]}, side="yes", quantity=5, quote_timestamp=97, now=100)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = PaperLedger(":memory:")
        self.position = self.ledger.enter(market="SYNTHETIC", side="yes", quantity=10, ask=".40", entry_fee=".20")

    def tearDown(self):
        self.ledger.close()

    def test_partial_and_final_exit_net_realized_pnl(self):
        # $2.4 proceeds - $1.6 basis - $.08 entry fees - $.04 exit fees = $.68.
        first = self.ledger.exit(position_id=self.position, quantity=4, bid=".60", exit_fee=".04")
        self.assertEqual(first, Decimal(".68"))
        partial = self.ledger.position(self.position)
        self.assertEqual(Decimal(partial["remaining"]), Decimal(6))
        self.assertEqual(Decimal(partial["unallocated_entry_fee"]), Decimal(".12"))
        # $1.8 proceeds - $2.4 basis - $.12 entry fees - $.06 exit fees = -$.78.
        last = self.ledger.exit(position_id=self.position, quantity=6, bid=".30", exit_fee=".06")
        self.assertEqual(last, Decimal("-.78"))
        final = self.ledger.position(self.position)
        self.assertEqual(Decimal(final["realized_pnl"]), Decimal("-.10"))
        self.assertEqual(Decimal(final["remaining"]), 0)
        self.assertEqual(Decimal(final["unallocated_entry_fee"]), 0)

    def test_rejected_oversell_is_atomic(self):
        before = self.ledger.position(self.position)
        with self.assertRaises(Rejected):
            self.ledger.exit(position_id=self.position, quantity=11, bid=.60, exit_fee=.04)
        self.assertEqual(self.ledger.position(self.position), before)
        self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM fills").fetchone()[0], 1)

    def test_database_error_rolls_back_position_and_fill(self):
        self.ledger.db.execute("CREATE TRIGGER forbid_exit BEFORE INSERT ON fills WHEN NEW.kind = 'exit' BEGIN SELECT RAISE(ABORT, 'simulated failure'); END;")
        before = self.ledger.position(self.position)
        with self.assertRaises(Exception):
            self.ledger.exit(position_id=self.position, quantity=3, bid=.60, exit_fee=.04)
        self.assertEqual(self.ledger.position(self.position), before)

    def test_invalid_fill_inputs(self):
        for fee in (None, math.nan, -1):
            with self.assertRaises(Rejected):
                self.ledger.exit(position_id=self.position, quantity=1, bid=.6, exit_fee=fee)

    def test_reopen_persists_accounting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "paper.sqlite")
            ledger = PaperLedger(path)
            identifier = ledger.enter(market="SYNTHETIC", side="no", quantity=5, ask=".30", entry_fee=".05")
            ledger.exit(position_id=identifier, quantity=5, bid=".70", exit_fee=".05")
            ledger.close()
            reopened = PaperLedger(path)
            self.assertEqual(Decimal(reopened.position(identifier)["realized_pnl"]), Decimal("1.90"))
            reopened.close()


if __name__ == "__main__":
    unittest.main()
