"""Niche swing desks: independent long-only spot strategies on 4h candles, judged by walk-forward.

Each desk maps closed candles -> target exposure (0..1) using only information up to that bar's close;
the exposure is held over the NEXT bar. Costs: (fee + slippage) bps per side on traded notional.

Walk-forward:  python desks.py --walkforward [--symbols BTCUSDT,ETHUSDT,SOLUSDT] [--fit 180 --test 30]
  For every window, each desk picks the setting with the best Sharpe on the previous `fit` days,
  then trades the next `test` days unseen. Only the unseen test slices are stitched into the result.
Live paper:    desks.live_step(state, cfg) is called by the bot; it advances each desk's paper sleeve on
  every newly closed 4h candle using the setting the walk-forward chose most recently.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import numpy as np

from binance import Binance
from config import Config

BAR_MS = 4 * 3_600_000
BARS_PER_DAY = 6
PER_YEAR = BARS_PER_DAY * 365
CACHE = Path(__file__).resolve().parent / "research" / "cache"


# ---------- indicators (causal) ----------

def ema(x, n):
    a, out = 2 / (n + 1), np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def sma(x, n):
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.full(len(x), np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def atr(h, l, c, n=14):
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    return ema(tr, n)


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up, dn = ema(np.maximum(d, 0), n), ema(np.maximum(-d, 0), n)
    return 100 - 100 / (1 + up / np.where(dn == 0, 1e-12, dn))


def roll_max(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1:i + 1].max()
    return out


def roll_min(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1:i + 1].min()
    return out


def adx(h, l, c, n=14):
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, l, c, n)
    pdi, ndi = 100 * ema(pdm, n) / a, 100 * ema(ndm, n) / a
    return ema(100 * abs(pdi - ndi) / np.where(pdi + ndi == 0, 1e-12, pdi + ndi), n)


# ---------- desks: f(K, **params) -> exposure array ----------
# K = dict of numpy arrays o,h,l,c,v. Daily-equivalent EMAs on 4h bars: N days * 6.

def desk_trend(K, fast=20, slow=50):
    """Daily trend filter (the bot's risk switch, without Drex): in while EMA(fast d) > EMA(slow d)."""
    c = K["c"]
    return (ema(c, fast * 6) > ema(c, slow * 6)).astype(float)


def desk_volgate_trend(K, fast=20, slow=50, target_vol=0.5):
    """Trend filter sized by volatility: exposure = min(1, target annual vol / realised 30d vol)."""
    c = K["c"]
    r = np.diff(np.log(c), prepend=np.log(c[0]))
    rv = np.sqrt(np.convolve(r ** 2, np.ones(180) / 180, "full")[:len(c)] * PER_YEAR)
    size = np.clip(target_vol / np.where(rv == 0, 1e9, rv), 0, 1)
    return (ema(c, fast * 6) > ema(c, slow * 6)) * size


def desk_pullback(K, rsi_in=35, rsi_out=65, stop_atr=3.0, trend_d=50):
    """Swing: buy RSI pullbacks only inside a daily uptrend; exit on RSI strength, trend loss or ATR stop."""
    c, h, l = K["c"], K["h"], K["l"]
    r, a, tr = rsi(c), atr(h, l, c), c > ema(c, trend_d * 6)
    pos, stop, out = 0.0, 0.0, np.zeros(len(c))
    for i in range(len(c)):
        if pos:
            if r[i] > rsi_out or not tr[i] or c[i] < stop:
                pos = 0.0
        elif tr[i] and r[i] < rsi_in:
            pos, stop = 1.0, c[i] - stop_atr * a[i]
        out[i] = pos
    return out


def desk_breakout(K, enter_d=20, exit_d=10):
    """Donchian breakout: buy a new enter_d-day closing high, exit on an exit_d-day closing low."""
    c = K["c"]
    hi = np.concatenate([[np.nan], roll_max(c, enter_d * 6)[:-1]])
    lo = np.concatenate([[np.nan], roll_min(c, exit_d * 6)[:-1]])
    pos, out = 0.0, np.zeros(len(c))
    for i in range(len(c)):
        if pos and c[i] < lo[i]:
            pos = 0.0
        elif not pos and c[i] > hi[i]:
            pos = 1.0
        out[i] = pos
    return out


def desk_range_revert(K, z_in=2.0, adx_max=20, hold_max=18):
    """Range mean-reversion: when ADX says no trend, buy closes below the 20-bar band, exit at the mean."""
    c, h, l = K["c"], K["h"], K["l"]
    m = sma(c, 20)
    sd = np.array([c[max(0, i - 19):i + 1].std() for i in range(len(c))])
    ax = adx(h, l, c)
    pos, held, out = 0.0, 0, np.zeros(len(c))
    for i in range(len(c)):
        if pos:
            held += 1
            if c[i] >= m[i] or held >= hold_max:
                pos = 0.0
        elif ax[i] < adx_max and not np.isnan(m[i]) and c[i] < m[i] - z_in * sd[i]:
            pos, held = 1.0, 0
        out[i] = pos
    return out


def desk_shock_rebound(K, drop_atr=4.0, hold=12, atr_ratio=1.3):
    """After a shock (fast drop of drop_atr ATRs with ATR already elevated) buy the snap-back, hold `hold` bars.
    This tests the bot's v6 finding: once ATR is elevated the next hours usually chop, not crash further."""
    c, h, l = K["c"], K["h"], K["l"]
    a = atr(h, l, c)
    a100 = sma(a, 100)
    drop = (c - np.concatenate([np.full(6, c[0]), c[:-6]])) / a
    pos, held, out = 0.0, 0, np.zeros(len(c))
    for i in range(len(c)):
        if pos:
            held += 1
            if held >= hold:
                pos = 0.0
        elif drop[i] < -drop_atr and a100[i] > 0 and a[i] > atr_ratio * a100[i]:
            pos, held = 1.0, 0
        out[i] = pos
    return out


def grid(**axes):
    keys = list(axes)
    return [dict(zip(keys, v)) for v in itertools.product(*axes.values())]


DESKS = {
    "trend": (desk_trend, grid(fast=[10, 20, 50], slow=[30, 50, 100, 200]), {"fast": 20, "slow": 50}),
    "volgate_trend": (desk_volgate_trend, grid(fast=[10, 20], slow=[50, 100], target_vol=[0.3, 0.5, 0.8]),
                      {"fast": 20, "slow": 50, "target_vol": 0.5}),
    "pullback": (desk_pullback, grid(rsi_in=[25, 30, 35, 40], rsi_out=[55, 65, 75], stop_atr=[2.0, 3.0, 5.0], trend_d=[50, 100]),
                 {"rsi_in": 35, "rsi_out": 65, "stop_atr": 3.0, "trend_d": 50}),
    "breakout": (desk_breakout, grid(enter_d=[10, 20, 55], exit_d=[5, 10, 20]), {"enter_d": 20, "exit_d": 10}),
    "range_revert": (desk_range_revert, grid(z_in=[1.5, 2.0, 2.5], adx_max=[15, 20, 25], hold_max=[6, 18, 36]),
                     {"z_in": 2.0, "adx_max": 20, "hold_max": 18}),
    "shock_rebound": (desk_shock_rebound, grid(drop_atr=[3.0, 4.0, 5.0], hold=[6, 12, 24], atr_ratio=[1.0, 1.3, 1.6]),
                      {"drop_atr": 4.0, "hold": 12, "atr_ratio": 1.3}),
}


# ---------- data ----------

def load(symbol: str, cfg: Config, since="2019-01-01") -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{symbol}_4h.json"
    rows = json.loads(f.read_text()) if f.exists() else []
    bx = Binance(cfg.binance_base)
    now = int(time.time() * 1000)
    t = rows[-1][0] + BAR_MS if rows else int(time.mktime(time.strptime(since, "%Y-%m-%d")) * 1000)
    while t < now - BAR_MS:
        raw = bx._get("/api/v3/klines", symbol=symbol, interval="4h", startTime=t, limit=1000)
        if not raw:
            break
        rows += [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in raw if k[6] < now]
        t = raw[-1][0] + BAR_MS
    f.write_text(json.dumps(rows))
    A = np.array(rows)
    return {"t": A[:, 0].astype(np.int64), "o": A[:, 1], "h": A[:, 2], "l": A[:, 3], "c": A[:, 4], "v": A[:, 5]}


# ---------- evaluation ----------

def bar_returns(pos, c, cost):
    """Strategy return per bar: exposure set at bar i's close earns bar i+1's move, minus turnover cost."""
    r = np.zeros(len(c))
    r[1:] = pos[:-1] * (c[1:] / c[:-1] - 1)
    turn = np.abs(np.diff(pos, prepend=0.0))
    return r - turn * cost


def stats(r, pos):
    if len(r) < 2:
        return {}
    eq = np.cumprod(1 + r)
    peak = np.maximum.accumulate(eq)
    sd = r.std()
    entries = int(((pos[1:] > 0) & (pos[:-1] == 0)).sum())
    return {"ret": float(eq[-1] - 1), "cagr": float(eq[-1] ** (PER_YEAR / len(r)) - 1),
            "max_dd": float(((peak - eq) / peak).max()),
            "sharpe": float(r.mean() / sd * math.sqrt(PER_YEAR)) if sd > 0 else 0.0,
            "in_mkt": float((pos > 0).mean()), "entries": entries}


def walk_forward(K, cost, fit_days=180, test_days=30, warmup_days=220):
    c, n = K["c"], len(K["c"])
    fit, test, start = fit_days * 6, test_days * 6, warmup_days * 6
    res = {}
    for name, (fn, params, default) in DESKS.items():
        series = [(p, fn(K, **p)) for p in params]
        rets = [bar_returns(pos, c, cost) for _, pos in series]
        oos_r, oos_pos, picks, windows = [], [], [], []
        i = start + fit
        while i + 1 < n:
            j = min(n, i + test)
            scores = []
            for (p, pos), r in zip(series, rets):
                s = r[i - fit:i]
                sh = s.mean() / s.std() * math.sqrt(PER_YEAR) if s.std() > 0 else -9.0
                scores.append(sh)
            k = int(np.argmax(scores))
            oos_r.append(rets[k][i:j]); oos_pos.append(series[k][1][i:j]); picks.append(k)
            windows.append(float(np.prod(1 + rets[k][i:j]) - 1))
            i = j
        r, pos = np.concatenate(oos_r), np.concatenate(oos_pos)
        d = DESKS[name][2]
        dpos = fn(K, **d)
        dr = bar_returns(dpos, c, cost)[start + fit:]
        changes = sum(1 for a, b in zip(picks, picks[1:]) if a != b)
        res[name] = {"wf": stats(r, pos), "fixed": stats(dr, dpos[start + fit:]),
                     "win_windows": float(np.mean([w > 0 for w in windows])),
                     "pick_changes": changes / max(1, len(picks) - 1),
                     "last_pick": params[picks[-1]], "series_r": r, "series_pos": pos}
    hold_r = np.zeros(n); hold_r[1:] = c[1:] / c[:-1] - 1
    res["_hold"] = {"wf": stats(hold_r[start + fit:], np.ones(n - start - fit))}
    # Ensemble: equal-weight the desks (each already walk-forward), no extra fitting.
    names = [k for k in DESKS]
    L = min(len(res[k]["series_r"]) for k in names)
    er = np.mean([res[k]["series_r"][:L] for k in names], axis=0)
    ep = np.mean([res[k]["series_pos"][:L] for k in names], axis=0)
    res["_ensemble"] = {"wf": stats(er, ep)}
    res["_span"] = (int(K["t"][start + fit]), int(K["t"][-1]))
    return res


def report(symbols, fit, test):
    cfg = Config.load()
    cost = (cfg.fee_bps + cfg.slippage_bps) / 1e4
    fmt = lambda ms: time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))
    lines, summary = [], {}
    lines.append(f"# Niche desk walk-forward — 4h candles, fit {fit}d → trade next {test}d unseen, rolled forward\n")
    lines.append(f"Costs {cfg.fee_bps + cfg.slippage_bps:.0f} bps per side. Long-only spot, no leverage. "
                 "Only unseen test slices are counted. `fixed` = the desk's default setting for the whole span (no tuning).\n")
    for sym in symbols:
        K = load(sym, cfg)
        res = walk_forward(K, cost, fit, test)
        a, b = res["_span"]
        lines.append(f"\n## {sym}  ({fmt(a)} → {fmt(b)}, {(b - a) / 86_400_000 / 365:.1f} years unseen)\n")
        lines.append("| desk | walk-fwd CAGR | max DD | Sharpe | fixed CAGR | fixed DD | win windows | setting churn | in market | entries/yr |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        yrs = (b - a) / 86_400_000 / 365
        rows = []
        for k in list(DESKS) + ["_ensemble", "_hold"]:
            w = res[k]["wf"]
            f = res[k].get("fixed", {})
            label = {"_ensemble": "**ensemble (equal weight)**", "_hold": "buy & hold"}.get(k, k)
            rows.append((k, w))
            lines.append(f"| {label} | {w['cagr']:+.1%} | {w['max_dd']:.1%} | {w['sharpe']:.2f} | "
                         f"{f.get('cagr', float('nan')):+.1%} | {f.get('max_dd', float('nan')):.1%} | "
                         f"{res[k].get('win_windows', float('nan')):.0%} | {res[k].get('pick_changes', float('nan')):.0%} | "
                         f"{w['in_mkt']:.0%} | {w['entries'] / yrs:.0f} |".replace("+nan%", "–").replace("nan%", "–"))
        summary[sym] = {k: {"cagr": round(res[k]["wf"]["cagr"], 4), "max_dd": round(res[k]["wf"]["max_dd"], 4),
                            "sharpe": round(res[k]["wf"]["sharpe"], 3),
                            **({"last_pick": res[k]["last_pick"], "win_windows": round(res[k]["win_windows"], 3)}
                               if k in DESKS else {})}
                        for k in list(DESKS) + ["_ensemble", "_hold"]}
    return "\n".join(lines), summary


# ---------- live paper ----------

def live_step(state: dict, cfg: Config, picks: dict, symbol="BTCUSDT") -> list[dict]:
    """Advance each desk's paper sleeve on newly closed 4h candles. Returns events (entries/exits)."""
    bx = Binance(cfg.binance_base)
    raw = bx._get("/api/v3/klines", symbol=symbol, interval="4h", limit=1000)
    now = int(time.time() * 1000)
    raw = [k for k in raw if k[6] < now]
    A = np.array([[k[0], *map(float, k[1:6])] for k in raw])
    K = {"t": A[:, 0].astype(np.int64), "o": A[:, 1], "h": A[:, 2], "l": A[:, 3], "c": A[:, 4], "v": A[:, 5]}
    cost = (cfg.fee_bps + cfg.slippage_bps) / 1e4
    events = []
    for name, (fn, _, default) in DESKS.items():
        p = picks.get(name, default)
        pos = fn(K, **p)
        s = state.setdefault(name, {"value": 10_000.0, "exposure": 0.0, "last_t": int(K["t"][-2]), "entries": 0})
        for i in range(len(K["t"])):
            t = int(K["t"][i])
            if t <= s["last_t"]:
                continue
            j = i - 1
            s["value"] = float(s["value"] * (1 + s["exposure"] * (K["c"][i] / K["c"][j] - 1)))
            new = float(pos[i])
            if abs(new - s["exposure"]) > 1e-9:
                s["value"] = float(s["value"] * (1 - abs(new - s["exposure"]) * cost))
                if s["exposure"] == 0 and new > 0:
                    s["entries"] += 1
                events.append({"desk": name, "t": t, "from": round(s["exposure"], 3), "to": round(new, 3),
                               "price": float(K["c"][i]), "value": round(s["value"], 2)})
                s["exposure"] = new
            s["last_t"] = t
        s["price"] = float(K["c"][-1])
        s["setting"] = p
    return events


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--walkforward", action="store_true")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--fit", type=int, default=180)
    ap.add_argument("--test", type=int, default=30)
    ap.add_argument("--out", default="research")
    a = ap.parse_args()
    if a.walkforward:
        md, summ = report(a.symbols.split(","), a.fit, a.test)
        print(md)
        day = time.strftime("%Y-%m-%d", time.gmtime())
        Path(a.out, f"desks-walkforward-{day}.md").write_text(md + "\n")
        Path(a.out, "desk_picks.json").write_text(json.dumps(
            {"date": day, "fit": a.fit, "test": a.test, "summary": summ,
             "picks": {k: v["last_pick"] for k, v in summ["BTCUSDT"].items() if not k.startswith("_")}}, indent=1))
