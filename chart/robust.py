"""Stress tests for the basket rotation: does its edge survive higher costs, other rebalance days, holding more than
one fund, other parameters, and a smaller universe? An edge that lives in one exact setup is curve fitting.

`run_multi` generalises `rotate.run` to an equal-weight set of holdings; with top=1 it reproduces `rotate.run`.
"""
from itertools import product

from . import rotate
from .backtest import Result, _stats


def basket_index(aligned):
    """Equal-weight basket level per bar (each fund rebased to 1 on the first aligned bar)."""
    syms, dates, bars = aligned
    return [sum(bars[s][i].close / bars[s][0].close for s in syms) / len(syms) for i in range(len(dates))]


def picks_top(aligned, lookback=10, hold=1, top=1, offset=0, buffer=0, trend=0):
    """Target per bar: a tuple of the `top` strongest symbols with positive momentum (empty = cash), or None (keep).
    Decides every `hold` bars after warm-up, starting `offset` bars later than rotate.picks would.

    buffer > 0 adds hysteresis: a fund already held stays while it still ranks inside the top `top + buffer` with
    positive momentum, and only the freed slots go to the strongest funds not held. buffer=0 is plain top-N.
    trend > 0 adds a basket trend filter: on a decision bar where the equal-weight basket closes below its
    `trend`-bar average, the target is cash. Bars before the average exists are not filtered."""
    syms, dates, bars = aligned
    out = [None] * len(dates)
    idx = basket_index(aligned) if trend else None
    prev = ()
    for i in range(lookback + offset, len(dates)):
        if (i - lookback - offset) % hold:
            continue
        if trend and i >= trend - 1 and idx[i] < sum(idx[i - trend + 1:i + 1]) / trend:
            out[i] = prev = ()
            continue
        mom = {s: bars[s][i].close / bars[s][i - lookback].close - 1 for s in syms}
        ranked = sorted(syms, key=lambda s: (mom[s], s), reverse=True)
        keep = [s for s in prev if s in ranked[:top + buffer] and mom[s] > 0]
        fill = [s for s in ranked if s not in keep and mom[s] > 0][:top - len(keep)]
        out[i] = prev = tuple(sorted(keep + fill))
    return out


def run_multi(aligned, targets, lo=0, hi=None, fee_bps=0.0, slippage_bps=0.0, start_cash=100_000.0,
              periods_per_year=252, start_in=None, trade_changes_only=False):
    """When the target set changes, sell everything at the next open and buy the new set in equal weights.
    trade_changes_only=True sells only the names leaving and buys the names joining with the proceeds (split
    equally), leaving the rest untouched, as a real desk would; with one holding the two modes are identical."""
    syms, dates, bars = aligned
    hi = len(dates) if hi is None else hi
    fee, slip = fee_bps / 1e4, slippage_bps / 1e4
    cash, held, units, entries = float(start_cash), (), {}, {}
    equity, trades, exposed = [], [], 0
    pending = start_in
    for i in range(lo, hi):
        if pending is not None and trade_changes_only and held and pending and tuple(pending) != held:
            leaving = [s for s in held if s not in pending]
            joining = [s for s in pending if s not in held]
            for s in leaving:
                px = bars[s][i].open * (1 - slip)
                proceeds = units.pop(s) * px * (1 - fee)
                cash += proceeds
                trades.append((entries[s][0], dates[i], s, entries[s][1], px, proceeds - entries.pop(s)[2]))
            each = cash / len(joining) if joining else 0.0
            for s in joining:
                px = bars[s][i].open * (1 + slip)
                units[s] = each / (px * (1 + fee))
                entries[s] = (dates[i], px, each)
            if joining:
                cash = 0.0
            held = tuple(sorted(units))
        elif pending is not None and tuple(pending) != held:
            for s in held:
                px = bars[s][i].open * (1 - slip)
                proceeds = units[s] * px * (1 - fee)
                cash += proceeds
                trades.append((entries[s][0], dates[i], s, entries[s][1], px, proceeds - entries[s][2]))
            held, units, entries = (), {}, {}
            if pending:
                each = cash / len(pending)
                for s in pending:
                    px = bars[s][i].open * (1 + slip)
                    units[s] = each / (px * (1 + fee))
                    entries[s] = (dates[i], px, each)
                cash, held = 0.0, tuple(pending)
        pending = None
        equity.append(cash + sum(units[s] * bars[s][i].close for s in held))
        exposed += bool(held)
        t = targets[i]
        if t is not None and i < hi - 1:
            pending = t
    for s in held:
        trades.append((entries[s][0], None, s, entries[s][1], bars[s][hi - 1].close,
                       units[s] * bars[s][hi - 1].close - entries[s][2]))
    return Result(equity, trades, _stats(equity, trades, exposed, start_cash, periods_per_year))


def rolling_multi(aligned, grid=None, min_train=252, test=21, top=1, offset=0, **kw):
    """rotate.rolling's protocol (re-pick on all earlier bars before each block, stitch, score) for top-N holdings."""
    grid = grid or rotate.GRID
    _, dates, _ = aligned
    combos = [dict(zip(grid, v)) for v in product(*grid.values())]
    stitched, chosen = [None] * len(dates), []
    for t0 in range(min_train, len(dates), test):
        t1 = min(t0 + test, len(dates))
        scored = [(p, run_multi(aligned, picks_top(aligned, top=top, offset=offset, **p), 0, t0, **kw).stats)
                  for p in combos]
        best = max(scored, key=lambda r: (r[1]["sharpe"], r[1]["total_return"]))[0]
        stitched[t0:t1] = picks_top(aligned, top=top, offset=offset, **best)[t0:t1]
        chosen.append(best)
    first = picks_top(aligned, top=top, offset=offset, **chosen[0])[:min_train]
    seed = next((t for t in reversed(first) if t is not None), None)
    res = run_multi(aligned, stitched, min_train, None, start_in=seed, **kw)
    bh = rotate.equal_weight_hold(aligned, min_train, None, **kw)
    beat, n = 0, 0
    for k, t0 in enumerate(range(min_train, len(dates), test)):
        a, b = t0 - min_train, min(t0 + test, len(dates)) - min_train - 1
        r = res.equity[b] / (res.equity[a - 1] if a else res.equity[0])
        h = bh.equity[b] / (bh.equity[a - 1] if a else bh.equity[0])
        beat, n = beat + (r > h), n + 1
    return {"oos": res.stats, "hold": bh.stats, "beat": beat, "blocks": n,
            "param_sets": len({tuple(sorted(p.items())) for p in chosen}), "trades": res.trades}


def fixed(aligned, params, min_train=252, top=1, **kw):
    """One parameter set held fixed over the whole out-of-sample span (no re-picking): a parameter-sensitivity probe."""
    res = run_multi(aligned, picks_top(aligned, top=top, **params), min_train, None, **kw)
    return res.stats


def day_sweep(aligned, lookback=60, hold=21, top=3, min_train=252, buffer=0, trend=0, **kw):
    """Run a fixed rule from every possible rebalance day (offset 0..hold-1); summarise the spread, not the best day."""
    hold_stats = rotate.equal_weight_hold(aligned, min_train, None,
                                          **{k: v for k, v in kw.items() if k in ("fee_bps", "slippage_bps")}).stats
    runs = []
    for off in range(hold):
        t = picks_top(aligned, lookback=lookback, hold=hold, top=top, offset=off, buffer=buffer, trend=trend)
        runs.append(run_multi(aligned, t, min_train, None, trade_changes_only=True, **kw).stats)
    med = lambda k: sorted(r[k] for r in runs)[len(runs) // 2]
    return {
        "rule": {"lookback": lookback, "hold": hold, "top": top, "buffer": buffer, "trend": trend},
        "days": len(runs),
        "cagr": {"min": min(r["cagr"] for r in runs), "median": med("cagr"), "max": max(r["cagr"] for r in runs)},
        "max_drawdown": {"worst": min(r["max_drawdown"] for r in runs), "median": med("max_drawdown")},
        "sharpe_median": med("sharpe"),
        "trades_median": med("n_trades"),
        "days_calmar_at_least_hold": sum(r["calmar"] >= hold_stats["calmar"] for r in runs),
        "hold": {k: hold_stats[k] for k in ("cagr", "max_drawdown", "sharpe", "calmar")},
    }


def stress(bars_by_symbol, rule=None, drops=("GLD", "TLT", "XLK"), costs=((1, 2), (10, 10), (25, 25))):
    """The full battery for one rule: every rebalance day, at several cost levels, and with key funds removed."""
    rule = rule or {"lookback": 60, "hold": 21, "top": 3}
    out = {"rule": rule, "costs": [], "without": []}
    full = rotate.align(bars_by_symbol)
    for f, s in costs:
        out["costs"].append({"fee_bps": f, "slippage_bps": s, **day_sweep(full, fee_bps=f, slippage_bps=s, **rule)})
    for d in drops:
        if d in bars_by_symbol:
            sub = rotate.align({k: v for k, v in bars_by_symbol.items() if k != d})
            out["without"].append({"dropped": d, **day_sweep(sub, fee_bps=1, slippage_bps=2, **rule)})
    return out
