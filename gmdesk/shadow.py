"""Stage 4: live shadow. Same Quoter as the replay, fed by live Kalshi trades. Never places orders.

    python -m gmdesk.shadow run --series KXETH15M --minutes 120 --log data/gm/shadow_KXETH15M.jsonl
    python -m gmdesk.shadow report data/gm/shadow_KXETH15M.jsonl --replay data/gm/replay_KXETH15M.json

The model (VPIN cuts, adverse cost per quintile, stop time, warn/halt, tuned spread) is read from the
stage-3 replay report, so shadow quotes exactly what was backtested. VPIN is warmed on the backfill.
Gate 4: shadow markout per filled contract and fills per market land inside the replay's range.
"""
import argparse
import json
import os
import sys
import time

from kalshi.calibration import throttled
from kalshi.feed import open_markets
from .analyze import load
from .core import VPIN
from .record import market_trades, norm_trade, ts_of
from .replay import Quoter


def load_model(path, gm=True):
    with open(path) as f:
        rep = json.load(f)
    cfg = rep["config"]["gm_as" if gm else "pure_as"]
    return rep["model"], cfg, rep


def warm_vpin(model, folder, last_n=10):
    v = VPIN(model["bucket"], model["n"])
    if os.path.isdir(folder):
        for m in load(folder)[-last_n:]:
            for r in m["trades"]:
                v.push(r["q"], r["s"])
    return v


def emit(log, rec):
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def run(series, minutes, log, model, cfg, vpin, fetch=None, clock=time.time, sleep=time.sleep, poll_s=2.0):
    fetch = fetch or throttled(delay=0.05)
    end, active, seen, pending = clock() + minutes * 60, {}, set(), {}
    while clock() < end:
        now = clock()
        for m in open_markets(series, fetch):
            t, close = m["ticker"], ts_of(m["close_time"])
            if t not in active and close > now:
                active[t] = {"q": Quoter(close, model, cfg, True, vpin), "since": now - 5}
                emit(log, {"ts": now, "ev": "open", "ticker": t, "close_ts": close})
        for t, st in list(active.items()):
            qt = st["q"]
            new = [x for x in market_trades(t, fetch, min_ts=st["since"]) if x["trade_id"] not in seen]
            for x in sorted(new, key=lambda x: x["created_time"]):
                seen.add(x["trade_id"])
                r = norm_trade(x, series)
                before = qt.quote
                qt.requote(r["ts"])
                if qt.quote != before:
                    emit(log, {"ts": r["ts"], "ev": "quote", "ticker": t, "status": qt.status,
                               "bid": qt.quote and qt.quote[0], "ask": qt.quote and qt.quote[1],
                               "vpin": vpin.value, "inv": qt.bk.inv})
                f = qt.on_trade(r)
                if f:
                    emit(log, {"ts": r["ts"], "ev": "fill", "ticker": t, **f, "inv": qt.bk.inv})
                st["since"] = max(st["since"], r["ts"] - 5)
            if clock() > qt.close_ts + 5:
                pending[t] = active.pop(t)["q"]
        for t, qt in list(pending.items()):
            m = fetch(f"/markets/{t}").get("market", {})
            if m.get("result") in ("yes", "no"):
                emit(log, {"ts": clock(), "ev": "settle", "ticker": t, "result": m["result"],
                           **qt.settle(1.0 if m["result"] == "yes" else 0.0)})
                pending.pop(t)
        sleep(poll_s)
    emit(log, {"ts": clock(), "ev": "stop", "unsettled": list(pending)})


def report(path, replay=None):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    S = [json.loads(l) for l in lines if '"settle"' in l]
    F = [json.loads(l) for l in lines if '"fill"' in l]
    if not S:
        return {"markets": 0, "note": "no settled markets yet"}
    pnl = sum(s["pnl"] for s in S)
    ct = sum(s["contracts"] for s in S)
    out = {"markets": len(S), "fills": len(F), "contracts": ct, "pnl": round(pnl, 2),
           "pnl_per_contract_c": round(100 * pnl / ct, 3) if ct else None,
           "fills_per_market": round(len(F) / len(S), 2)}
    if replay:
        with open(replay) as f:
            g = json.load(f)["gm_as"]
        exp_pc = 100 * g["total_pnl"] / max(g["contracts"], 1)
        exp_fpm = g["fills"] / max(g["markets"], 1)
        out["replay"] = {"pnl_per_contract_c": round(exp_pc, 3), "fills_per_market": round(exp_fpm, 2)}
        ok_fill = exp_fpm * 0.5 <= out["fills_per_market"] <= exp_fpm * 1.5
        ok_mo = out["pnl_per_contract_c"] is not None and out["pnl_per_contract_c"] >= exp_pc - abs(exp_pc) * 0.5 - 0.5
        out["gate4"] = {"pass": len(S) >= 20 and ok_fill and ok_mo,
                        "rule": ">=20 settled markets, fills/market within 50% of replay, P&L/contract no worse than replay by >50% (+0.5c)"}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--series", default="KXETH15M"); r.add_argument("--minutes", type=float, default=60)
    r.add_argument("--data", default="data/gm"); r.add_argument("--log")
    p = sp.add_parser("report"); p.add_argument("log"); p.add_argument("--replay")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        print(json.dumps(report(a.log, a.replay), indent=2))
        return 0
    rp = os.path.join(a.data, f"replay_{a.series}.json")
    if not os.path.exists(rp):
        print(f"no stage-3 model at {rp}; run gmdesk.replay first", file=sys.stderr)
        return 2
    model, cfg, _ = load_model(rp)
    vpin = warm_vpin(model, os.path.join(a.data, a.series))
    try:
        run(a.series, a.minutes, a.log or os.path.join(a.data, f"shadow_{a.series}.jsonl"), model, cfg, vpin)
    except OSError as e:
        print(f"Kalshi unreachable: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
