"""Regime risk switch: Drex's regime call sets how much BTC a core paper position holds (spot, long-only).

Policy (per closed candle):
  PANIC p >= panic_threshold           -> 0%
  uptrend (EMA20 > EMA50)               -> P(TRENDING) * 100% + P(CHOPPY) * 50%
  downtrend                             -> P(CHOPPY) * 25%
  quantised to 0 / 25 / 50 / 75 / 100%; rebalances only when the target moves by >= 25 points and at least
  `min_hold` candles after the last change (cuts churn), except PANIC exits, which are immediate.

Backtest:  python risk_switch.py --backtest [--days 365]   (rule-based stand-in regime; no Drex calls)
Replay:    python risk_switch.py --replay <decisions.jsonl>  (the bot's real Drex calls)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from binance import INTERVAL_MS, Binance
from config import Config

STEP = 0.25


def target_exposure(probs: dict, trend_up: bool, panic_threshold: float = 0.5) -> float:
    pt, pc, pp = probs.get("TRENDING", 0.0), probs.get("CHOPPY", 0.0), probs.get("PANIC", 0.0)
    if pp >= panic_threshold:
        return 0.0
    raw = pt * 1.0 + pc * 0.5 if trend_up else pc * 0.25
    return min(1.0, max(0.0, round(raw / STEP) * STEP))


class CoreSleeve:
    """Paper core position: cash + BTC, rebalanced to the switch's target. State is a plain dict."""

    def __init__(self, state: dict | None, equity: float, fee_bps: float, slip_bps: float, min_hold: int = 4):
        self.s = state or {"cash": equity, "btc": 0.0, "exposure": 0.0, "since_change": 99, "fees": 0.0, "trades": 0}
        self.cost = (fee_bps + slip_bps) / 1e4
        self.min_hold = min_hold

    def value(self, px: float) -> float:
        return self.s["cash"] + self.s["btc"] * px

    def step(self, px: float, probs: dict, trend_up: bool, panic_threshold: float = 0.5) -> dict | None:
        s = self.s
        s["since_change"] += 1
        tgt = target_exposure(probs, trend_up, panic_threshold)
        panic_exit = tgt == 0.0 and probs.get("PANIC", 0.0) >= panic_threshold and s["exposure"] > 0
        if not panic_exit and (abs(tgt - s["exposure"]) < STEP or s["since_change"] < self.min_hold):
            return None
        val = self.value(px)
        want_btc = val * tgt / px
        trade_btc = want_btc - s["btc"]
        fee = abs(trade_btc) * px * self.cost
        s["btc"] = want_btc
        s["cash"] = val - want_btc * px - fee
        s["fees"] += fee
        s["trades"] += 1
        prev, s["exposure"], s["since_change"] = s["exposure"], tgt, 0
        return {"from": prev, "to": tgt, "price": round(px, 2), "fee": round(fee, 4), "value": round(self.value(px), 2)}


# ---------- backtest with a rule-based stand-in regime ----------

def _ema(x, n):
    a, out = 2 / (n + 1), np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def proxy_probs(h, l, c, v):
    """Deterministic stand-in for Drex, from the v3 question's criteria (one-hot)."""
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    atr = _ema(tr, 14)
    atr100 = np.convolve(atr, np.ones(100) / 100, "full")[:len(c)]
    e20, e50 = _ema(c, 20), _ema(c, 50)
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdi, ndi = 100 * _ema(pdm, 14) / atr, 100 * _ema(ndm, 14) / atr
    adx = _ema(100 * abs(pdi - ndi) / np.where(pdi + ndi == 0, 1e-12, pdi + ndi), 14)
    sd = np.array([c[max(0, i - 19):i + 1].std() for i in range(len(c))])
    bbw = 4 * sd / np.maximum(1e-9, np.convolve(c, np.ones(20) / 20, "full")[:len(c)]) * 100
    vma = np.convolve(v, np.ones(50) / 50, "full")[:len(c)]
    volr = v / np.where(vma == 0, 1, vma)
    sep = abs(e20 / e50 - 1) * 100
    drop12 = (c - np.concatenate([np.full(12, c[0]), c[:-12]])) / atr
    out = []
    for i in range(len(c)):
        if i < 150:
            out.append({"CHOPPY": 1.0}); continue
        if atr[i] > 2.0 * atr100[i] or drop12[i] < -4:
            out.append({"PANIC": 1.0})
        elif (adx[i] > 25 and sep[i] > 0.4 and bbw[i] > 1.0 and volr[i] >= 1.0) or (bbw[i] < 0.9 and adx[i] > 40 and volr[i] >= 0.7):
            out.append({"TRENDING": 1.0})
        else:
            out.append({"CHOPPY": 1.0})
    return out, e20 > e50


def simulate(c, probs, trend_up, cfg, policy):
    sl = CoreSleeve(None, 10_000.0, cfg.fee_bps, cfg.slippage_bps)
    vals = np.empty(len(c))
    for i in range(len(c)):
        if policy == "hold":
            if i == 0:
                sl.step(c[0], {"TRENDING": 1.0}, True)
                sl.s["since_change"] = -10**9  # never rebalance again
        elif policy == "trend":
            sl.step(c[i], {"TRENDING": 1.0} if trend_up[i] else {"CHOPPY": 0.0}, bool(trend_up[i]))
        else:
            sl.step(c[i], probs[i], bool(trend_up[i]))
        vals[i] = sl.value(c[i])
    return vals, sl.s


def metrics(vals, per_year):
    r = np.diff(vals) / vals[:-1]
    peak = np.maximum.accumulate(vals)
    sharpe = r.mean() / r.std() * math.sqrt(per_year) if r.std() > 0 else float("nan")
    return {"return": vals[-1] / vals[0] - 1, "max_dd": float(((peak - vals) / peak).max()), "sharpe": float(sharpe)}


def backtest(days: int):
    cfg = Config.load()
    ms = INTERVAL_MS[cfg.interval]
    now = int(time.time() * 1000)
    bx, out, t = Binance(cfg.binance_base), [], now - (days * 96 + 200) * ms
    while t < now:
        raw = bx._get("/api/v3/klines", symbol=cfg.symbol, interval=cfg.interval, startTime=t, limit=1000)
        if not raw:
            break
        out += raw
        t = raw[-1][0] + 1
    K = np.array([[float(x) for x in k[1:6]] for k in out if k[6] < now])
    o, h, l, c, v = K.T
    probs, trend_up = proxy_probs(h, l, c, v)
    start = 200
    c, probs, trend_up = c[start:], probs[start:], trend_up[start:]
    split = int(len(c) * 0.6)
    per_year = 96 * 365
    fmt = lambda ms_: time.strftime("%Y-%m-%d", time.gmtime(ms_ / 1000))
    print(f"# Regime risk switch backtest — BTCUSDT 15m, {fmt(out[start][0])} → {fmt(out[-1][0])} ({len(c) / 96:.0f} days)\n")
    print("Stand-in regime from the v3 question's own criteria (no Drex calls). Costs "
          f"{cfg.fee_bps + cfg.slippage_bps:.0f} bps per side on traded notional. Out-of-sample = last 40%.\n")
    print("| policy | return (all) | max drawdown | Sharpe | return OOS | max DD OOS | rebalances | fees $ | time in market |")
    print("|---|---|---|---|---|---|---|---|---|")
    for pol, label in (("hold", "Buy and hold"), ("trend", "Trend filter (EMA20>EMA50, 0/100%)"), ("switch", "Regime risk switch")):
        vals, st = simulate(c, probs, trend_up, cfg, pol)
        m = metrics(vals, per_year)
        vo, _ = simulate(c[split:], probs[split:], trend_up[split:], cfg, pol)
        mo = metrics(vo, per_year)
        exp = st["exposure"]
        tim = "100%" if pol == "hold" else f"{np.mean([target_exposure(p, bool(u)) for p, u in zip(probs, trend_up)]) * 100:.0f}% avg" if pol == "switch" else f"{trend_up.mean() * 100:.0f}%"
        print(f"| {label} | {m['return']:+.1%} | {m['max_dd']:.1%} | {m['sharpe']:.2f} | {mo['return']:+.1%} | {mo['max_dd']:.1%} | "
              f"{st['trades']} | {st['fees']:,.0f} | {tim} |")
    counts = {k: sum(1 for p in probs if p.get(k)) for k in ("TRENDING", "CHOPPY", "PANIC")}
    print(f"\nStand-in regime mix: {counts}. Ending exposure for the switch: {exp:.0%}.")


def replay(path: str):
    cfg = Config.load()
    rows = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    calls = [r for r in rows if r["kind"] == "regime"]
    sl = CoreSleeve(None, 10_000.0, cfg.fee_bps, cfg.slippage_bps)
    c0, events = calls[0]["candle"]["close"], []
    for r in calls:
        px, up = r["candle"]["close"], r["candle"]["ema20"] > r["candle"]["ema50"]
        ev = sl.step(px, r["probs"], up)
        if ev:
            events.append(ev)
    last = calls[-1]["candle"]["close"]
    print(f"Replay of {len(calls)} real Drex calls: switch {sl.value(last) / 10_000 - 1:+.2%} vs hold {last / c0 - 1:+.2%}, "
          f"{len(events)} rebalances, fees ${sl.s['fees']:.2f}, ending exposure {sl.s['exposure']:.0%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--replay")
    a = ap.parse_args()
    if a.backtest:
        backtest(a.days)
    if a.replay:
        replay(a.replay)
