"""Bar backtester. A signal decided at bar i's close fills at bar i+1's open — no lookahead."""
import math
from dataclasses import dataclass, field

from . import indicators as ind


@dataclass
class Result:
    equity: list
    trades: list = field(default_factory=list)   # (entry_ts, exit_ts, side, entry_px, exit_px, pnl)
    stats: dict = field(default_factory=dict)


def backtest(bars, signals, fee_bps=0.0, slippage_bps=0.0, allow_short=False,
             start_cash=100_000.0, periods_per_year=252):
    if len(signals) != len(bars):
        raise ValueError("signals must be the same length as bars")
    fee, slip = fee_bps / 1e4, slippage_bps / 1e4
    cash, units, side = float(start_cash), 0.0, 0
    entry = None                     # (ts, px, cost basis incl. entry fee)
    equity, trades, held = [], [], 0
    pending = None

    for i, b in enumerate(bars):
        if pending is not None and pending != side:
            if side != 0:            # close the current position at this open
                px = b.open * (1 - slip) if side > 0 else b.open * (1 + slip)
                notional = abs(units) * px
                cash += units * px - notional * fee
                trades.append((entry[0], b.ts, side, entry[1], px, cash - entry[2]))
                units, side = 0.0, 0
            if pending != 0:         # open the new one with all equity
                px = b.open * (1 + slip) if pending > 0 else b.open * (1 - slip)
                basis = cash
                qty = cash / (px * (1 + fee))
                cash -= qty * px * fee
                units = qty * pending
                cash -= units * px
                side, entry = pending, (b.ts, px, basis)
        pending = None

        equity.append(cash + units * b.close)
        held += side != 0
        s = signals[i]
        if s is not None and i < len(bars) - 1:
            s = max(min(int(s), 1), -1)
            pending = s if (s >= 0 or allow_short) else 0

    if side != 0:
        trades.append((entry[0], None, side, entry[1], bars[-1].close, equity[-1] - entry[2]))
    return Result(equity, trades, _stats(equity, trades, held, start_cash, periods_per_year))


def _stats(equity, trades, held, start_cash, ppy):
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1]]
    sharpe = 0.0
    if len(rets) > 1:
        mu = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
        sharpe = mu / sd * math.sqrt(ppy) if sd > 1e-12 else 0.0
    peak, mdd = -math.inf, 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    wins = sum(1 for t in trades if t[5] > 0)
    total = equity[-1] / start_cash - 1 if equity else 0.0
    years = len(equity) / ppy if equity else 0.0
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else -1.0
    calmar = cagr / -mdd if mdd < 0 else 0.0
    return {
        "total_return": total,
        "cagr": cagr,
        "max_drawdown": mdd,
        "calmar": calmar,
        "sharpe": sharpe,
        "n_trades": len(trades),
        "win_rate": wins / len(trades) if trades else 0.0,
        "exposure": held / len(equity) if equity else 0.0,
    }


def sma_cross(close, fast=10, slow=30):
    f, s = ind.sma(close, fast), ind.sma(close, slow)
    return [None if a is None or b is None else (1 if a > b else 0) for a, b in zip(f, s)]


def rsi_revert(close, n=14, lo=30, hi=70):
    out = []
    for v in ind.rsi(close, n):
        out.append(None if v is None else 1 if v < lo else 0 if v > hi else None)
    return out


STRATEGIES = {"sma_cross": sma_cross, "rsi_revert": rsi_revert}
