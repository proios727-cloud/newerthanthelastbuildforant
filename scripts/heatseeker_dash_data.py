"""Write the Heat Seeker dashboard's three data files from the repository: today's levels, today's bars, scored signals.
    python3 scripts/heatseeker_dash_data.py OUTDIR --chains CHAIN.json [CHAIN.json ...] [--bars chart/data/intraday/15m]
`hs_levels.csv` runs gex_map.py on each chain (with and without same-day flow), `hs_today.csv` holds the chains' trading
day of 15-minute bars, and `hs_signals.csv` is research/heatseeker/signals.jsonl scored by chart/signals.py.
"""
import csv
import json
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chart import load_csv  # noqa: E402
from chart.signals import score_journal  # noqa: E402

GEX_MAP = pathlib.Path.home() / ".claude/skills/synced"


def find_gex_map():
    hits = sorted(GEX_MAP.glob("*/gex-vex-heatseeker/scripts/gex_map.py"))
    if not hits:
        raise SystemExit("gex_map.py not found: the gex-vex-heatseeker skill must be installed")
    return hits[0]


def levels(chain_path, gex):
    plain = json.loads(subprocess.check_output([sys.executable, str(gex), str(chain_path), "--json"]))
    flow = json.loads(subprocess.check_output([sys.executable, str(gex), str(chain_path), "--json", "--flow-adjust"]))
    f0, f1 = plain["nearest_flip"], flow["nearest_flip"]
    drift = abs(f1 - f0) / f0 * 100 if f0 and f1 else None
    asof = dt.datetime.fromisoformat(plain["asof"][:19] + "+00:00").astimezone(ZoneInfo("America/New_York"))
    return {"ticker": plain["symbol"], "date": asof.date().isoformat(), "asof_et": asof.strftime("%H:%M"),
            "spot": plain["spot"], "flip": f0, "flip_flow": f1, "drift_pct": round(drift, 2) if drift is not None else "",
            "confidence": "stable" if drift is not None and drift < 0.15 else "contested",
            "regime": "+GEX" if plain["regime"] == "positive" else "-GEX", "vanna": plain["vanna_alignment"],
            "king": plain["king_node"], "call_wall": plain["call_wall"], "put_wall": plain["put_wall"],
            "net_gex_musd": round(plain["net_gex"] / 1e6, 1),
            "air_pockets": "; ".join(f"{p['low']:g}-{p['high']:g}" for p in plain["air_pockets"]
                                     if isinstance(p, dict) and "low" in p)}


def main(argv):
    out = pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    chains = []
    for c in argv[argv.index("--chains") + 1:]:
        if c.startswith("--"):
            break
        chains.append(c)
    bars_dir = argv[argv.index("--bars") + 1] if "--bars" in argv else str(ROOT / "chart/data/intraday/15m")
    gex = find_gex_map()
    lv = [levels(c, gex) for c in chains]
    with open(out / "hs_levels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lv[0]))
        w.writeheader()
        w.writerows(lv)
    today = []
    for row in lv:
        p = pathlib.Path(bars_dir) / f"{row['ticker']}.csv"
        for b in load_csv(p) if p.exists() else []:
            if b.ts[:10] == row["date"]:
                today.append({"ticker": row["ticker"], "time": b.ts[11:16], "open": b.open, "high": b.high,
                              "low": b.low, "close": b.close, "volume": int(b.volume)})
    with open(out / "hs_today.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "time", "open", "high", "low", "close", "volume"])
        w.writeheader()
        w.writerows(today)
    res = score_journal(ROOT / "research/heatseeker/signals.jsonl", bars_dir)
    with open(out / "hs_signals.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0]))
        w.writeheader()
        w.writerows({k: ("" if v is None else round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}
                    for r in res)
    print(f"{out}: {len(lv)} level rows, {len(today)} bars, {len(res)} signals")


if __name__ == "__main__":
    main(sys.argv)
