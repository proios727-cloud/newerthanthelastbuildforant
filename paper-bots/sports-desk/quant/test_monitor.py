from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from engine import Rejected
from monitor import PaperAccount, synthetic_demo


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'crypto.sqlite'
        self.account = PaperAccount(self.path, desk='crypto', bankroll='100')

    def tearDown(self):
        self.account.close()
        self.directory.cleanup()

    def enter(self):
        return self.account.enter(market='SYNTHETIC', side='yes', quantity=10, ask='.40', entry_fee='.10')

    def mark(self, identifier, bid='.60', fee='.10', timestamp=100):
        return {identifier: dict(bid=bid, exit_fee=fee, timestamp=timestamp)}

    def test_initial_and_no_position_equity(self):
        report = self.account.snapshot(now=100)
        self.assertEqual(Decimal(report['cash']), 100)
        self.assertEqual(Decimal(report['equity']), 100)
        self.assertEqual(Decimal(report['realized_pnl']), 0)

    def test_cash_realized_fees_partial_and_final_exit(self):
        identifier = self.enter()
        self.assertEqual(Decimal(self.account.snapshot(now=100)['cash']), Decimal('95.90'))
        profit = self.account.exit(position_id=identifier, quantity=5, bid='.60', exit_fee='.05')
        self.assertEqual(profit, Decimal('.90'))
        partial = self.account.snapshot(marks=self.mark(identifier, bid='.55', fee='.05'), now=100)
        self.assertEqual(Decimal(partial['cash']), Decimal('98.85'))
        self.assertEqual(Decimal(partial['realized_pnl']), Decimal('.90'))
        self.assertEqual(Decimal(partial['unrealized_pnl']), Decimal('.65'))
        self.assertEqual(Decimal(partial['total_pnl']), Decimal('1.55'))
        self.assertEqual(Decimal(partial['fees_paid']), Decimal('.15'))
        self.account.exit(position_id=identifier, quantity=5, bid='.30', exit_fee='.05')
        final = self.account.snapshot(now=101)
        self.assertEqual(Decimal(final['cash']), Decimal('100.30'))
        self.assertEqual(Decimal(final['realized_pnl']), Decimal('.30'))
        self.assertEqual(Decimal(final['total_pnl']), Decimal('.30'))
        self.assertEqual(Decimal(final['unrealized_pnl']), 0)
        self.assertEqual(Decimal(final['fees_paid']), Decimal('.20'))

    def test_missing_stale_future_and_invalid_marks_make_equity_unavailable(self):
        identifier = self.enter()
        for marks in (None, self.mark(identifier,timestamp=94), self.mark(identifier,timestamp=101),
                      self.mark(identifier, fee=None), self.mark(identifier,bid='NaN')):
            with self.subTest(marks=marks):
                report = self.account.snapshot(marks=marks, now=100)
                self.assertIsNone(report['equity'])
                self.assertIsNone(report['unrealized_pnl'])
                self.assertIsNone(report['sampled_drawdown'])
                self.assertEqual(Decimal(report['sampled_equity_peak']), 100)
                self.assertEqual(len(report['unavailable_marks']), 1)

    def test_mark_all_open_positions(self):
        first, second = self.enter(), self.enter()
        self.assertIsNone(self.account.snapshot(marks=self.mark(first),now=100)['equity'])
        marks = {**self.mark(first), **self.mark(second)}
        self.assertIsNotNone(self.account.snapshot(marks=marks,now=100)['equity'])

    def test_sampled_peak_and_drawdown_survive_reopen(self):
        identifier = self.enter()
        first = self.account.snapshot(marks=self.mark(identifier), now=100)
        self.assertEqual(Decimal(first['sampled_equity_peak']), Decimal('101.80'))
        second = self.account.snapshot(marks=self.mark(identifier,bid='.30'),now=100)
        self.assertEqual(Decimal(second['equity']), Decimal('98.80'))
        self.assertEqual(Decimal(second['sampled_drawdown']), Decimal('3.00'))
        self.account.close()
        self.account = PaperAccount(self.path, desk='crypto', bankroll=100)
        self.assertEqual(Decimal(self.account.snapshot(now=101)['sampled_equity_peak']), Decimal('101.80'))

    def test_overdraft_rejected_before_any_mutation(self):
        with self.assertRaises(Rejected):
            self.account.enter(market='SYNTHETIC',side='yes',quantity=200,ask='.50',entry_fee='.01')
        self.assertEqual(self.account.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0],0)
        self.assertEqual(self.account.db.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
        self.assertEqual(Decimal(self.account.snapshot(now=100)['cash']),100)

    def test_exit_fee_cannot_overdraw_account(self):
        identifier = self.account.enter(market='SYNTHETIC', side='yes', quantity=200,ask='.50',entry_fee=0)
        with self.assertRaises(Rejected):
            self.account.exit(position_id=identifier,quantity=1,bid=0,exit_fee='.01')
        self.assertEqual(Decimal(self.account.position(identifier)['remaining']), 200)

    def test_entry_database_failure_rolls_back_cash_and_position(self):
        self.account.db.execute("CREATE TRIGGER forbid_entry BEFORE INSERT ON fills BEGIN SELECT RAISE(ABORT,'simulated failure'); END;")
        with self.assertRaises(sqlite3.IntegrityError):
            self.enter()
        self.assertEqual(self.account.db.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
        self.assertEqual(Decimal(self.account.snapshot(now=100)['cash']),100)

    def test_second_connection_sees_persisted_cash(self):
        other = PaperAccount(self.path,desk='crypto',bankroll=100)
        try:
            self.account.enter(market='SYNTHETIC',side='yes',quantity=180,ask='.50',entry_fee=0)
            with self.assertRaises(Rejected):
                other.enter(market='SYNTHETIC',side='yes',quantity=21,ask='.50',entry_fee=0)
            self.assertEqual(Decimal(other.snapshot(now=100)['cash']),10)
        finally:
            other.close()

    def test_desk_and_initial_bankroll_are_immutable(self):
        for desk, bankroll in (('sports',100), ('crypto',101)):
            with self.subTest(desk=desk,bankroll=bankroll), self.assertRaises(Rejected):
                PaperAccount(self.path,desk=desk,bankroll=bankroll)
        other_path = Path(self.directory.name)/'sports.sqlite'
        other = PaperAccount(other_path,desk='sports',bankroll=50)
        self.enter()
        self.assertEqual(Decimal(other.snapshot(now=100)['cash']),50)
        other.close()

    def test_invalid_initial_bankroll(self):
        for bankroll in ('NaN','Infinity',0,-1,None):
            with self.subTest(bankroll=bankroll), self.assertRaises(Rejected):
                PaperAccount(Path(self.directory.name)/'invalid.sqlite',desk='sports',bankroll=bankroll)

    def test_crypto_spot_prices_and_fees(self):
        identifier = self.account.enter(market='BTC-SYNTHETIC', side='long', quantity='.001', ask='60000', entry_fee='.10')
        report = self.account.snapshot(marks=self.mark(identifier,bid='61000',fee='.10'),now=100)
        self.assertEqual(Decimal(report['unrealized_pnl']), Decimal('.80'))
        self.assertEqual(report['quantity_unit'], 'asset units')
        profit = self.account.exit(position_id=identifier,quantity='.001',bid='61000',exit_fee='.10')
        self.assertEqual(profit,Decimal('.80'))
        self.assertEqual(Decimal(self.account.snapshot(now=100)['cash']),Decimal('100.80'))

    def test_sports_prices_remain_binary(self):
        sports = PaperAccount(Path(self.directory.name)/'sports.sqlite',desk='sports',bankroll=100)
        try:
            with self.assertRaises(Rejected):
                sports.enter(market='SYNTHETIC',side='yes',quantity=1,ask=60000,entry_fee=0)
            identifier = sports.enter(market='SYNTHETIC',side='yes',quantity=1,ask='.50',entry_fee=0)
            self.assertIsNone(sports.snapshot(marks=self.mark(identifier,bid='2'),now=100)['equity'])
            with self.assertRaises(Rejected):
                sports.exit(position_id=identifier,quantity=1,bid=2,exit_fee=0)
        finally:
            sports.close()

    def test_synthetic_demo_label_and_repeated_demo_rejection(self):
        report = synthetic_demo(self.account)
        self.assertIn('SYNTHETIC PAPER DEMO',report['label'])
        self.assertEqual(Decimal(report['realized_pnl']), Decimal('.09'))
        with self.assertRaises(Rejected):
            synthetic_demo(self.account)


if __name__ == '__main__':
    unittest.main()
