"""Basket momentum rotation: hold the one symbol with the strongest trailing return, or cash if none is up.

Decided at bar i's close from closes <= i; switches fill at bar i+1's open with fees and slippage,
the same execution rule as `backtest`. Benchmark: an equal-weight buy-and-hold of the same basket.
"""
from itertools import product

from .backtest import Result, _stats

GRID = {"lookback": (5, 10, 20), "hold": (1, 5)}


def align(bars_by_symbol):
    """Keep only dates every symbol has; returns (symbols, dates, {symbol: [Bar]})."""
    syms = sorted(bars_by_symbol)
    common = set.intersection(*({b.ts for b in bars_by_symbol[s]} for s in syms))
    dates = sorted(common)
    idx = {s: {b.ts: b for b in bars_by_symbol[s]} for s in syms}
    return syms, dates, {s: [idx[s][d] for d in dates] for s in syms}


def picks(aligned, lookback=10, hold=1):
    """Target per bar: a symbol, "CASH", or None (keep). Re-decides every `hold` bars after warm-up."""
    syms, dates, bars = aligned
    out = [None] * len(dates)
    for i in range(lookback, len(dates)):
        if (i - lookback) % hold:
            continue
        mom = {s: bars[s][i].close / bars[s][i - lookback].close - 1 for s in syms}
        best = max(syms, key=lambda s: (mom[s], s))
        out[i] = best if mom[best] > 0 else "CASH"
    return out


def run(aligned, targets, lo=0, hi=None, fee_bps=0.0, slippage_bps=0.0, start_cash=100_000.0,
        periods_per_year=252, start_in=None):
    syms, dates, bars = aligned
    hi = len(dates) if hi is None else hi
    fee, slip = fee_bps / 1e4, slippage_bps / 1e4
    cash, held, units, entry = float(start_cash), None, 0.0, None
    equity, trades, exposed = [], [], 0
    pending = start_in
    for i in range(lo, hi):
        if pending is not None and pending != (held or "CASH"):
            if held:
                px = bars[held][i].open * (1 - slip)
                cash += units * px * (1 - fee)
                trades.append((entry[0], dates[i], held, entry[1], px, cash - entry[2]))
                held, units = None, 0.0
            if pending != "CASH":
                px = bars[pending][i].open * (1 + slip)
                basis = cash
                units = cash / (px * (1 + fee))
                cash = 0.0
                held, entry = pending, (dates[i], px, basis)
        pending = None
        equity.append(cash + (units * bars[held][i].close if held else 0.0))
        exposed += held is not None
        t = targets[i]
        if t is not None and i < hi - 1:
            pending = t
    if held:
        trades.append((entry[0], None, held, entry[1], bars[held][hi - 1].close, equity[-1] - entry[2]))
    return Result(equity, trades, _stats(equity, trades, exposed, start_cash, periods_per_year))


def equal_weight_hold(aligned, lo=0, hi=None, fee_bps=0.0, slippage_bps=0.0, start_cash=100_000.0,
                      periods_per_year=252):
    """Buy 1/N of each symbol at bar lo+1's open, hold to the end."""
    syms, dates, bars = aligned
    hi = len(dates) if hi is None else hi
    fee, slip = fee_bps / 1e4, slippage_bps / 1e4
    units = {s: (start_cash / len(syms)) / (bars[s][lo + 1].open * (1 + slip) * (1 + fee)) for s in syms}
    equity = [start_cash] + [sum(units[s] * bars[s][i].close for s in syms) for i in range(lo + 1, hi)]
    return Result(equity, [], _stats(equity, [], len(equity) - 1, start_cash, periods_per_year))


def combos(grid=None):
    grid = grid or GRID
    keys = list(grid)
    for vals in product(*(grid[k] for k in keys)):
        yield dict(zip(keys, vals))


def rolling(aligned, grid=None, min_train=40, test=10, **kw):
    """Same protocol as sweep.rolling_walk_forward, on the basket."""
    syms, dates, _ = aligned
    if len(dates) < min_train + test:
        raise ValueError(f"need at least {min_train + test} aligned bars; have {len(dates)}")
    stitched, windows = [None] * len(dates), []
    for t0 in range(min_train, len(dates), test):
        t1 = min(t0 + test, len(dates))
        scored = [(p, run(aligned, picks(aligned, **p), 0, t0, **kw).stats) for p in combos(grid)]
        scored.sort(key=lambda r: (r[1]["sharpe"], r[1]["total_return"]), reverse=True)
        best = scored[0][0]
        stitched[t0:t1] = picks(aligned, **best)[t0:t1]
        windows.append({"from": dates[t0], "to": dates[t1 - 1], "params": best, "_span": (t0, t1)})
    seed = next((t for t in reversed(picks(aligned, **windows[0]["params"])[:min_train]) if t), None)
    res = run(aligned, stitched, min_train, None, start_in=seed, **kw)
    bh = equal_weight_hold(aligned, min_train, None, **kw)
    beat = 0
    for w in windows:
        t0, t1 = w.pop("_span")
        a, b = t0 - min_train, t1 - min_train - 1
        w["return"] = res.equity[b] / (res.equity[a - 1] if a else res.equity[0]) - 1
        w["hold_return"] = bh.equity[b] / (bh.equity[a - 1] if a else bh.equity[0]) - 1
        beat += w["return"] > w["hold_return"]
    latest = next((t for t in reversed(stitched) if t), seed)
    return {
        "strategy": "momentum_rotation",
        "basket": syms,
        "oos": {"bars": len(res.equity), "from": dates[min_train], "to": dates[-1], **res.stats},
        "equal_weight_hold_oos": bh.stats,
        "edge_vs_hold": res.stats["total_return"] - bh.stats["total_return"],
        "windows": windows,
        "windows_beat_hold": beat,
        "param_sets_used": len({tuple(sorted(w["params"].items())) for w in windows}),
        "latest_target": latest,
        "trades": res.trades,
    }
