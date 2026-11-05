"""Backtest stricter entry rules for the two playbooks on Binance BTCUSDT 15m (research only; never trades).

Every variant trades one position at a time, enters at the signal candle's close, and exits on the first
touch of stop or target (stop wins a tie; open after 96 candles = closed at that candle's close).
Costs: fee_bps per side + slippage_bps, charged in R. Results are split in-sample (first 60%) and
out-of-sample (last 40%); a variant only counts if it is positive in both and after costs.

Usage: python backtest_playbooks.py [--days 120] > playbook_backtest.md
"""
from __future__ import annotations

import argparse
import math
import time

import numpy as np

from binance import INTERVAL_MS, Binance
from config import Config
from features import atr, ema, rsi


def fetch(bx, cfg, start_ms, end_ms):
    out, t = [], start_ms
    while t < end_ms:
        raw = bx._get("/api/v3/klines", symbol=cfg.symbol, interval=cfg.interval, startTime=t, limit=1000)
        if not raw:
            break
        out += [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in raw]
        t = raw[-1][0] + 1
    now = int(time.time() * 1000)
    return np.array([r for r in out if r[0] + INTERVAL_MS[cfg.interval] <= now])


def indicators(K, cfg):
    t, o, h, l, c, v = K.T
    a = atr(h, l, c, cfg.atr_period)
    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    r = rsi(c)
    n = len(c)
    sma = np.full(n, np.nan); sd = np.full(n, np.nan)
    for i in range(19, n):
        w = c[i - 19:i + 1]; sma[i] = w.mean(); sd[i] = w.std()
    bbw = 4 * sd / sma * 100
    # ADX(14)
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdi, ndi = 100 * ema(pdm, 14) / a, 100 * ema(ndm, 14) / a
    adx = ema(100 * abs(pdi - ndi) / np.where(pdi + ndi == 0, 1e-12, pdi + ndi), 14)
    vma = np.convolve(v, np.ones(50) / 50, "full")[:n]; vma[:49] = np.nan
    hi20 = np.full(n, np.nan); lo20 = np.full(n, np.nan); bbw_rank = np.full(n, np.nan)
    for i in range(cfg.breakout_lookback + 1, n):
        hi20[i] = h[i - cfg.breakout_lookback:i].max(); lo20[i] = l[i - cfg.breakout_lookback:i].min()
    for i in range(120, n):
        win = bbw[i - 100:i]; bbw_rank[i] = (win < bbw[i - 1]).mean()  # squeeze measured on the candle before
    return dict(t=t, o=o, h=h, l=l, c=c, v=v, atr=a, e20=e20, e50=e50, e200=e200, rsi=r, sma=sma, sd=sd,
                bbw=bbw, adx=adx, volr=v / vma, hi20=hi20, lo20=lo20, sq=bbw_rank)


def breakout(X, i, tgt=3.0, vol=None, adx_min=None, squeeze=None, trend200=False):
    if not (X["c"][i] > X["hi20"][i] and X["e20"][i] > X["e50"][i]):
        return None
    if vol and not X["volr"][i] >= vol: return None
    if adx_min and not X["adx"][i] >= adx_min: return None
    if squeeze is not None and not X["sq"][i] <= squeeze: return None
    if trend200 and not X["c"][i] > X["e200"][i]: return None
    e, a = X["c"][i], X["atr"][i]
    return e, e - 1.5 * a, e + tgt * a


def mean_rev(X, i, rsi_max=35, adx_max=None, trend200=False, vol_max=None):
    e, a, mid, sd = X["c"][i], X["atr"][i], X["sma"][i], X["sd"][i]
    if not (e < mid - 2 * sd and X["rsi"][i] < rsi_max and mid > e + 0.5 * a):
        return None
    if adx_max and not X["adx"][i] <= adx_max: return None
    if trend200 and not e > X["e200"][i]: return None
    if vol_max and not X["volr"][i] <= vol_max: return None
    return e, e - 1.5 * a, mid


VARIANTS = {
    "B0 breakout (live rule)": lambda X, i: breakout(X, i),
    "B1 + volume ≥1.5×": lambda X, i: breakout(X, i, vol=1.5),
    "B2 + ADX ≥25": lambda X, i: breakout(X, i, adx_min=25),
    "B3 + after squeeze (BB width bottom 20%)": lambda X, i: breakout(X, i, squeeze=0.2),
    "B4 + volume ≥1.5× + squeeze": lambda X, i: breakout(X, i, vol=1.5, squeeze=0.2),
    "B5 + volume ≥1.5× + above EMA200": lambda X, i: breakout(X, i, vol=1.5, trend200=True),
    "B6 B1 with 2×ATR target": lambda X, i: breakout(X, i, tgt=2.0, vol=1.5),
    "M0 mean reversion (live rule)": lambda X, i: mean_rev(X, i),
    "M1 + ADX ≤20": lambda X, i: mean_rev(X, i, adx_max=20),
    "M2 + RSI <25": lambda X, i: mean_rev(X, i, rsi_max=25),
    "M3 + ADX ≤20 + above EMA200": lambda X, i: mean_rev(X, i, adx_max=20, trend200=True),
    "M4 + ADX ≤20 + no volume spike (≤2×)": lambda X, i: mean_rev(X, i, adx_max=20, vol_max=2.0),
}


def run(X, fn, start, end, cost_frac):
    trades, i = [], start
    while i < end - 1:
        s = fn(X, i)
        if not s or not all(map(math.isfinite, s)) or s[0] - s[1] <= 0:
            i += 1; continue
        e, stop, tgt = s
        risk = e - stop
        r_out, j = None, i + 1
        for j in range(i + 1, min(i + 97, len(X["c"]))):
            if X["l"][j] <= stop: r_out = -1.0; break
            if X["h"][j] >= tgt: r_out = (tgt - e) / risk; break
        if r_out is None:
            r_out = (X["c"][j] - e) / risk
        r_out -= cost_frac * e / risk
        trades.append(r_out)
        i = j + 1
    return np.array(trades)


def stats(r):
    if len(r) == 0:
        return dict(n=0, win=float("nan"), avg=float("nan"), tot=0.0, t=float("nan"), dd=0.0)
    eq = np.cumsum(r); dd = float((np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max())
    t = r.mean() / (r.std(ddof=1) / math.sqrt(len(r))) if len(r) > 1 and r.std() > 0 else float("nan")
    return dict(n=len(r), win=float((r > 0).mean()), avg=float(r.mean()), tot=float(r.sum()), t=float(t), dd=dd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    a = ap.parse_args()
    cfg = Config.load()
    ms = INTERVAL_MS[cfg.interval]
    now = int(time.time() * 1000)
    K = fetch(Binance(cfg.binance_base), cfg, now - (a.days * 96 + 300) * ms, now)
    X = indicators(K, cfg)
    start, n = 300, len(K)
    split = start + int((n - start) * 0.6)
    fmt = lambda ms_: time.strftime("%Y-%m-%d", time.gmtime(ms_ / 1000))
    base_cost = (2 * cfg.fee_bps + cfg.slippage_bps) / 1e4
    bh = (X["c"][-1] / X["c"][start] - 1) * 100
    print(f"# Playbook backtest — BTCUSDT 15m, {fmt(X['t'][start])} → {fmt(X['t'][-1])} ({(n - start) / 96:.0f} days)\n")
    print(f"In-sample to {fmt(X['t'][split])}, out-of-sample after. Costs {base_cost * 1e4:.0f} bps round trip "
          f"(fees {cfg.fee_bps:.0f} bps/side + {cfg.slippage_bps:.0f} bps slippage), charged in R. BTC buy-and-hold: {bh:+.1f}%.\n")
    print("| variant | trades IS | avg R IS | trades OOS | avg R OOS | win OOS | total R OOS | t OOS | max DD R (all) | avg R at 2× cost (all) | verdict |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    results = []
    for name, fn in VARIANTS.items():
        IS, OOS = run(X, fn, start, split, base_cost), run(X, fn, split, n, base_cost)
        ALL2 = run(X, fn, start, n, 2 * base_cost)
        si, so, s2 = stats(IS), stats(OOS), stats(ALL2)
        sall = stats(np.concatenate([IS, OOS]))
        if so["n"] < 15 or si["n"] < 15:
            verdict = "too few trades"
        elif si["avg"] > 0 and so["avg"] > 0 and s2["avg"] > 0:
            verdict = "candidate" if so["t"] >= 2.0 else "positive, not significant"
        elif si["avg"] > 0 and so["avg"] <= 0:
            verdict = "fails out-of-sample"
        else:
            verdict = "reject"
        results.append((name, verdict))
        print(f"| {name} | {si['n']} | {si['avg']:+.3f} | {so['n']} | {so['avg']:+.3f} | {so['win']:.0%} | {so['tot']:+.1f} | "
              f"{so['t']:+.2f} | {sall['dd']:.1f} | {s2['avg']:+.3f} | {verdict} |")
    k = len(VARIANTS)
    print(f"\n{k} variants were tested on the same data, so roughly one in {k} would look good by luck at 1 in 20 odds; "
          f"a t-statistic of about {2.0 + 0.3 * math.log(k):.1f} or more out-of-sample is the bar for trusting one.\n")
    cands = [n_ for n_, v in results if v == "candidate"]
    print("Candidates: " + (", ".join(cands) if cands else "none") + ".")


if __name__ == "__main__":
    main()
