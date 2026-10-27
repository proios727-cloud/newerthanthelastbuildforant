"""Parameter sweep and walk-forward: pick parameters on the train slice, score them only on the test slice."""
from itertools import product

from .backtest import STRATEGIES, backtest

GRIDS = {
    "sma_cross": {"fast": (3, 5, 8, 10), "slow": (15, 20, 30)},
    "rsi_revert": {"n": (7, 14), "lo": (25, 30, 35), "hi": (60, 70)},
}


def combos(strategy, grid=None):
    grid = grid or GRIDS[strategy]
    keys = list(grid)
    for vals in product(*(grid[k] for k in keys)):
        p = dict(zip(keys, vals))
        if strategy == "sma_cross" and p["fast"] >= p["slow"]:
            continue
        if strategy == "rsi_revert" and p["lo"] >= p["hi"]:
            continue
        yield p


def signals(strategy, close, params):
    return STRATEGIES[strategy](close, **params)


def buy_and_hold(bars, **kw):
    sig = [1] + [None] * (len(bars) - 1)
    return backtest(bars, sig, **kw)


def sweep(bars, strategy, grid=None, **kw):
    """Every combo on `bars`, best Sharpe first. Ties break on total return."""
    close = [b.close for b in bars]
    rows = [(p, backtest(bars, signals(strategy, close, p), **kw).stats) for p in combos(strategy, grid)]
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
    ranked = sweep(train, strategy, grid, **kw)
    best, train_stats = ranked[0]
    close = [b.close for b in bars]
    sig = signals(strategy, close, best)
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
