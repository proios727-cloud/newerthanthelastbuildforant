"""Isolated paper bankroll accounting. Status refresh only; never collects live data."""
from __future__ import annotations
import argparse
from decimal import Decimal
import json
import sqlite3
from pathlib import Path
import time

from engine import PaperLedger, Rejected, decimal, fresh, number


class PaperAccount(PaperLedger):
    def __init__(self, path, *, desk, bankroll):
        if desk not in ('crypto', 'sports'):
            raise Rejected('desk must be crypto or sports')
        initial = decimal(bankroll, 'bankroll')
        if initial <= 0:
            raise Rejected('bankroll must be positive')
        super().__init__(str(path))
        try:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), desk TEXT NOT NULL, initial TEXT NOT NULL, equity_peak TEXT NOT NULL)')
            row = self.db.execute('SELECT desk, initial FROM account WHERE id=1').fetchone()
            if row is None:
                # Never reinterpret an existing unbound ledger as a funded account.
                if self.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0]:
                    raise Rejected('existing unbound ledger contains fills')
                self.db.execute('INSERT INTO account VALUES (1, ?, ?, ?)', (desk, str(initial), str(initial)))
            elif row[0] != desk:
                raise Rejected('database is bound to a different desk')
            elif Decimal(row[1]) != initial:
                raise Rejected('persisted initial bankroll cannot be changed')
            self.db.commit()
        except BaseException:
            self.db.rollback()
            self.db.close()
            raise
        self.desk, self.initial = desk, initial

    def _validate(self, quantity, price, fee):
        q, p, f = decimal(quantity, 'quantity'), decimal(price, 'price'), decimal(fee, 'fee')
        if q <= 0 or p < 0 or f < 0 or (self.desk == 'sports' and p > 1):
            raise Rejected('invalid paper fill quantity, price or fee')
        return q, p, f

    def _cash(self):
        cash = self.initial
        for kind, quantity, price, fee in self.db.execute('SELECT kind, quantity, price, fee FROM fills'):
            q, p, f = map(Decimal, (quantity, price, fee))
            cash += q * p - f if kind == 'exit' else -(q * p + f)
        return cash

    def enter(self, *, market, side, quantity, ask, entry_fee):
        q, price, fee = self._validate(quantity, ask, entry_fee)
        if not isinstance(market, str) or not market.strip() or side not in (('yes', 'long') if self.desk == 'crypto' else ('yes', 'no')) or price <= 0:
            raise Rejected('invalid market, side or entry ask')
        try:
            self.db.execute('BEGIN IMMEDIATE')
            if q * price + fee > self._cash():
                raise Rejected('entry exceeds available paper cash')
            cursor = self.db.execute("INSERT INTO positions VALUES (NULL, ?, ?, ?, ?, ?, '0')", (market, side, str(q), str(price), str(fee)))
            identifier = cursor.lastrowid
            self.db.execute("INSERT INTO fills VALUES (NULL, ?, 'entry', ?, ?, ?, '0')", (identifier, str(q), str(price), str(fee)))
            self.db.commit()
            return identifier
        except BaseException:
            self.db.rollback()
            raise

    def exit(self, *, position_id, quantity, bid, exit_fee):
        q, price, fee = self._validate(quantity, bid, exit_fee)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT remaining, unit_cost, unallocated_entry_fee, realized FROM positions WHERE id=?', (position_id,)).fetchone()
            if row is None:
                raise Rejected('unknown paper position')
            remaining, cost, entry_fee, realized = map(Decimal, row)
            if q > remaining:
                raise Rejected('exit exceeds remaining quantity')
            if self._cash() + q * price - fee < 0:
                raise Rejected('exit fee exceeds available paper cash and proceeds')
            allocated_fee = entry_fee * q / remaining
            profit = q * (price - cost) - allocated_fee - fee
            self.db.execute('UPDATE positions SET remaining=?, unallocated_entry_fee=?, realized=? WHERE id=?', (str(remaining-q), str(entry_fee-allocated_fee), str(realized+profit), position_id))
            self.db.execute("INSERT INTO fills VALUES (NULL, ?, 'exit', ?, ?, ?, ?)", (position_id, str(q), str(price), str(fee), str(profit)))
            self.db.commit()
            return profit
        except BaseException:
            self.db.rollback()
            raise

    def snapshot(self, *, marks=None, now=None, max_mark_age=5):
        """Marks map position ID to bid, exit_fee TOTAL and timestamp.

        Every open position requires a valid mark. Peak/drawdown are sampled only
        when equity is available; absence of prices never implies zero value.
        """
        now = time.time() if now is None else number(now, 'now')
        max_mark_age = number(max_mark_age, 'max_mark_age')
        if now < 0 or max_mark_age < 0:
            raise Rejected('invalid snapshot time or maximum age')
        marks = {} if marks is None else marks
        try:
            self.db.execute('BEGIN IMMEDIATE')
            cash = self._cash()
            fees = sum((Decimal(row[0]) for row in self.db.execute('SELECT fee FROM fills')), Decimal(0))
            realized, basis, liquidation = Decimal(0), Decimal(0), Decimal(0)
            positions, unavailable = [], []
            for identifier, market, side, quantity, cost, entry_fee, pnl in self.db.execute('SELECT id, market, side, remaining, unit_cost, unallocated_entry_fee, realized FROM positions ORDER BY id'):
                q, price, fee, profit = map(Decimal, (quantity, cost, entry_fee, pnl))
                realized += profit
                if q == 0:
                    continue
                basis += q * price + fee
                position = dict(id=identifier, market=market, side=side, quantity=str(q), remaining_basis=str(q*price+fee))
                mark = marks.get(identifier, marks.get(str(identifier)))
                try:
                    if not isinstance(mark, dict):
                        raise Rejected('missing explicit executable mark')
                    bid = decimal(mark.get('bid'), 'mark bid')
                    exit_fee = decimal(mark.get('exit_fee'), 'mark exit fee')
                    if bid < 0 or (self.desk == 'sports' and bid > 1) or exit_fee < 0:
                        raise Rejected('invalid mark bid or exit fee')
                    fresh(mark.get('timestamp'), now, max_mark_age, 'mark')
                    value = q*bid-exit_fee
                    liquidation += value
                    position['net_liquidation_value'] = str(value)
                except Rejected as error:
                    unavailable.append(dict(position_id=identifier, reason=str(error)))
                positions.append(position)
            peak = Decimal(self.db.execute('SELECT equity_peak FROM account WHERE id=1').fetchone()[0])
            equity = None if unavailable else cash + liquidation
            if equity is not None:
                peak = max(peak, equity)
                self.db.execute('UPDATE account SET equity_peak=? WHERE id=1', (str(peak),))
            self.db.commit()
            return dict(mode='PAPER ONLY', desk=self.desk, quantity_unit='asset units' if self.desk == 'crypto' else 'binary contracts', initial_bankroll=str(self.initial), cash=str(cash),
                        entry_basis_open=str(basis), realized_pnl=str(realized), fees_paid=str(fees),
                        equity=None if equity is None else str(equity),
                        unrealized_pnl=None if equity is None else str(liquidation-basis),
                        total_pnl=None if equity is None else str(equity-self.initial),
                        sampled_equity_peak=str(peak),
                        sampled_drawdown=None if equity is None else str(peak-equity),
                        sampled_drawdown_fraction=None if equity is None else str((peak-equity)/peak),
                        open_positions=positions, unavailable_marks=unavailable, snapshot_timestamp=now)
        except BaseException:
            self.db.rollback()
            raise


def synthetic_demo(account):
    """Idempotent demo on an empty account, intentionally no data adapters."""
    if account.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0]:
        raise Rejected('synthetic demo requires an empty account database')
    # Scale demo cash risk to any positive bankroll; fractional contracts are simulated.
    q = account.initial / Decimal(100)
    identifier = account.enter(market=f'SYNTHETIC-{account.desk.upper()}-NO-REAL-MARKET', side='yes', quantity=q, ask='.40', entry_fee=q*Decimal('.01'))
    account.exit(position_id=identifier, quantity=q/2, bid='.60', exit_fee=q*Decimal('.005'))
    now = time.time()
    report = account.snapshot(marks={identifier: dict(bid='.55', exit_fee=str(q*Decimal('.005')), timestamp=now)}, now=now)
    report['label'] = 'SYNTHETIC PAPER DEMO: hypothetical prices, fees and fills; no live data or orders'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desk', required=True, choices=('crypto', 'sports'))
    parser.add_argument('--bankroll', help='Positive immutable initial paper bankroll; required for new databases')
    parser.add_argument('--db', type=Path)
    parser.add_argument('--demo', action='store_true', help='Create explicitly synthetic fills on empty account only')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--marks', type=Path, help='Explicit local JSON marks; no data collection')
    parser.add_argument('--max-mark-age', type=float, default=5)
    parser.add_argument('--watch', type=float, help='Refresh status every positive number of seconds; no collection')
    args = parser.parse_args()
    if args.watch is not None and (number(args.watch, 'watch') <= 0 or args.demo):
        parser.error('--watch must be positive and cannot accompany --demo')
    path = args.db or Path(__file__).resolve().parents[1] / 'desks' / args.desk / 'paper.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    bankroll = args.bankroll
    if bankroll is None:
        if not path.exists():
            parser.error('--bankroll is required when creating a new paper database')
        lookup = sqlite3.connect(str(path))
        try:
            try:
                row = lookup.execute('SELECT initial FROM account WHERE id=1').fetchone()
            except sqlite3.OperationalError:
                row = None
        finally:
            lookup.close()
        if row is None:
            parser.error('--bankroll is required when creating a new paper account')
        bankroll = row[0]
    account = PaperAccount(path, desk=args.desk, bankroll=bankroll)
    try:
        while True:
            marks = json.loads(args.marks.read_text()) if args.marks else None
            report = synthetic_demo(account) if args.demo else account.snapshot(marks=marks, max_mark_age=args.max_mark_age)
            output = json.dumps(report, indent=2, allow_nan=False) + '\n'
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(output, encoding='utf-8')
            print(output, flush=True)
            if args.watch is None:
                break
            time.sleep(args.watch)
    finally:
        account.close()


if __name__ == '__main__':
    main()
