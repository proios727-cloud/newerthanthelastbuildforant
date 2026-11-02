"""Trend breakout with a stop: research/crypto-breakout/RULE.md (amendment). Long or flat, 100% of equity, no leverage.

- Entry signal at bar i's close: close > highest high of bars i-20..i-1 and close > EMA(200)[i]. It fills at bar i+1's open.
- Exit signal at bar i's close: close < lowest low of bars i-10..i-1 (prior bars only, so it is reachable). Fills at i+1's open.
- Stop: entry fill - 2 x ATR(14) at the signal bar, fixed for the trade. It is hit when a later bar's low touches it, filling at
  the stop, or at the open if the bar opens below it. On the entry bar itself the open is the entry, so only the low counts.
- Costs: fee_bps and slip_bps per side, slippage adverse on every fill.
"""
import math

from .indicators import atr, ema

BARS_PER_YEAR_4H = 6 * 365
COST_LADDER = (("0", 0.0, 0.0), ("5+5", 5.0, 5.0), ("10+10", 10.0, 10.0), ("25+25", 25.0, 25.0))


def run(bars, entry_n=20, exit_n=10, trend_n=200, atr_n=14, atr_mult=2.0, fee_bps=10.0, slip_bps=10.0):
    """Returns (equity list marked at each close, trades list of dicts)."""
    fee, slip = fee_bps / 1e4, slip_bps / 1e4
    close = [b.close for b in bars]
    trend, vol = ema(close, trend_n), atr(bars, atr_n)
    cash, units = 1.0, 0.0
    pending = None              # ("buy", stop_dist) or ("sell", reason)
    stop = entry = None
    trades, equity = [], []

    def sell(px, ts, reason):
        nonlocal cash, units
        fill = px * (1 - slip)
        cash = units * fill * (1 - fee)
        trades.append(dict(entry_ts=entry[0], exit_ts=ts, entry=entry[1], exit=fill, reason=reason,
                           ret=cash / entry[2] - 1))
        units = 0.0

    for i, b in enumerate(bars):
        if pending is not None:                       # fills at this bar's open
            if pending[0] == "buy" and units == 0:
                fill = b.open * (1 + slip)
                entry = (b.ts, fill, cash)
                units = cash * (1 - fee) / fill
                cash = 0.0
                stop = fill - pending[1]
            elif pending[0] == "sell" and units > 0:
                sell(b.open, b.ts, pending[1])
            pending = None
            entered_now = units > 0 and entry[0] == b.ts
        else:
            entered_now = False
        if units > 0:                                 # stop check inside the bar
            if not entered_now and b.open <= stop:
                sell(b.open, b.ts, "stop")
            elif b.low <= stop:
                sell(stop, b.ts, "stop")
        equity.append(cash + units * b.close)
        if i == len(bars) - 1:
            break
        if units == 0 and i >= entry_n and trend[i] is not None and vol[i] is not None:
            if b.close > max(x.high for x in bars[i - entry_n:i]) and b.close > trend[i]:
                pending = ("buy", atr_mult * vol[i])
        elif units > 0 and i >= exit_n and b.close < min(x.low for x in bars[i - exit_n:i]):
            pending = ("sell", "10-bar low")
    if units > 0:
        trades.append(dict(entry_ts=entry[0], exit_ts=None, entry=entry[1], exit=bars[-1].close, reason="open",
                           ret=equity[-1] / entry[2] - 1))
    return equity, trades


def _mdd(eq):
    peak, mdd = -math.inf, 0.0
    for e in eq:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    return mdd


def _cagr(total, n_bars, ppy):
    years = n_bars / ppy
    return (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else -1.0


def summary(bars, equity, trades, ppy=BARS_PER_YEAR_4H):
    """Strategy vs buy and hold over the same bars, plus per-year and final-third splits."""
    bh = [b.close / bars[0].open for b in bars]
    total, bh_total = equity[-1] - 1, bh[-1] - 1
    mdd, bh_mdd = _mdd(equity), _mdd(bh)
    cagr, bh_cagr = _cagr(total, len(bars), ppy), _cagr(bh_total, len(bars), ppy)
    rets = [t["ret"] for t in trades]
    n = len(rets)
    mean = sum(rets) / n if n else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0

    def span(lo, hi):                                   # equity and buy-hold return over bars[lo:hi]
        start_eq = equity[lo - 1] if lo > 0 else 1.0
        start_px = bars[lo - 1].close if lo > 0 else bars[0].open
        return equity[hi - 1] / start_eq - 1, bars[hi - 1].close / start_px - 1

    years = {}
    for i, b in enumerate(bars):
        y = b.ts[:4]
        years.setdefault(y, [i, i])[1] = i
    by_year = {y: dict(zip(("strategy", "buy_hold"), span(lo, hi + 1))) for y, (lo, hi) in years.items()}
    third = len(bars) * 2 // 3
    hold = span(third, len(bars))
    return {
        "first": bars[0].ts, "last": bars[-1].ts, "bars": len(bars),
        "trades": n, "win_rate": sum(r > 0 for r in rets) / n if n else 0.0,
        "mean_trade": mean, "t_stat": mean / (sd / math.sqrt(n)) if sd > 0 else 0.0,
        "total_return": total, "cagr": cagr, "max_drawdown": mdd, "calmar": cagr / -mdd if mdd < 0 else 0.0,
        "buy_hold": {"total_return": bh_total, "cagr": bh_cagr, "max_drawdown": bh_mdd,
                     "calmar": bh_cagr / -bh_mdd if bh_mdd < 0 else 0.0},
        "exposure": None,
        "holdout_final_third": {"from": bars[third].ts, "strategy": hold[0], "buy_hold": hold[1]},
        "by_year": by_year,
        "exits": {k: sum(1 for t in trades if t["reason"] == k) for k in ("10-bar low", "stop", "open")},
    }


def window_return(bars, equity, start, end):
    """(strategy, buy and hold) return over the bars dated start..end inclusive (YYYY-MM-DD), or None if none are."""
    idx = [i for i, b in enumerate(bars) if start <= b.ts[:10] <= end]
    if not idx:
        return None
    lo, hi = idx[0], idx[-1]
    start_eq = equity[lo - 1] if lo > 0 else 1.0
    start_px = bars[lo - 1].close if lo > 0 else bars[0].open
    return equity[hi] / start_eq - 1, bars[hi].close / start_px - 1


def report(paths, ppy=BARS_PER_YEAR_4H, end=None, windows=(), interval="4h"):
    """Base case, cost ladder and named windows for each CSV path. `end` (YYYY-MM-DD) drops later bars first."""
    import pathlib
    from . import load_csv
    out = {}
    for p in paths:
        bars = load_csv(p)
        if end:
            bars = [b for b in bars if b.ts[:10] <= end]
        eq, tr = run(bars)
        s = summary(bars, eq, tr, ppy)
        idx = {b.ts: i for i, b in enumerate(bars)}
        held = sum((idx[t["exit_ts"]] if t["exit_ts"] else len(bars)) - idx[t["entry_ts"]] for t in tr)
        s["exposure"] = held / len(bars)
        s["interval"] = interval
        s["cost_ladder"] = {lab: summary(bars, *run(bars, fee_bps=f, slip_bps=sl), ppy)["total_return"]
                            for lab, f, sl in COST_LADDER}
        s["windows"] = {}
        for name, a, b in windows:
            r = window_return(bars, eq, a, b)
            if r:
                s["windows"][name] = {"from": a, "to": b, "strategy": r[0], "buy_hold": r[1]}
        out[pathlib.Path(p).stem] = s
    return out


def format_report(rep):
    lines = []
    for sym, s in rep.items():
        bh = s["buy_hold"]
        lines += [f"\n## {sym}: {s['first'][:10]} → {s['last'][:10]}, {s['bars']} bars ({s.get('interval', '4h')})\n",
                  "| | Strategy (10+10 bp) | Buy & hold |", "|---|---|---|",
                  f"| Total return | {s['total_return']:+.1%} | {bh['total_return']:+.1%} |",
                  f"| CAGR | {s['cagr']:+.1%} | {bh['cagr']:+.1%} |",
                  f"| Max drawdown | {s['max_drawdown']:.1%} | {bh['max_drawdown']:.1%} |",
                  f"| CAGR ÷ max DD | {s['calmar']:.2f} | {bh['calmar']:.2f} |",
                  f"| Holdout (from {s['holdout_final_third']['from'][:10]}) | "
                  f"{s['holdout_final_third']['strategy']:+.1%} | {s['holdout_final_third']['buy_hold']:+.1%} |",
                  f"\nTrades {s['trades']} · win {s['win_rate']:.0%} · mean {s['mean_trade']:+.2%} · t {s['t_stat']:+.2f} · "
                  f"time in market {s['exposure']:.0%} · exits: {s['exits']}",
                  "\nCost ladder (total return): " + " · ".join(f"{k}: {v:+.1%}" for k, v in s["cost_ladder"].items()),
                  "\n| Year | Strategy | Buy & hold |", "|---|---|---|"]
        lines += [f"| {y} | {v['strategy']:+.1%} | {v['buy_hold']:+.1%} |" for y, v in s["by_year"].items()]
        if s.get("windows"):
            lines += ["\n| Window | Strategy | Buy & hold |", "|---|---|---|"]
            lines += [f"| {k} ({v['from']} → {v['to']}) | {v['strategy']:+.1%} | {v['buy_hold']:+.1%} |"
                      for k, v in s["windows"].items()]
    return "\n".join(lines)
