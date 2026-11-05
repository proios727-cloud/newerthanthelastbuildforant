"""Export the bot's state into the three JSON files the Regime Bot Desk dashboard reads.

Usage: python export_dashboard.py <decisions.jsonl> <paper.json> <out_dir>
Regime calls are scored with review.py's own realized_regime() on the next 12 Binance candles.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from binance import INTERVAL_MS, Binance
from config import Config
from features import arrays, atr
from review import H, fetch_range, realized_regime, r_of
from strategies import resolve


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(decisions: str, paper: str, out: str) -> None:
    cfg = Config.load()
    rows = [json.loads(x) for x in Path(decisions).read_text().splitlines() if x.strip()]
    state = json.loads(Path(paper).read_text())
    regimes = [r for r in rows if r["kind"] == "regime"]
    ms = INTERVAL_MS[cfg.interval]
    start = min((r["candle_t"] for r in regimes), default=int(time.time() * 1000)) - 60 * ms
    candles = fetch_range(Binance(cfg.binance_base), cfg, start, int(time.time() * 1000))
    idx = {c["t"]: i for i, c in enumerate(candles)}
    _, hh, ll, cc, _ = arrays(candles)
    atrs = atr(hh, ll, cc, cfg.atr_period)

    calls = []
    for r in regimes:
        i = idx.get(r["candle_t"])
        actual = None
        if i is not None and i + H < len(candles):
            actual = realized_regime(candles[i + 1:i + 1 + H], float(atrs[i]))
        pr = r["probs"]
        calls.append({"time": iso(r["candle_t"]), "close": r["candle"]["close"], "regime": r["regime"],
                      "p": round(r["p"], 4), "p_trending": round(pr.get("TRENDING", 0), 4),
                      "p_choppy": round(pr.get("CHOPPY", 0), 4), "p_panic": round(pr.get("PANIC", 0), 4),
                      "actual": actual, "correct": None if actual is None else int(actual == r["regime"]),
                      "q_version": r["q_version"], "adx": r["candle"].get("adx14"),
                      "tokens": (r.get("usage") or {}).get("input_tokens")})

    gates = {r["trade_id"]: r for r in rows if r["kind"] == "gate"}
    exits = {r["trade_id"]: r for r in rows if r["kind"] == "exit"}
    sigs = []
    for r in rows:
        if r["kind"] != "signal":
            continue
        s, g = r["signal"], gates.get(r["trade_id"], {})
        i = idx.get(r["candle_t"])
        outcome = resolve(s, candles[i + 1:i + 1 + 96]) if i is not None else "OPEN"
        e = exits.get(r["trade_id"])
        sigs.append({"time": iso(r["candle_t"]), "id": r["trade_id"], "playbook": s["playbook"], "side": s["side"],
                     "entry": round(s["entry"], 2), "stop": round(s["stop"], 2), "target": round(s["target"], 2),
                     "rr": round(s["rr"], 2), "regime": r["regime"], "take_p": round(r["take_p"], 4),
                     "book_control": r["book_control"], "entry_style": r["entry"], "decision": g.get("decision"),
                     "blocked_by": "; ".join(g.get("reasons") or []) or None, "outcome": outcome,
                     "replay_r": round(r_of(s, outcome), 2), "pnl": e["pnl"] if e else None})

    # Regime risk switch: three $10k paper portfolios replayed on the bot's real Drex calls (same code as the live core sleeve)
    from features import ema
    from risk_switch import CoreSleeve
    day_ms = 86_400_000
    dk = Binance(cfg.binance_base)._get("/api/v3/klines", symbol=cfg.symbol, interval="1d",
                                        startTime=(regimes[0]["candle_t"] if regimes else start) - 80 * day_ms, limit=1000)
    dts, dcl = np.array([k[0] for k in dk]), np.array([float(k[4]) for k in dk])
    e20, e50 = ema(dcl, 20), ema(dcl, 50)
    hold = CoreSleeve(None, cfg.starting_equity, cfg.fee_bps, cfg.slippage_bps)
    trend = CoreSleeve(None, cfg.starting_equity, cfg.fee_bps, cfg.slippage_bps, min_hold=96)
    core = CoreSleeve(None, cfg.starting_equity, cfg.fee_bps, cfg.slippage_bps, min_hold=96)
    block, compare = 0, []
    for n_, r in enumerate(regimes):
        px, t = r["candle"]["close"], r["candle_t"]
        j = int(np.searchsorted(dts, t - day_ms, side="right")) - 1  # last daily candle fully closed before t
        up = bool(e20[j] > e50[j]) if j >= 0 else False
        if n_ == 0:
            hold.step(px, {"TRENDING": 1.0}, True)
        p_panic = float(r["probs"].get("PANIC", 0))
        panic = p_panic >= cfg.panic_threshold
        block = cfg.core_cooloff if panic else max(0, block - 1)
        trend.step(px, {"TRENDING": 1.0} if up else {"CHOPPY": 0.0}, up)
        want = up and block == 0
        core.step(px, {"PANIC": 1.0} if panic else ({"TRENDING": 1.0} if want else {"CHOPPY": 0.0}), want, cfg.panic_threshold)
        compare.append({"time": iso(t), "close": px, "hold": round(hold.value(px), 2), "trend": round(trend.value(px), 2),
                        "switch": round(core.value(px), 2), "switch_exposure": core.s["exposure"],
                        "trend_exposure": trend.s["exposure"], "daily_uptrend": int(up), "p_panic": round(p_panic, 4)})

    pos = state.get("position")
    paper_rows = [{"equity": round(state["equity"], 2), "start_equity": cfg.starting_equity,
                   "closed_trades": state["closed_trades"], "open_position": pos["side"] if pos else "none",
                   "pending_order": "yes" if state.get("pending") else "no", "day_pnl": round(state["day_pnl"], 2),
                   "last_candle": iso(state["last_candle_t"]) if state.get("last_candle_t") else None,
                   "drex_errors": sum(r["kind"] == "drex_error" for r in rows),
                   "hands_off": sum(r["kind"] == "hands_off" for r in rows),
                   "shifts": sum(r["kind"] == "start" for r in rows),
                   "core_live_value": (state.get("core") or {}).get("value"),
                   "core_live_exposure": ((state.get("core") or {}).get("sleeve") or {}).get("exposure"),
                   "exported": iso(int(time.time() * 1000))}]

    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    for name, data in (("regime_calls", calls), ("signals", sigs), ("paper", paper_rows), ("switch_compare", compare)):
        (o / f"{name}.json").write_text(json.dumps(data))
    print(f"regime_calls {len(calls)} (scored {sum(c['actual'] is not None for c in calls)}), signals {len(sigs)}, paper 1, switch_compare {len(compare)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
