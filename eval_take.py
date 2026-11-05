"""Offline test of the TAKE/SKIP question on real historical setups (paper research; never trades).

Finds every breakout and mean-reversion setup in the last N days of BTCUSDT 15m candles, replays whether
stop or target was hit first, then asks Drex two TAKE variants about each setup in one call:
  current — the live `signal.take` question from questions.json
  outcome — a plain "will target be hit before stop" question with no setup checklist
Historical order books aren't available, so both variants see candle metrics and the trade only (no image,
no book): the comparison is fair between variants, but absolute numbers differ from live.

Usage: python eval_take.py [--days 14] [--max 24] > take_eval.md
"""
from __future__ import annotations

import argparse
import json
import random
import time

import numpy as np

from binance import INTERVAL_MS, Binance
from config import Config
from drex import Drex, DrexError, load_questions
from features import candle_features
from review import r_of
from strategies import breakout, mean_reversion, resolve

OUTCOME_Q = {"type": "noul",
             "instructions": ("The state describes a proposed BTCUSDT trade (side, entry, stop, target) and the market's candle "
                              "metrics when it was proposed. Estimate the probability that price touches the TARGET before it "
                              "touches the STOP. Give a calibrated probability: a 2:1 reward-to-risk trade in a random market "
                              "reaches target first about one time in three."),
             "criteria": {"true": "Target is hit before stop.", "false": "Stop is hit before target."}}


def fetch(bx: Binance, cfg, start_ms: int, end_ms: int) -> list[dict]:
    """Closed candles with every field candle_features() uses."""
    out, t = [], start_ms
    while t < end_ms:
        raw = bx._get("/api/v3/klines", symbol=cfg.symbol, interval=cfg.interval, startTime=t, limit=1000)
        if not raw:
            break
        out += [{"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5]),
                 "close_time": k[6], "trades": k[8], "taker_buy_v": float(k[9])} for k in raw]
        t = raw[-1][0] + 1
    return [c for c in out if c["close_time"] < int(time.time() * 1000)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--max", type=int, default=24)
    a = ap.parse_args()
    cfg = Config.load()
    ms = INTERVAL_MS[cfg.interval]
    now = int(time.time() * 1000)
    candles = fetch(Binance(cfg.binance_base), cfg, now - (a.days * 96 + 200) * ms, now)
    look = cfg.candles_lookback
    setups, last = [], {}
    for i in range(look, len(candles) - 1):
        win = candles[i - look + 1:i + 1]
        for fn in (breakout, mean_reversion):
            s = fn(win, cfg)
            if not s or i - last.get(s.playbook, -99) < 8:  # one setup per playbook per 2h
                continue
            out = resolve(s.as_dict(), candles[i + 1:i + 1 + 96])
            if out == "OPEN":
                continue
            last[s.playbook] = i
            setups.append({"i": i, "signal": s.as_dict(), "outcome": out, "r": r_of(s.as_dict(), out)})
    random.Random(7).shuffle(setups)
    sample = sorted(setups[:a.max], key=lambda x: x["i"])

    q = load_questions()
    questions = {"current": q["signal"]["take"], "outcome": OUTCOME_Q}
    drex = Drex(cfg.drex_base, cfg.drex_model, 60)
    rows = []
    for s in sample:
        win = candles[s["i"] - look + 1:s["i"] + 1]
        state = {"symbol": cfg.symbol, "interval": cfg.interval, "candle": candle_features(win, cfg.atr_period),
                 "order_book": "not available in this historical test", "proposed_trade": s["signal"]}
        try:
            ans = drex.decide(state, questions)["answers"]
        except DrexError as e:
            rows.append({**s, "error": str(e)})
            continue
        rows.append({**s, "p_current": float(ans["current"]["noul"]), "p_outcome": float(ans["outcome"]["noul"])})
        time.sleep(0.5)

    ok = [r for r in rows if "error" not in r]
    win = np.array([r["outcome"] == "TARGET" for r in ok], dtype=float)
    print(f"# TAKE question test — {len(setups)} resolved setups in {a.days} days, {len(ok)} asked ({len(rows) - len(ok)} errors)\n")
    print(f"Base rate: target hit first in {win.mean():.0%} of asked setups; average replay R {np.mean([r['r'] for r in ok]):+.2f}.\n")
    print("| variant | mean p | mean p (won) | mean p (lost) | Brier | trades @ p≥0.65 | R @ p≥0.65 | trades @ p>breakeven+0.05 | R @ breakeven |")
    print("|---|---|---|---|---|---|---|---|---|")
    for v in ("current", "outcome"):
        p = np.array([r[f"p_{v}"] for r in ok])
        be = np.array([1 / (1 + r["signal"]["rr"]) + 0.05 for r in ok])
        R = np.array([r["r"] for r in ok])
        hi, b = p >= 0.65, p > be
        pw = p[win == 1].mean() if win.any() else float("nan")
        pl = p[win == 0].mean() if (win == 0).any() else float("nan")
        print(f"| {v} | {p.mean():.3f} | {pw:.3f} | {pl:.3f} | {np.mean((p - win) ** 2):.3f} | {hi.sum()} | {R[hi].sum():+.2f} | {b.sum()} | {R[b].sum():+.2f} |")
    print("\n## Setups\n\n| candle | playbook | rr | outcome | R | p current | p outcome |\n|---|---|---|---|---|---|---|")
    for r in rows:
        t = time.strftime("%m-%d %H:%M", time.gmtime(candles[r["i"]]["t"] / 1000))
        if "error" in r:
            print(f"| {t} | {r['signal']['playbook']} | {r['signal']['rr']:.2f} | {r['outcome']} | {r['r']:+.2f} | error | error |")
        else:
            print(f"| {t} | {r['signal']['playbook']} | {r['signal']['rr']:.2f} | {r['outcome']} | {r['r']:+.2f} | {r['p_current']:.3f} | {r['p_outcome']:.3f} |")
    print("\n```json\n" + json.dumps({"n": len(ok), "base_rate": round(float(win.mean()), 3)}) + "\n```")


if __name__ == "__main__":
    main()
