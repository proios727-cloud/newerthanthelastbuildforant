"""Quant-seat bridge: rolling walk-forward of each universe symbol's CSV, plus a basket rotation,
emitted as the desk's signal_list.

Output is research for the Fundamental Analyst and Risk Officer. Nothing here builds a preview,
touches the ledger, or places an order; a candidate still goes analyst → risk → trader → EXECUTE.
"""
import pathlib

from . import load_csv
from . import rotate
from .sweep import GRIDS, rolling_walk_forward


def symbol_for(path, universe):
    """chart/data/SPY.csv → SPY; chart/data/BTC-USD.csv → BTC/USD. None when it isn't in the pinned universe."""
    stem = pathlib.Path(path).stem.upper()
    for cand in (stem, stem.replace("-", "/"), stem.replace("_", "/")):
        if cand in universe:
            return cand
    return None


MIN_TRADES = 3


def _verdict(latest_long, oos, edge, beat, n_windows, hold):
    reasons = []
    if not latest_long:
        reasons.append("signal is flat")
    if oos["sharpe"] <= 0:
        reasons.append("out-of-sample Sharpe ≤ 0")
    if edge <= 0:
        reasons.append("did not beat buy-and-hold out of sample")
    if oos["sharpe"] < hold["sharpe"]:
        reasons.append(f"risk-adjusted worse than buy-and-hold (Sharpe {oos['sharpe']:.2f} vs {hold['sharpe']:.2f})")
    if beat * 2 < n_windows:
        reasons.append(f"beat buy-and-hold in only {beat} of {n_windows} test blocks")
    if oos["n_trades"] < MIN_TRADES:
        reasons.append(f"fewer than {MIN_TRADES} out-of-sample trades")
    return reasons


DD_CUT = 1 / 3        # a risk filter must take at least a third off buy-and-hold's worst drawdown
MIN_EXPOSURE = 0.3    # ...while still being invested at least 30% of the time


def _risk_verdict(oos, hold):
    """Does the strategy work as a risk filter on top of holding: shallower drawdown, no worse return per unit of it?"""
    reasons = []
    if hold["max_drawdown"] >= 0 or oos["max_drawdown"] < hold["max_drawdown"] * (1 - DD_CUT):
        reasons.append(f"drawdown {oos['max_drawdown']:.1%} not at least a third shallower than hold's "
                       f"{hold['max_drawdown']:.1%}")
    if oos["calmar"] < hold["calmar"]:
        reasons.append(f"return per unit of drawdown below hold's (Calmar {oos['calmar']:.2f} vs {hold['calmar']:.2f})")
    if oos["exposure"] < MIN_EXPOSURE:
        reasons.append(f"invested only {oos['exposure']:.0%} of the time")
    if oos["sharpe"] <= 0:
        reasons.append("out-of-sample Sharpe ≤ 0")
    if oos["n_trades"] < MIN_TRADES:
        reasons.append(f"fewer than {MIN_TRADES} out-of-sample trades")
    return reasons


def _oos(stats):
    return {k: round(stats[k], 4) for k in ("total_return", "cagr", "max_drawdown", "calmar", "sharpe",
                                             "n_trades", "win_rate", "exposure")}


def _hold(stats):
    return {k: round(stats[k], 4) for k in ("total_return", "cagr", "max_drawdown", "calmar", "sharpe")}


def entry(symbol, bars, strategy, min_train=40, test=10, **kw):
    wf = rolling_walk_forward(bars, strategy, min_train=min_train, test=test, **kw)
    oos, n = wf["oos"], len(wf["windows"])
    reasons = _verdict(wf["latest_signal"] == 1, oos, wf["edge_vs_hold"], wf["windows_beat_hold"], n,
                       wf["buy_hold_oos"])
    return {
        "symbol": symbol,
        "strategy": strategy,
        "params": wf["latest_params"],
        "param_sets_used": wf["param_sets_used"],
        "as_of": bars[-1].ts,
        "close": bars[-1].close,
        "signal": "long" if wf["latest_signal"] == 1 else "flat",
        "oos": _oos(oos),
        "oos_window": [oos["from"], oos["to"], oos["bars"]],
        "test_blocks_beat_hold": f"{wf['windows_beat_hold']}/{n}",
        "hold": _hold(wf["buy_hold_oos"]),
        "edge_vs_hold": round(wf["edge_vs_hold"], 4),
        "candidate": not reasons,
        "why_not": reasons,
        "risk_filter": not (risk := _risk_verdict(oos, wf["buy_hold_oos"])),
        "risk_why_not": risk,
    }


def basket_entry(bars_by_symbol, min_train=40, test=10, **kw):
    al = rotate.align(bars_by_symbol)
    r = rotate.rolling(al, min_train=min_train, test=test, **kw)
    oos = r["oos"]
    n = len(r["windows"])
    reasons = _verdict(r["latest_target"] not in (None, "CASH"), oos, r["edge_vs_hold"], r["windows_beat_hold"], n,
                       r["equal_weight_hold_oos"])
    return {
        "symbol": "+".join(r["basket"]),
        "strategy": "momentum_rotation",
        "params": r["windows"][-1]["params"],
        "param_sets_used": r["param_sets_used"],
        "as_of": oos["to"],
        "signal": f"hold {r['latest_target']}",
        "oos": _oos(oos),
        "oos_window": [oos["from"], oos["to"], oos["bars"]],
        "test_blocks_beat_hold": f"{r['windows_beat_hold']}/{n}",
        "hold": _hold(r["equal_weight_hold_oos"]),
        "edge_vs_hold": round(r["edge_vs_hold"], 4),
        "candidate": not reasons,
        "why_not": reasons,
        "risk_filter": not (risk := _risk_verdict(oos, r["equal_weight_hold_oos"])),
        "risk_why_not": risk,
    }


def scan(paths, universe, strategies=tuple(GRIDS), basket=True, **kw):
    out, skipped, loaded = [], [], {}
    for p in sorted(paths):
        sym = symbol_for(p, universe)
        if sym is None:
            skipped.append({"file": str(p), "reason": "not in desk.json universe"})
            continue
        bars = load_csv(p)
        loaded[sym] = bars
        for s in strategies:
            try:
                out.append(entry(sym, bars, s, **kw))
            except ValueError as e:
                skipped.append({"file": str(p), "strategy": s, "reason": str(e)})
    if basket and len(loaded) >= 2:
        try:
            out.append(basket_entry(loaded, **kw))
        except ValueError as e:
            skipped.append({"basket": sorted(loaded), "reason": str(e)})
    out.sort(key=lambda e: (not e["candidate"], -e["oos"]["sharpe"]))
    return {"signal_list": out, "skipped": skipped,
            "candidates": sum(e["candidate"] for e in out),
            "risk_filters": sum(e["risk_filter"] for e in out),
            "note": "Research only. Candidates still need a thesis, a Risk Officer PASS and EXECUTE."}
