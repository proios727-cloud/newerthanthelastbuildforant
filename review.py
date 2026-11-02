"""Step 8: nightly review of the decision log.

- Scores every regime call against what the market actually did next (calibration, Brier).
- Replays every signal (taken AND skipped) to see whether TAKE/SKIP was right.
- Retunes take/regime thresholds within bounded steps (auto_tune), written to state/tuned.json.
- Writes reports/review-<date>.md plus a packet of the worst misses, which the nightly
  Claude session uses to rewrite questions.json (version bump) — the "sharpen the questions" loop.

Usage: python review.py [--hours 24] [--no-tune]
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

from binance import INTERVAL_MS, Binance
from config import ROOT, STATE_DIR, Config
from features import arrays, atr
from journal import Journal, read, verify
from strategies import resolve

REPORTS = STATE_DIR / "reports"
H = 12  # candles ahead used to label the realized regime


def fetch_range(bx: Binance, cfg, start_ms: int, end_ms: int) -> list[dict]:
    out, t = [], start_ms
    while t < end_ms:
        raw = bx._get("/api/v3/klines", symbol=cfg.symbol, interval=cfg.interval, startTime=t, limit=1000)
        if not raw:
            break
        out += [{"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]),
                 "v": float(k[5]), "close_time": k[6]} for k in raw]
        t = raw[-1][0] + 1
    now = int(time.time() * 1000)
    return [c for c in out if c["close_time"] < now]


def realized_regime(path: list[dict], atr_now: float) -> str:
    _, h, l, c, _ = arrays(path)
    c0 = path[0]["o"]
    net = abs(c[-1] - c0)
    travel = np.abs(np.diff(np.concatenate([[c0], c]))).sum()
    excursion = max(h.max() - c0, c0 - l.min())
    if excursion >= 4 * atr_now or (h - l).max() >= 3 * atr_now:
        return "PANIC"
    if net >= 2 * atr_now and net / max(travel, 1e-9) >= 0.35:
        return "TRENDING"
    return "CHOPPY"


def r_of(sig: dict, outcome: str) -> float:
    return {"TARGET": abs(sig["target"] - sig["entry"]) / abs(sig["entry"] - sig["stop"]), "STOP": -1.0}.get(outcome, 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24 * 7, help="look-back window for scoring")
    ap.add_argument("--no-tune", action="store_true")
    a = ap.parse_args()
    cfg = Config.load()
    jpath = STATE_DIR / "decisions.jsonl"
    ok, n = verify(jpath)
    rows = read(jpath)
    since = int(time.time() * 1000) - int(a.hours * 3_600_000)
    rows = [r for r in rows if r.get("candle_t", r["ts"]) >= since]
    regimes = [r for r in rows if r["kind"] == "regime"]
    signals = {r["trade_id"]: r for r in rows if r["kind"] == "signal"}
    gates = {r["trade_id"]: r for r in rows if r["kind"] == "gate"}
    exits = [r for r in rows if r["kind"] == "exit"]
    errors = Counter(r["stage"] for r in rows if r["kind"] == "drex_error")

    ms = INTERVAL_MS[cfg.interval]
    bx = Binance(cfg.binance_base)
    candles = fetch_range(bx, cfg, since - 60 * ms, int(time.time() * 1000)) if rows else []
    idx = {c["t"]: i for i, c in enumerate(candles)}
    _, hh, ll, cc, _ = arrays(candles) if candles else (None,) * 5
    atrs = atr(hh, ll, cc, cfg.atr_period) if candles else []

    # --- regime scoring
    labels = ["TRENDING", "CHOPPY", "PANIC"]
    conf, brier, scored, misses = defaultdict(Counter), [], 0, []
    for r in regimes:
        i = idx.get(r["candle_t"])
        if i is None or i + H >= len(candles):
            continue
        truth = realized_regime(candles[i + 1:i + 1 + H], float(atrs[i]))
        conf[r["regime"]][truth] += 1
        brier.append(sum((r["probs"].get(lb, 0) - (lb == truth)) ** 2 for lb in labels))
        scored += 1
        if r["regime"] != truth:
            misses.append({"candle_t": r["candle_t"], "called": r["regime"], "p": r["p"], "actual": truth,
                           "q_version": r["q_version"], "snapshot": r["snapshot"], "candle": r["candle"], "book": r["book"]})
    acc = sum(conf[x][x] for x in labels) / scored if scored else None

    # --- signal replay (taken and skipped alike)
    sig_rows = []
    for tid, s in signals.items():
        i = idx.get(s["candle_t"])
        if i is None:
            continue
        out = resolve(s["signal"], candles[i + 1:i + 1 + 96])
        g = gates.get(tid, {})
        sig_rows.append({"trade_id": tid, "take_p": s["take_p"], "regime_p": s["regime_p"], "playbook": s["signal"]["playbook"],
                         "decision": g.get("decision"), "entry": s["entry"], "outcome": out, "r": r_of(s["signal"], out),
                         "book_control": s["book_control"]})
    done = [x for x in sig_rows if x["outcome"] != "OPEN"]
    by_dec = defaultdict(list)
    for x in done:
        by_dec[x["decision"]].append(x["r"])

    # --- threshold sweep on TAKE probability (counterfactual R across all resolved signals)
    sweep, tuned = [], {}
    for th in np.round(np.arange(0.40, 0.91, 0.05), 2):
        sel = [x["r"] for x in done if x["take_p"] >= th]
        sweep.append({"th": float(th), "n": len(sel), "total_r": round(sum(sel), 2), "avg_r": round(np.mean(sel), 3) if sel else None})
    eligible = [s for s in sweep if s["n"] >= max(5, cfg.tune_min_samples // 3)]
    if cfg.auto_tune and not a.no_tune and len(done) >= cfg.tune_min_samples and eligible:
        best = max(eligible, key=lambda s: s["total_r"])["th"]
        step = float(np.clip(best - cfg.take_threshold, -cfg.tune_max_step, cfg.tune_max_step))
        if abs(step) >= 0.01:
            tuned["take_threshold"] = round(cfg.take_threshold + step, 3)
    if tuned:
        tp = STATE_DIR / "tuned.json"
        cur = json.loads(tp.read_text()) if tp.exists() else {}
        cur.update(tuned)
        tp.write_text(json.dumps(cur, indent=2))
        Journal(jpath).log("tune", changes=tuned, basis={"resolved_signals": len(done)})

    # --- realized paper PnL
    pnl = sum(e["pnl"] for e in exits)
    wins = sum(e["pnl"] > 0 for e in exits)
    by_entry = defaultdict(list)
    for e in exits:
        s = signals.get(e["trade_id"])
        by_entry[s["entry"] if s else "?"].append(e["r_multiple"])

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    REPORTS.mkdir(parents=True, exist_ok=True)
    md = [f"# Review {day}  ({cfg.symbol} {cfg.interval}, last {a.hours:.0f}h)", "",
          f"- Log integrity: {'OK' if ok else 'BROKEN at line ' + str(n)} ({n} records)",
          f"- Drex errors: {dict(errors) or 'none'}",
          f"- Paper P&L (closed): {pnl:+.2f} over {len(exits)} trades, win rate {wins / len(exits):.0%}" if exits else "- No closed trades",
          "", "## Regime calls vs realized (next 12 candles)",
          f"Scored {scored}; accuracy {acc:.1%}; mean Brier {np.mean(brier):.3f} (lower is better, 0.667 = uniform)" if scored else "Not enough candles yet",
          "", "| called \\ actual | " + " | ".join(labels) + " |", "|---|---|---|---|"]
    md += [f"| {c} | " + " | ".join(str(conf[c][t]) for t in labels) + " |" for c in labels]
    md += ["", "## TAKE / SKIP replay (resolved signals)", "| decision | n | avg R | total R |", "|---|---|---|---|"]
    md += [f"| {d} | {len(v)} | {np.mean(v):+.2f} | {sum(v):+.2f} |" for d, v in by_dec.items()]
    md += ["", "## TAKE threshold sweep", "| p ≥ | n | avg R | total R |", "|---|---|---|---|"]
    md += [f"| {s['th']:.2f} | {s['n']} | {s['avg_r'] if s['avg_r'] is not None else '—'} | {s['total_r']} |" for s in sweep]
    md += ["", "## Realized R by entry type", "| entry | n | avg R |", "|---|---|---|"]
    md += [f"| {k} | {len(v)} | {np.mean(v):+.2f} |" for k, v in by_entry.items()]
    md += ["", f"## Threshold changes: {tuned or 'none'} (current take {cfg.take_threshold}, regime {cfg.regime_threshold})",
           "", f"## Question version in use: {json.loads((ROOT / 'questions.json').read_text())['version']}",
           f"Worst regime misses written to review-{day}-packet.json for question rewriting."]
    (REPORTS / f"review-{day}.md").write_text("\n".join(md) + "\n")
    misses.sort(key=lambda m: -m["p"])
    wrong_takes = [x for x in sig_rows if x["decision"] == "TAKE" and x["outcome"] == "STOP"]
    wrong_skips = [x for x in sig_rows if x["decision"] == "SKIP" and x["outcome"] == "TARGET"]
    (REPORTS / f"review-{day}-packet.json").write_text(json.dumps(
        {"confident_regime_misses": misses[:15], "takes_that_stopped": wrong_takes[:15],
         "skips_that_would_have_won": wrong_skips[:15], "confusion": {k: dict(v) for k, v in conf.items()}}, indent=2, default=str))
    print("\n".join(md))


if __name__ == "__main__":
    main()
