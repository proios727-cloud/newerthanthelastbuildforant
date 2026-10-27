"""Quant-seat bridge: walk-forward each universe symbol's CSV and emit the desk's signal_list.

Output is research for the Fundamental Analyst and Risk Officer. Nothing here builds a preview,
touches the ledger, or places an order; a candidate still goes analyst → risk → trader → EXECUTE.
"""
import pathlib

from . import load_csv
from .sweep import walk_forward


def symbol_for(path, universe):
    """chart/data/SPY.csv → SPY; chart/data/BTC-USD.csv → BTC/USD. None when it isn't in the pinned universe."""
    stem = pathlib.Path(path).stem.upper()
    for cand in (stem, stem.replace("-", "/"), stem.replace("_", "/")):
        if cand in universe:
            return cand
    return None


def entry(symbol, bars, strategy, train_frac=0.7, **kw):
    wf = walk_forward(bars, strategy, train_frac=train_frac, **kw)
    sig = [s for s in wf.pop("signals") if s is not None]
    latest = sig[-1] if sig else 0
    flipped = len(sig) > 1 and sig[-1] != sig[-2]
    test = wf["test"]
    reasons = []
    if latest != 1:
        reasons.append("signal is flat")
    if test["sharpe"] <= 0:
        reasons.append("out-of-sample Sharpe ≤ 0")
    if wf["edge_vs_hold"] <= 0:
        reasons.append("did not beat buy-and-hold out of sample")
    if test["n_trades"] < 2:
        reasons.append("fewer than 2 out-of-sample trades")
    return {
        "symbol": symbol,
        "strategy": strategy,
        "params": wf["params"],
        "as_of": bars[-1].ts,
        "close": bars[-1].close,
        "signal": "long" if latest == 1 else "flat",
        "flipped_today": flipped,
        "oos": {k: round(test[k], 4) for k in ("total_return", "max_drawdown", "sharpe", "n_trades", "win_rate")},
        "oos_window": [test["from"], test["to"], test["bars"]],
        "buy_hold_oos_return": round(wf["buy_hold_test"]["total_return"], 4),
        "edge_vs_hold": round(wf["edge_vs_hold"], 4),
        "candidate": not reasons,
        "why_not": reasons,
    }


def scan(paths, universe, strategies=("sma_cross", "rsi_revert"), **kw):
    out, skipped = [], []
    for p in sorted(paths):
        sym = symbol_for(p, universe)
        if sym is None:
            skipped.append({"file": str(p), "reason": "not in desk.json universe"})
            continue
        bars = load_csv(p)
        for s in strategies:
            try:
                out.append(entry(sym, bars, s, **kw))
            except ValueError as e:
                skipped.append({"file": str(p), "strategy": s, "reason": str(e)})
    out.sort(key=lambda e: (not e["candidate"], -e["oos"]["sharpe"]))
    return {"signal_list": out, "skipped": skipped,
            "note": "Research only. Candidates still need a thesis, a Risk Officer PASS and EXECUTE."}
