"""Paper-only pricing and accounting primitives. No network or order submission code."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import math
import sqlite3
from typing import Mapping, Sequence


class Rejected(ValueError):
    """Inputs fail the required validation or execution/risk gate."""


def number(value, name: str) -> float:
    if isinstance(value, bool):
        raise Rejected(f"{name}: boolean is not numeric")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise Rejected(f"{name}: numeric value required") from None
    if not math.isfinite(result):
        raise Rejected(f"{name}: finite value required")
    return result


def decimal(value, name: str) -> Decimal:
    if isinstance(value, bool):
        raise Rejected(f"{name}: boolean is not numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise Rejected(f"{name}: decimal required") from None
    if not result.is_finite():
        raise Rejected(f"{name}: finite value required")
    return result


def probability(value, name: str) -> float:
    value = number(value, name)
    if not 0 <= value <= 1:
        raise Rejected(f"{name}: must be in [0, 1]")
    return value


def fresh(timestamp, now, max_age, name):
    timestamp, now, max_age = (number(timestamp, name), number(now, "now"), number(max_age, "max_age"))
    if max_age < 0 or timestamp < 0 or now < 0 or timestamp > now or now - timestamp > max_age:
        raise Rejected(f"{name}: future, invalid or stale timestamp")


@dataclass(frozen=True)
class Decision:
    accepted: bool
    conservative_probability: float
    effective_cost: float
    edge: float
    reason: str


def fair_value_gate(*, p_lower, bid, ask, fee_per_contract, slippage_per_contract,
                    quote_timestamp, source_timestamp, now, max_quote_age=2,
                    max_source_age=30, max_spread=.03, minimum_edge=.02) -> Decision:
    """Use an externally calibrated lower bound; do not manufacture confidence."""
    p = probability(p_lower, "p_lower")
    bid, ask = probability(bid, "bid"), probability(ask, "ask")
    fee, slip = number(fee_per_contract, "fee_per_contract"), number(slippage_per_contract, "slippage_per_contract")
    spread_limit, edge_limit = number(max_spread, "max_spread"), number(minimum_edge, "minimum_edge")
    if fee < 0 or slip < 0 or spread_limit < 0 or edge_limit < 0:
        raise Rejected("fees, slippage and gate limits must be nonnegative")
    if bid > ask or ask <= 0:
        raise Rejected("crossed book or invalid executable ask")
    fresh(quote_timestamp, now, max_quote_age, "quote")
    fresh(source_timestamp, now, max_source_age, "source")
    cost = ask + fee + slip
    edge = p - cost
    if cost >= 1:
        return Decision(False, p, cost, edge, "effective cost reaches payout")
    if ask - bid > spread_limit + 1e-12:
        return Decision(False, p, cost, edge, "spread exceeds limit")
    accepted = edge > 0 and edge >= edge_limit
    return Decision(accepted, p, cost, edge, "eligible for paper review" if accepted else "insufficient conservative edge")


def no_vig(odds: Mapping[str, float], *, complete: bool, mutually_exclusive: bool) -> dict[str, float]:
    """Normalize decimal odds ONLY for a supplied exhaustive, exclusive market."""
    if complete is not True or mutually_exclusive is not True or len(odds) < 2:
        raise Rejected("complete mutually exclusive market with at least two outcomes required")
    implied = {}
    for outcome, value in odds.items():
        value = number(value, "decimal odds")
        if value <= 1:
            raise Rejected("decimal odds must exceed 1")
        implied[outcome] = 1 / value
    total = sum(implied.values())
    return {key: value / total for key, value in implied.items()}


def empirical_joint_probability(legs: Sequence[Sequence[bool]]) -> float:
    """Each index represents the same simulated scenario across every leg."""
    if not legs or not legs[0]:
        raise Rejected("nonempty aligned simulation outcomes required")
    size = len(legs[0])
    if any(len(leg) != size for leg in legs):
        raise Rejected("unequal simulation lengths")
    if any(type(value) is not bool for leg in legs for value in leg):
        raise Rejected("simulation outcomes must be booleans")
    return sum(all(leg[index] for leg in legs) for index in range(size)) / size


@dataclass(frozen=True)
class Size:
    contracts: int
    spend: float
    quarter_kelly_fraction: float


def quarter_kelly(*, p_lower, effective_cost, bankroll, max_position_fraction=.01,
                  current_exposure=0, max_exposure_fraction=.05) -> Size:
    """Binary $1 payout, cost includes estimated fees/slippage. Cash risk ceilings."""
    p = probability(p_lower, "p_lower")
    cost = number(effective_cost, "effective_cost")
    bank, exposure = number(bankroll, "bankroll"), number(current_exposure, "current_exposure")
    position_limit = probability(max_position_fraction, "max_position_fraction")
    exposure_limit = probability(max_exposure_fraction, "max_exposure_fraction")
    if not 0 < cost < 1 or bank <= 0 or exposure < 0:
        raise Rejected("invalid cost, bankroll or exposure")
    fraction = max(0., (p - cost) / (1 - cost)) / 4
    budget = min(bank * fraction, bank * position_limit, max(0., bank * exposure_limit - exposure))
    count = math.floor(budget / cost)
    return Size(count, count * cost, fraction)


@dataclass(frozen=True)
class Fill:
    quantity: Decimal
    average_ask: Decimal
    total_cost: Decimal
    worst_ask: Decimal


def kalshi_depth_ask(orderbook_fp: Mapping, *, side: str, quantity,
                     quote_timestamp, now, max_quote_age=2) -> Fill:
    """Buy YES against NO bids (ask = 1 - NO bid), and vice versa.

    Expects orderbook_fp {yes_dollars: [[price, size], ...], no_dollars: ...}.
    Returned cost excludes fees, which callers must add explicitly. All math Decimal.
    """
    fresh(quote_timestamp, now, max_quote_age, "quote")
    if side not in ("yes", "no"):
        raise Rejected("side must be yes or no")
    requested = decimal(quantity, "quantity")
    if requested <= 0:
        raise Rejected("positive quantity required")
    field = "no_dollars" if side == "yes" else "yes_dollars"
    levels = orderbook_fp.get(field)
    if not isinstance(levels, list) or not levels:
        raise Rejected("missing opposing bid depth")
    asks = []
    for level in levels:
        if not isinstance(level, (list, tuple)) or len(level) != 2:
            raise Rejected("invalid depth level")
        bid, size = decimal(level[0], "bid"), decimal(level[1], "size")
        if not 0 <= bid <= 1 or size <= 0:
            raise Rejected("invalid bid or depth size")
        asks.append((Decimal(1) - bid, size))
    remaining, total, worst = requested, Decimal(0), Decimal(0)
    for ask, size in sorted(asks):
        taken = min(size, remaining)
        total += taken * ask
        worst = ask
        remaining -= taken
        if remaining == 0:
            return Fill(requested, total / requested, total, worst)
    raise Rejected("insufficient executable depth")


class PaperLedger:
    """SQLite local simulated fills; explicitly no ability to place live orders."""
    def __init__(self, path="paper.sqlite"):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY, market TEXT NOT NULL, side TEXT NOT NULL,
                remaining TEXT NOT NULL, unit_cost TEXT NOT NULL,
                unallocated_entry_fee TEXT NOT NULL, realized TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS fills (
                id INTEGER PRIMARY KEY, position_id INTEGER NOT NULL REFERENCES positions(id),
                kind TEXT NOT NULL, quantity TEXT NOT NULL, price TEXT NOT NULL,
                fee TEXT NOT NULL, realized TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    @staticmethod
    def _validate(quantity, price, fee):
        q, p, f = decimal(quantity, "quantity"), decimal(price, "price"), decimal(fee, "fee")
        if q <= 0 or not 0 <= p <= 1 or f < 0:
            raise Rejected("invalid paper fill quantity, price or fee")
        return q, p, f

    def enter(self, *, market, side, quantity, ask, entry_fee) -> int:
        q, price, fee = self._validate(quantity, ask, entry_fee)
        if not isinstance(market, str) or not market.strip() or side not in ("yes", "no") or price <= 0:
            raise Rejected("invalid market, side or entry ask")
        with self.db:
            cursor = self.db.execute("INSERT INTO positions VALUES (NULL, ?, ?, ?, ?, ?, '0')",
                                     (market, side, str(q), str(price), str(fee)))
            identifier = cursor.lastrowid
            self.db.execute("INSERT INTO fills VALUES (NULL, ?, 'entry', ?, ?, ?, '0')",
                            (identifier, str(q), str(price), str(fee)))
        return identifier

    def exit(self, *, position_id, quantity, bid, exit_fee) -> Decimal:
        q, price, fee = self._validate(quantity, bid, exit_fee)
        # BEGIN IMMEDIATE locks before the read so concurrent exits cannot oversell.
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT remaining, unit_cost, unallocated_entry_fee, realized FROM positions WHERE id = ?",
                                  (position_id,)).fetchone()
            if row is None:
                raise Rejected("unknown paper position")
            remaining, cost, entry_fee, realized = map(Decimal, row)
            if q > remaining:
                raise Rejected("exit exceeds remaining quantity")
            allocated_fee = entry_fee * q / remaining
            profit = q * (price - cost) - allocated_fee - fee
            self.db.execute("UPDATE positions SET remaining = ?, unallocated_entry_fee = ?, realized = ? WHERE id = ?",
                            (str(remaining - q), str(entry_fee - allocated_fee), str(realized + profit), position_id))
            self.db.execute("INSERT INTO fills VALUES (NULL, ?, 'exit', ?, ?, ?, ?)",
                            (position_id, str(q), str(price), str(fee), str(profit)))
            self.db.commit()
            return profit
        except BaseException:
            self.db.rollback()
            raise

    def position(self, position_id) -> dict:
        row = self.db.execute("SELECT market, side, remaining, unit_cost, unallocated_entry_fee, realized FROM positions WHERE id = ?",
                              (position_id,)).fetchone()
        if row is None:
            raise Rejected("unknown paper position")
        return dict(zip(("market", "side", "remaining", "unit_cost", "unallocated_entry_fee", "realized_pnl"), row))
