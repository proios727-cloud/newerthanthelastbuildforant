"""Intraday session backtester: opening-range breakout and gap fade. Rule and grid: research/intraday-orb/RULE.md.

Bars are regular-hours only, with ts as ISO time in US/Eastern (scripts/tv_ohlcv_to_csv.py writes them that way).
- A signal is decided at a bar's close and fills at the next bar's open. No lookahead.
- One trade a day at most. Stops and targets are checked on each bar's high/low, and **the stop wins a tie**. A bar that opens
  through the stop fills at that open. Everything is flat at the session's last close.
- Costs are bps of notional per side, so a round trip costs 2 x cost_side.
"""
import datetime as dt
import itertools
import math

ENTRY_CUTOFF = dt.time(14, 0)
COST_LADDER = (("0", 0.0), ("1+1", 2.0), ("2+2", 4.0), ("5+5", 10.0))   # label, bps per side
BASE_COST = 2.0
MIN_TRAIN_SESSIONS = 40
RVOL_LOOKBACK = 20
INTERVAL_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1D": 1440}   # TradingView names


def _time(ts):
    return dt.datetime.fromisoformat(ts)


def sessions(bars):
    """[(date, [bars])] in order. A session is every bar sharing the ET calendar date."""
    out = []
    for b in bars:
        d = b.ts[:10]
        if not out or out[-1][0] != d:
            out.append((d, []))
        out[-1][1].append(b)
    return out


def interval_minutes(sess):
    """The bar size, from the most common gap between consecutive bars of the first full sessions."""
    gaps = {}
    for _, bars in sess[:20]:
        for a, b in zip(bars, bars[1:]):
            m = int((_time(b.ts) - _time(a.ts)).total_seconds() // 60)
            gaps[m] = gaps.get(m, 0) + 1
    if not gaps:
        raise ValueError("need at least one session with two bars")
    return max(gaps, key=gaps.get)


def simulate(bars, side, entry_idx, stop, target):
    """Run one trade from bars[entry_idx].open. Returns (entry_px, exit_px, reason), or None if the entry is already invalid."""
    entry = bars[entry_idx].open
    if (side > 0 and entry <= stop) or (side < 0 and entry >= stop):
        return None
    if target is not None and ((side > 0 and entry >= target) or (side < 0 and entry <= target)):
        return None
    for j in range(entry_idx, len(bars)):
        b = bars[j]
        later = j > entry_idx                # on the entry bar the open is the entry, so no gap-through fill
        if side > 0:
            if b.low <= stop:
                return entry, (min(b.open, stop) if later else stop), "stop"
            if target is not None and b.high >= target:
                return entry, (max(b.open, target) if later else target), "target"
        else:
            if b.high >= stop:
                return entry, (max(b.open, stop) if later else stop), "stop"
            if target is not None and b.low <= target:
                return entry, (min(b.open, target) if later else target), "target"
    return entry, bars[-1].close, "close"


def _signal_ok(bar, ivl):
    return (_time(bar.ts) + dt.timedelta(minutes=ivl)).time() <= ENTRY_CUTOFF


def orb_signal(bars, ivl, or_min, target_r, rvol, or_vol_hist):
    """(side, entry_idx, stop, target) for the first opening-range breakout, or None."""
    k = or_min // ivl
    if k < 1 or len(bars) <= k + 1:
        return None
    if rvol:
        if len(or_vol_hist) < RVOL_LOOKBACK:
            return None
        avg = sum(or_vol_hist[-RVOL_LOOKBACK:]) / RVOL_LOOKBACK
        if avg <= 0 or sum(b.volume for b in bars[:k]) < rvol * avg:
            return None
    hi, lo = max(b.high for b in bars[:k]), min(b.low for b in bars[:k])
    for i in range(k, len(bars) - 1):
        if not _signal_ok(bars[i], ivl):
            return None
        c = bars[i].close
        if c > hi or c < lo:
            side = 1 if c > hi else -1
            stop = lo if side > 0 else hi
            entry = bars[i + 1].open
            target = None if target_r is None else entry + side * target_r * abs(entry - stop)
            return side, i + 1, stop, target
    return None


def gap_signal(bars, ivl, prev_close, gap_pct, stop_x):
    if prev_close is None or len(bars) < 2 or not _signal_ok(bars[0], ivl):
        return None
    o = bars[0].open
    gap = o / prev_close - 1
    if abs(gap) < gap_pct / 100:
        return None
    side = -1 if gap > 0 else 1
    stop = None if stop_x is None else o + stop_x * (o - prev_close)
    if stop is None:                         # no stop: an unreachable level keeps simulate() simple
        stop = -math.inf if side > 0 else math.inf
    return side, 1, stop, prev_close


def grid(strategy, ivl):
    if strategy == "orb":
        ors = (15, 30) if ivl == 15 else (60,) if ivl == 60 else (ivl,)
        return [dict(or_min=o, target_r=t, rvol=v) for o, t, v in itertools.product(ors, (1.0, 2.0, None), (None, 1.2))]
    if strategy == "gap_fade":
        return [dict(gap_pct=g, stop_x=s) for g, s in itertools.product((0.25, 0.5, 1.0), (1.0, None))]
    raise ValueError(strategy)


def label(strategy, p):
    if strategy == "orb":
        t = "close" if p["target_r"] is None else f"{p['target_r']:g}R"
        return f"orb or={p['or_min']} tgt={t} rvol={p['rvol'] or 'off'}"
    return f"gap_fade gap={p['gap_pct']:g}% stop={'none' if p['stop_x'] is None else str(p['stop_x']) + 'x'}"


def run(sess, strategy, params, ivl=None):
    """Gross trades, one per session at most: dicts with date, side, entry, exit, reason, gross (return, not bps)."""
    ivl = ivl or interval_minutes(sess)
    trades, or_vols, prev_close = [], [], None
    for date, bars in sess:
        if strategy == "orb":
            sig = orb_signal(bars, ivl, params["or_min"], params["target_r"], params["rvol"], or_vols)
            k = params["or_min"] // ivl
            or_vols.append(sum(b.volume for b in bars[:k]))
        else:
            sig = gap_signal(bars, ivl, prev_close, params["gap_pct"], params["stop_x"])
        prev_close = bars[-1].close
        if sig is None:
            continue
        side, idx, stop, target = sig
        res = simulate(bars, side, idx, stop, target)
        if res is None:
            continue
        entry, exit_, why = res
        trades.append(dict(date=date, side=side, entry=entry, exit=exit_, reason=why,
                           gross=side * (exit_ / entry - 1)))
    return trades


def net(trades, cost_side):
    return [t["gross"] - 2 * cost_side / 1e4 for t in trades]


def stats(trades, cost_side, n_sessions):
    rets = net(trades, cost_side)
    n = len(rets)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    mean = sum(rets) / n if n else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
    gains, losses = sum(r for r in rets if r > 0), -sum(r for r in rets if r < 0)
    daily = rets + [0.0] * max(n_sessions - n, 0)                   # flat days count as zero-return days
    dm = sum(daily) / len(daily) if daily else 0.0
    dsd = math.sqrt(sum((r - dm) ** 2 for r in daily) / (len(daily) - 1)) if len(daily) > 1 else 0.0
    return {
        "n_trades": n,
        "win_rate": sum(r > 0 for r in rets) / n if n else 0.0,
        "mean_bps": mean * 1e4,
        "t_stat": mean / (sd / math.sqrt(n)) if sd > 0 else 0.0,
        "total_return": eq - 1,
        "max_drawdown": mdd,
        "profit_factor": gains / losses if losses > 0 else (math.inf if gains > 0 else 0.0),
        "sharpe": dm / dsd * math.sqrt(252) if dsd > 0 else 0.0,
    }


def walk_forward(sess, strategies=("orb", "gap_fade"), ivl=None, cost_side=BASE_COST, min_train=MIN_TRAIN_SESSIONS):
    """Re-pick the variant at the start of each month from all earlier sessions; return its trades in that month only.

    Returns (oos_trades, picks, n_oos_sessions). Each strategy family is walked forward on its own.
    """
    ivl = ivl or interval_minutes(sess)
    out = {}
    for strat in strategies:
        variants = grid(strat, ivl)
        all_trades = [run(sess, strat, p, ivl) for p in variants]
        months = sorted({d[:7] for d, _ in sess})
        oos, picks, n_oos = [], [], 0
        for m in months:
            prior = [d for d, _ in sess if d[:7] < m]
            if len(prior) < min_train:
                continue
            cut = m + "-00"
            scores = []
            for trades in all_trades:
                eq = 1.0
                for r in net([t for t in trades if t["date"] < cut], cost_side):
                    eq *= 1 + r
                scores.append(eq)
            best = max(range(len(variants)), key=lambda i: scores[i])   # ties: first in grid order
            picks.append((m, label(strat, variants[best]), scores[best] - 1))
            oos += [t for t in all_trades[best] if t["date"][:7] == m]
            n_oos += sum(1 for d, _ in sess if d[:7] == m)
        out[strat] = (oos, picks, n_oos)
    return out


def buy_hold(sess):
    return sess[-1][1][-1].close / sess[0][1][0].open - 1


def check_daily(sess, daily_bars, tol_bps=15.0):
    """Compare each session's first open and last close with a daily file. Returns (n_compared, n_off, worst_bps)."""
    by_date = {b.ts[:10]: b for b in daily_bars}
    n = off = 0
    worst = 0.0
    for d, bars in sess:
        db = by_date.get(d)
        if db is None:
            continue
        n += 1
        diff = max(abs(bars[0].open / db.open - 1), abs(bars[-1].close / db.close - 1)) * 1e4
        worst = max(worst, diff)
        off += diff > tol_bps
    return n, off, worst


def report(folder, symbols=("SPY", "QQQ"), daily_folder="chart/data"):
    """Every variant at every cost (in-sample, for the robustness table) plus the walk-forward result, per symbol."""
    import pathlib
    from . import load_csv
    out = {}
    for sym in symbols:
        path = pathlib.Path(folder) / f"{sym}.csv"
        if not path.exists():
            continue
        sess = sessions(load_csv(path))
        ivl = interval_minutes(sess)
        daily = pathlib.Path(daily_folder) / f"{sym}.csv"
        rec = {"interval_min": ivl, "sessions": len(sess), "first": sess[0][0], "last": sess[-1][0],
               "buy_hold": buy_hold(sess), "daily_check": check_daily(sess, load_csv(daily)) if daily.exists() else None,
               "variants": [], "walk_forward": {}}
        for strat in ("orb", "gap_fade"):
            for p in grid(strat, ivl):
                trades = run(sess, strat, p, ivl)
                rec["variants"].append({"strategy": strat, "label": label(strat, p),
                                        "by_cost": {lab: stats(trades, c, len(sess)) for lab, c in COST_LADDER}})
        for strat, (oos, picks, n_oos) in walk_forward(sess, ivl=ivl).items():
            rec["walk_forward"][strat] = {"oos_sessions": n_oos, "picks": picks,
                                          "by_cost": {lab: stats(oos, c, n_oos) for lab, c in COST_LADDER}}
        out[sym] = rec
    return out


def format_report(rep):
    lines = []
    for sym, r in rep.items():
        lines.append(f"\n## {sym} — {r['interval_min']}m bars, {r['sessions']} sessions {r['first']} → {r['last']}, "
                     f"buy & hold {r['buy_hold']:+.1%}")
        lines.append("\nIn-sample, every variant (base cost 1+1 bp; net mean per trade):\n")
        lines.append("| Variant | Trades | Win | Mean bp | t | Total | Max DD | PF | Total @2+2 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for v in r["variants"]:
            s, s2 = v["by_cost"]["1+1"], v["by_cost"]["2+2"]
            lines.append(f"| {v['label']} | {s['n_trades']} | {s['win_rate']:.0%} | {s['mean_bps']:+.1f} | "
                         f"{s['t_stat']:+.2f} | {s['total_return']:+.1%} | {s['max_drawdown']:.1%} | "
                         f"{s['profit_factor']:.2f} | {s2['total_return']:+.1%} |")
        lines.append("\nWalk-forward (out-of-sample, variant re-picked monthly):\n")
        lines.append("| Strategy | OOS sessions | Trades | Mean bp @1+1 | t @1+1 | Total @0 | @1+1 | @2+2 | @5+5 | Max DD @1+1 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for strat, w in r["walk_forward"].items():
            c = w["by_cost"]
            lines.append(f"| {strat} | {w['oos_sessions']} | {c['1+1']['n_trades']} | {c['1+1']['mean_bps']:+.1f} | "
                         f"{c['1+1']['t_stat']:+.2f} | {c['0']['total_return']:+.1%} | {c['1+1']['total_return']:+.1%} | "
                         f"{c['2+2']['total_return']:+.1%} | {c['5+5']['total_return']:+.1%} | "
                         f"{c['1+1']['max_drawdown']:.1%} |")
    return "\n".join(lines)
