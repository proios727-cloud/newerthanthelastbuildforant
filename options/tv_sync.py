"""Premarket sync: GEX snapshot -> TradingView Pine inputs.

One command prints the exact values to paste into heatseeker_strategy.pine's
"GEX map" input group and writes tv_levels.json for the ledger/bridge:

  python -m options.tv_sync SPY,QQQ
  python -m options.tv_sync --snapshot data/gex_snapshot.json

Honesty: levels are as fresh as the snapshot. The Pine flags STALE after 36h;
the bridge stamps every row with the map's as-of time.
"""
import argparse
import json
import pathlib

from fund.config import ROOT

from .collector import collect, rvol_5m
from . import gex_map
from .setup_scan import _find_pocket, net_by_strike

SNAPSHOT = ROOT / "data" / "gex_snapshot.json"
TV_LEVELS = ROOT / "data" / "tv_levels.json"

VANNA_PLACEHOLDER = "aligned"  # vanna axis not computed yet; skill default


def levels_for_symbol(sym, snap_sym):
    walls = snap_sym.get("walls") or {}
    spot = snap_sym.get("spot")
    # Spot-correct OTM walls: the engine's gex_map picks max/min over ALL strikes
    # (its documented convention), but the heatseeker walls are directional -
    # the biggest call gamma ABOVE spot, the biggest put gamma BELOW it.
    call_wall, put_wall = walls.get("call_wall"), walls.get("put_wall")
    bars = snap_sym.get("bars") or []
    if spot and bars:
        above = {b["strike"]: b["call"] for b in bars if b["strike"] > spot and b["call"] > 0}
        below = {b["strike"]: -b["put"] for b in bars if b["strike"] < spot and b["put"] < 0}
        if above:
            call_wall = max(above, key=above.get)
        if below:
            put_wall = max(below, key=below.get)
    # air pocket from the bars if the setup scan found one
    pocket_lo = pocket_hi = None
    for st in snap_sym.get("setups") or []:
        if st["setup"] == "air_pocket" and st["state"] in ("WATCH", "ARMED"):
            import re
            m = re.search(r"([0-9.]+)\D+([0-9.]+)", st.get("reason", ""))
            if m:
                pocket_lo, pocket_hi = float(m.group(1)), float(m.group(2))
    return {
        "symbol": sym,
        "as_of": None,  # filled by build()
        "spot": spot,
        "flip": walls.get("flip"),
        "call_wall": call_wall,
        "put_wall": put_wall,
        "king": walls.get("king"),
        "pocket_lo": pocket_lo,
        "pocket_hi": pocket_hi,
        "vanna": VANNA_PLACEHOLDER,
        "source": "gex_board snapshot",
    }


def build(symbols, snapshot_path=SNAPSHOT):
    snap = json.loads(pathlib.Path(snapshot_path).read_text(encoding="utf-8"))
    captured = snap.get("captured_at", "")
    out = {}
    for sym in symbols:
        s = snap["symbols"].get(sym) or snap["symbols"].get(sym.upper())
        if not s or s.get("regime") == "error" or not s.get("spot"):
            continue
        lv = levels_for_symbol(sym, s)
        lv["as_of"] = captured
        out[sym] = lv
    return {"captured_at": captured, "symbols": out}


def render_paste_block(levels):
    sym = levels["symbol"]
    lines = [
        f"== {sym} - paste into heatseeker_strategy.pine 'GEX map' group ==",
        f"Levels as-of date: {levels['as_of'][:10] if levels['as_of'] else 'today'}",
        f"Gamma flip:        {levels['flip'] or 0.0}",
        f"Call wall:          {levels['call_wall'] or 0.0}",
        f"Put wall:           {levels['put_wall'] or 0.0}",
        f"King node:          {levels['king'] or 0.0}",
        f"Air pocket low:     {levels['pocket_lo'] or 0.0}",
        f"Air pocket high:    {levels['pocket_hi'] or 0.0}",
        f"Vanna:              {levels['vanna']}  (axis not computed; skill default)",
        f"Map source:         vendor  (levels from our gex_board snapshot)",
        "",
        f"spot at capture: {levels['spot']} | {levels['source']}",
    ]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m options.tv_sync")
    ap.add_argument("symbols", nargs="?", default="SPY,QQQ")
    ap.add_argument("--snapshot", default=str(SNAPSHOT))
    a = ap.parse_args(argv)
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    data = build(syms, a.snapshot)
    if not data["symbols"]:
        raise SystemExit("no symbols in snapshot - run options.gex_board first")
    TV_LEVELS.parent.mkdir(parents=True, exist_ok=True)
    TV_LEVELS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for sym, lv in data["symbols"].items():
        print(render_paste_block(lv))
    print(f"\nwrote {TV_LEVELS}")


if __name__ == "__main__":
    main()