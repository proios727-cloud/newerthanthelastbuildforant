"""Parameter sweep and walk-forward: pick parameters on past bars, score them only on later bars.

`walk_forward` makes one train/test split. `rolling_walk_forward` repeats it: for each test block it
re-picks parameters on everything before the block, then stitches every block's out-of-sample signals
into one continuous backtest, so a single lucky split can't carry the verdict.
"""
from itertools import product

from .backtest import STRATEGIES, backtest
from .strategies import BAR_STRATEGIES, CLOSE_STRATEGIES

ALL = {**STRATEGIES, **CLOSE_STRATEGIES, **BAR_STRATEGIES}

GRIDS = {
    "sma_cross": {"fast": (3, 5, 8, 10), "slow": (15, 20, 30)},
    "rsi_revert": {"n": (7, 14), "lo": (25, 30, 35), "hi": (60, 70)},
    "rsi_dip_trend": {"n": (3, 7), "lo": (20, 30), "hi": (55, 65), "trend": (20, 30)},
    "macd_trend": {"fast": (8, 12), "slow": (17, 26), "signal": (9,), "trend": (20, 30)},
    "bollinger_revert": {"n": (10, 20), "k": (1.5, 2.0)},
    "donchian_breakout": {"n": (10, 20), "exit_n": (5, 10)},
}

def _valid(strategy, p):
    if strategy in ("sma_cross", "macd_trend"):
        return p["fast"] < p["slow"]
    if strategy in ("rsi_revert", "rsi_dip_trend"):
        return p["lo"] < p["hi"]
    if strategy == "donchian_breakout":
        return p["exit_n"] <= p["n"]
    return True


def combos(strategy, grid=None):
    grid = grid or GRIDS[strategy]
    keys = list(grid)
    for vals in product(*(grid[k] for k in keys)):
        p = dict(zip(keys, vals))
        if _valid(strategy, p):
            yield p


def signals(strategy, bars, params):
    fn = ALL[strategy]
    return fn(bars, **params) if strategy in BAR_STRATEGIES else fn([b.close for b in bars], **params)


def buy_and_hold(bars, **kw):
    sig = [1] + [None] * (len(bars) - 1)
    return backtest(bars, sig, **kw)


def _score(bars, strategy, params, lo, hi, **kw):
    """Signals from bars[:hi] (indicators warm up on all history), scored only on bars[lo:hi]."""
    sig = signals(strategy, bars[:hi], params)
    return backtest(bars[lo:hi], sig[lo:hi], **kw).stats


def sweep(bars, strategy, grid=None, lo=0, hi=None, **kw):
    """Every combo scored on bars[lo:hi], best Sharpe first. Ties break on total return."""
    hi = len(bars) if hi is None else hi
    rows = [(p, _score(bars, strategy, p, lo, hi, **kw)) for p in combos(strategy, grid)]
    rows.sort(key=lambda r: (r[1]["sharpe"], r[1]["total_return"]), reverse=True)
    return rows


def walk_forward(bars, strategy, grid=None, train_frac=0.7, min_test=10, **kw):
    """Choose params on bars[:cut]; report them on bars[cut:] next to buy-and-hold on the same slice.

    Signals are computed on the full series because every indicator is causal: the value at bar i
    uses bars <= i only, so test-slice signals never see test-slice futures beyond their own bar.
    """
    cut = int(len(bars) * train_frac)
    if cut < 2 or len(bars) - cut < min_test:
        raise ValueError(f"need at least {min_test} test bars; have {len(bars) - cut} of {len(bars)}")
    train, test = bars[:cut], bars[cut:]
    ranked = sweep(bars, strategy, grid, 0, cut, **kw)
    best, train_stats = ranked[0]
    sig = signals(strategy, bars, best)
    oos = backtest(test, sig[cut:], **kw)
    bh = buy_and_hold(test, **kw)
    return {
        "strategy": strategy,
        "params": best,
        "train": {"bars": len(train), "from": train[0].ts, "to": train[-1].ts, **train_stats},
        "test": {"bars": len(test), "from": test[0].ts, "to": test[-1].ts, **oos.stats},
        "buy_hold_test": bh.stats,
        "edge_vs_hold": oos.stats["total_return"] - bh.stats["total_return"],
        "combos_tried": len(ranked),
        "latest_signal": next((s for s in reversed(sig) if s is not None), None),
        "signals": sig,
    }


def rolling_walk_forward(bars, strategy, grid=None, min_train=40, test=10, anchored=True, **kw):
    """Re-pick params before every `test`-bar block, then backtest the stitched out-of-sample signals.

    anchored=True trains on bars[0:t]; anchored=False trains on the last `min_train` bars only.
    Positions carry across block boundaries, as they would live.
    """
    if len(bars) < min_train + test:
        raise ValueError(f"need at least {min_train + test} bars; have {len(bars)}")
    first = min_train
    stitched = [None] * len(bars)
    windows = []
    for t0 in range(first, len(bars), test):
        t1 = min(t0 + test, len(bars))
        lo = 0 if anchored else t0 - min_train
        best, train_stats = sweep(bars, strategy, grid, lo, t0, **kw)[0]
        sig = signals(strategy, bars[:t1], best)
        stitched[t0:t1] = sig[t0:t1]
        windows.append({"from": bars[t0].ts, "to": bars[t1 - 1].ts, "params": best,
                        "train_sharpe": train_stats["sharpe"], "_span": (t0, t1)})

    oos_bars = bars[first:]
    # Seed the first block with the position the chosen params already held, so block 1 isn't forced flat.
    seed = next((s for s in reversed(signals(strategy, bars[:first], windows[0]["params"])) if s is not None), None)
    oos_sig = stitched[first:]
    if oos_sig[0] is None and seed is not None:
        oos_sig[0] = seed
    res = backtest(oos_bars, oos_sig, **kw)
    bh = buy_and_hold(oos_bars, **kw)
    beat = 0
    for w in windows:
        t0, t1 = w.pop("_span")
        a, b = t0 - first, t1 - first - 1
        prev = res.equity[a - 1] if a > 0 else res.equity[0]
        hprev = bh.equity[a - 1] if a > 0 else bh.equity[0]
        w["return"] = res.equity[b] / prev - 1
        w["hold_return"] = bh.equity[b] / hprev - 1
        beat += w["return"] > w["hold_return"]
    distinct = {tuple(sorted(w["params"].items())) for w in windows}
    latest = next((s for s in reversed(stitched) if s is not None), seed)
    return {
        "strategy": strategy,
        "mode": "anchored" if anchored else "rolling",
        "oos": {"bars": len(oos_bars), "from": oos_bars[0].ts, "to": oos_bars[-1].ts, **res.stats},
        "buy_hold_oos": bh.stats,
        "edge_vs_hold": res.stats["total_return"] - bh.stats["total_return"],
        "windows": windows,
        "windows_beat_hold": beat,
        "param_sets_used": len(distinct),
        "latest_signal": latest,
        "latest_params": windows[-1]["params"],
        "curve": {"dates": [b.ts for b in oos_bars], "strategy": res.equity, "hold": bh.equity},
    }
