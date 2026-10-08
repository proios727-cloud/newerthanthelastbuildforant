"""Snapshot + CLI for the GEX/Flow discovery board.

  python -m options.gex_board SPY,QQQ            # collect, snapshot, build board
  python -m options.gex_board --refresh-only    # snapshot only (board via scripts/)
"""
import argparse
import json
import pathlib
import sys

from fund import clock
from fund.config import ROOT

from . import gex_by_strike, gex_map, regime
from .collector import collect, rvol_5m, gap_pct, save_chain
from .flow import contract_flows, premium_split
from .setup_scan import scan

SNAPSHOT = ROOT / "data" / "gex_snapshot.json"


def build_symbol(symbol, now_et):
    chain = collect(symbol, now_et=now_et)
    save_chain(chain)
    m = gex_map(chain)
    by_strike = gex_by_strike(chain)
    strikes = sorted(by_strike)
    bars = [{"strike": s, "call": by_strike[s][0], "put": by_strike[s][1]} for s in strikes]
    rvol, rvol_note = rvol_5m(symbol)
    gap = gap_pct(symbol)
    flows = [vars(f) for f in (contract_flows(chain) or [])[:12]]
    prem = premium_split(chain)
    setups = [{"setup": s.setup, "state": s.state, "reason": s.reason}
              for s in scan(chain, m, rvol=rvol, gap=gap)]
    return {
        "spot": chain["spot"],
        "net_gex": m.net,
        "regime": regime(m),
        "walls": {"king": m.king, "call_wall": m.call_wall,
                  "put_wall": m.put_wall, "flip": m.flip},
        "rvol": rvol, "rvol_note": rvol_note,
        "gap_pct": gap,
        "bars": bars,
        "premium": prem,
        "flows": flows,
        "setups": setups,
        "note": f'{len(chain["contracts"])} contracts; {chain["source"]}',
    }


def snapshot(symbols):
    now = clock.now()
    now_et = clock.to_et(now)
    snap = {"captured_at": now_et.isoformat(), "symbols": {}}
    for sym in symbols:
        try:
            snap["symbols"][sym] = build_symbol(sym, now_et)
        except Exception as e:  # one dead symbol must not kill the board
            snap["symbols"][sym] = {
                "spot": 0, "net_gex": 0, "regime": "error", "walls": {},
                "rvol": None, "rvol_note": "", "gap_pct": None,
                "bars": [], "premium": {}, "flows": [], "setups": [],
                "note": f"collection failed: {str(e)[:120]}",
            }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m options.gex_board")
    ap.add_argument("symbols", nargs="?", default="SPY,QQQ")
    ap.add_argument("--refresh-only", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "gex_board.html"))
    a = ap.parse_args(argv)
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    snap = snapshot(syms)
    for sym, s in snap["symbols"].items():
        if s.get("regime") == "error":
            print(f"{sym}: ERROR - {s['note']}", file=sys.stderr)
        else:
            print(f"{sym}: net GEX {s['net_gex']/1e9:.2f}B/1%, {s['regime']}, "
                  f"flip {s['walls'].get('flip')}, {len(s['flows'])} discovery flows")
    if a.refresh_only:
        return
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_gex_board.py"),
                    "--snapshot", str(SNAPSHOT), "--out", a.out], check=True)


if __name__ == "__main__":
    main()