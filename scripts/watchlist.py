"""Build the day's hybrid watchlist: the fixed core plus up to 5 scanned outsiders, ranked by unusual option action.

    python3 scripts/watchlist.py --today YYYY-MM-DD [--new T1,T2,...] [--out DIR]

Scores every ticker with a chain snapshot dated --today in options/data/chains_swing, chains_premium and chains_watch
(the core is whatever the swing and premium runs pulled; outsiders are the scanned names saved to chains_watch). Each
ticker is compared only with its own earlier snapshots in the same folder. --new names the scanned outsiders so the board
tags them "new" (at most 5 are kept). Tickers with an open real-account position in research/desk_ledger.csv are tagged held (paper picks are not).
Writes OUTDIR/watchlist.csv (default research/watchlist/<today>/). Read-only: nothing here places an order.
"""
import argparse
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from options.watch import board, score  # noqa: E402

DIRS = [ROOT / "options/data/chains_swing", ROOT / "options/data/chains_premium", ROOT / "options/data/chains_watch"]
LEDGER = ROOT / "research/desk_ledger.csv"
MAX_NEW = 5
FIELDS = ["rank", "ticker", "source", "held", "liq", "busy", "signals", "action", "rel_volume", "vol_oi", "call_share",
          "iv_chg_pts", "spread_pct", "oi", "volume", "budget_call", "spot", "baseline_days", "asof"]


def snapshots(dirs=DIRS):
    """{(folder, ticker): [snapshot, ...] oldest first}."""
    out = {}
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            snap = json.loads(p.read_text())
            if snap.get("contracts") and snap.get("asof"):
                out.setdefault((d.name, snap["symbol"]), []).append(snap)
    for v in out.values():
        v.sort(key=lambda s: s["asof"])
    return out


def rows_for(today, snaps):
    """One scored row per ticker with a snapshot dated today, from the folder with the most contracts that day."""
    best = {}
    for (_, tic), series in snaps.items():
        todays = [s for s in series if s["asof"][:10] == today]
        if not todays:
            continue
        now = todays[-1]
        hist = [s for s in series if s["asof"][:10] < today]
        if tic not in best or len(now["contracts"]) > len(best[tic][0]["contracts"]):
            best[tic] = (now, hist)
    return [score(now, hist) for now, hist in best.values()]


def held_tickers(path=LEDGER):
    """Tickers with an open position in the owner's real account; paper books never count as held."""
    if not path.exists():
        return set()
    with open(path, newline="") as f:
        return {r["ticker"] for r in csv.DictReader(f) if r["status"] == "open" and r["book"] == "Real account"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", required=True)
    ap.add_argument("--new", default="")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    new = [t.strip().upper() for t in a.new.split(",") if t.strip()][:MAX_NEW]
    out = pathlib.Path(a.out) if a.out else ROOT / "research/watchlist" / a.today
    out.mkdir(parents=True, exist_ok=True)
    b = board(rows_for(a.today, snapshots()), held=held_tickers(), new=set(new))
    with open(out / "watchlist.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in b:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else ("" if v is None else v)) for k, v in r.items()})
    print(f"{out / 'watchlist.csv'}: {len(b)} liquid tickers ({sum(r['source'] == 'new' for r in b)} new)")
    for r in b[:10]:
        print(f"{r['rank']:>2} {r['ticker']:<5} {r['liq']} {r['source']:<4} {r['signals']:<40} {r['budget_call']}")


if __name__ == "__main__":
    main()
