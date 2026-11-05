"""Go/no-go check for one logged Heat Seeker signal, run when its price alert fires. Decision support only: it prints an
order ticket for the user to place by hand and never places, previews or cancels anything.

    python3 scripts/heatseeker_check.py ID --bars DIR --bid B --ask A --buying-power BP [--now HH:MM] [--json]

DIR holds today's merged 15-minute bars for the signal's ticker and for the partner index (SPY <-> QQQ). Gates:
1. trigger    a completed bar in the signal's window met the trigger (the alert alone is only a touch)
2. rvol       relative volume at that bar meets the signal's rvol_min (Heat Seeker: 1.4)
   Gates 1-2 use chart.signals.first_trigger, the same scan the journal is scored with (default window 09:45-14:00).
3. alignment  the partner index is moving the same way on the day (above its open for a long, below for a short)
4. still on   the latest close is still on the right side of the stop and short of the target
5. time       now is inside the entry window: after 09:45, before the signal's `before`, and before 15:35
6. spread     the contract's bid/ask spread is at most 10% of mid
Sizing follows the playbook's standing rules: 2.5% of buying power per position, capped at $1,000; tier B is half size.
"""
import argparse
import datetime as dt
import json
import math
import pathlib
import sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chart import load_csv  # noqa: E402
from chart.intraday import interval_minutes, sessions as to_sessions  # noqa: E402
from chart.signals import DEFAULT_BEFORE, FIRST_ENTRY, _end_hm, first_trigger, load_journal  # noqa: E402

PARTNER = {"SPY": "QQQ", "QQQ": "SPY"}
RISK_PCT, RISK_CAP, LAST_ENTRY = 0.025, 1000.0, "15:35"


def check(signal, sessions, partner_sessions, bid, ask, buying_power, now):
    gates, date, side = [], signal["date"], signal["side"]
    sign = 1 if side == "long" else -1
    ivl = interval_minutes(sessions)
    done = [b for b in dict(sessions).get(date, []) if _end_hm(b, ivl) <= now]       # completed bars only
    trig = signal["trigger"]
    i, rv, fired = first_trigger(trig, done, sessions, date, ivl)
    hit = done[i if i is not None else fired] if fired is not None else None
    gates.append(("trigger", hit is not None,
                  f"{trig['kind'].replace('_', ' ')} {trig['level']:g}: " +
                  (f"met by the {hit.ts[11:16]} bar (close {hit.close:g})" if hit else "no completed bar has met it yet")))
    need = trig.get("rvol_min")
    gates.append(("rvol", hit is not None and (i is not None),
                  f"RVOL {rv:.2f} vs {need}" if rv is not None else "RVOL unavailable (needs 10 prior sessions)"))
    pday = dict(partner_sessions).get(date, [])
    pdone = [b for b in pday if _end_hm(b, ivl) <= now]
    if pdone:
        move = pdone[-1].close / pday[0].open - 1
        gates.append(("alignment", move * sign > 0, f"{PARTNER.get(signal['ticker'], 'index')} {move:+.2%} on the day"))
    else:
        gates.append(("alignment", False, "partner index bars unavailable"))
    last = done[-1].close if done else None
    stop, target = signal["stop"]["level"], signal.get("target")
    ok = last is not None and (last - stop) * sign > 0 and (target is None or (target - last) * sign > 0)
    gates.append(("still on", ok, f"last close {last} vs stop {stop:g}" + (f", target {target:g}" if target else "")))
    last_entry = min(trig.get("before", DEFAULT_BEFORE), LAST_ENTRY)
    gates.append(("time", FIRST_ENTRY <= now <= last_entry, f"now {now} ET; window {FIRST_ENTRY}-{last_entry}"))
    mid = (bid + ask) / 2 if bid is not None and ask else None
    spread = (ask - bid) / mid if mid else None
    gates.append(("spread", spread is not None and spread <= 0.10,
                  f"bid {bid} / ask {ask}, spread {spread:.1%} of mid" if spread is not None else "no quote"))
    go = all(g[1] for g in gates)
    budget = min(RISK_PCT * buying_power, RISK_CAP) * (0.5 if signal.get("tier") == "B" else 1.0)
    n = math.floor(budget / (ask * 100)) if ask else 0
    limit = round(mid + 0.01, 2) if mid else None
    action = "BUY TO OPEN"
    ticket = f"{action} {n} × {signal.get('contract', '?').split(',')[0]} · LIMIT {limit:.2f} · DAY" if n and limit else None
    return {"id": signal["id"], "verdict": "GO" if go else "NO-GO", "gates": gates, "budget": round(budget, 2),
            "contracts": n, "ticket": ticket if go else None, "stop": stop, "target": target}


def render(r):
    lines = [f"== {r['id']}: {r['verdict']} =="]
    lines += [f"  {'PASS' if ok else 'FAIL'}  {name:<9} {why}" for name, ok, why in r["gates"]]
    lines.append(f"  Size: {r['contracts']} contract(s) within a ${r['budget']:,.0f} risk budget")
    if r["ticket"]:
        lines.append(f"  Ticket (you place it): {r['ticket']}")
        lines.append(f"  Then: exit on the stop rule ({r['stop']:g}) or at the target ({r['target']}); flat by 15:45 ET.")
    else:
        lines.append("  No ticket: a gate failed. Re-check when the next 15-minute bar closes.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--journal", default=str(ROOT / "research/heatseeker/signals.jsonl"))
    ap.add_argument("--bars", default=str(ROOT / "chart/data/intraday/15m"))
    ap.add_argument("--bid", type=float, required=True)
    ap.add_argument("--ask", type=float, required=True)
    ap.add_argument("--buying-power", type=float, required=True)
    ap.add_argument("--now", default=dt.datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sig = next((s for s in load_journal(a.journal) if s["id"] == a.id), None)
    if sig is None or sig.get("side") not in ("long", "short"):
        raise SystemExit(f"{a.id}: no tradeable signal with that id in the journal")
    load = lambda t: to_sessions(load_csv(pathlib.Path(a.bars) / f"{t}.csv"))  # noqa: E731
    r = check(sig, load(sig["ticker"]), load(PARTNER.get(sig["ticker"], "SPY")), a.bid, a.ask, a.buying_power, a.now)
    print(json.dumps(r, indent=1) if a.json else render(r))


if __name__ == "__main__":
    main()
