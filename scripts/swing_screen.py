"""Run the daily swing buyer (research/swing-buyer/RULE.md): mark open picks, screen, log the day's pick.

    python3 scripts/swing_screen.py --chains DIR --bars DIR --earnings EARNINGS.json --out OUTDIR [--today YYYY-MM-DD]

- DIR (--chains): chain JSON files from scripts/rh_chain_from_transcript.py (calls, one 21-45 day expiry per ticker).
- DIR (--bars): daily bar CSVs (<TICKER>.csv).
- EARNINGS.json: {"TICKER": "YYYY-MM-DD"} next earnings dates (missing means none found).
Writes OUTDIR/swing_screen.csv, appends exits for open picks and at most one new pick to research/swing-buyer/picks.jsonl.
Paper only: nothing here places an order.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chart import append_jsonl, load_csv, read_jsonl  # noqa: E402
from options import chain_index  # noqa: E402
from options.swing import exit_check, open_picks, pick_expiry, rank, screen_call  # noqa: E402

PICKS = ROOT / "research/swing-buyer/picks.jsonl"
FIELDS = ["rank", "ticker", "status", "reason", "expiry", "dte", "strike", "ask", "bid", "delta", "oi", "cost",
          "breakeven", "breakeven_pct", "iv30", "rv20", "iv_rv", "mom20", "score", "spot", "earnings",
          "take_profit_at", "stop_at", "time_exit", "ticket", "asof"]


def mark(idx, today, picks_path=PICKS, write=True):
    """Exit lines for open picks whose rule is hit, from the newest snapshot of each pick's own expiry."""
    exits = []
    for p in open_picks(read_jsonl(picks_path)):
        hit = idx.get((p["ticker"], p["expiry"]))
        bid = None
        if hit:
            for c in hit[1].get("contracts", []):
                if c["type"] == "call" and abs(c["strike"] - p["strike"]) < 1e-6:
                    bid = c.get("bid")
        why = exit_check(p, bid, today)
        if why:
            exit_px = bid if bid is not None else 0.0
            exits.append({"close_of": p["id"], "date": today, "exit": exit_px,
                          "pnl": round((exit_px - p["ask"]) * 100, 2), "reason": why})
    if write and exits:
        append_jsonl(picks_path, *exits)
    return exits


PICK_FIELDS = ["id", "date", "ticker", "expiry", "strike", "ask", "cost", "breakeven", "take_profit_at", "stop_at",
               "time_exit", "status", "exit", "pnl", "reason", "ticket"]


def write_picks_csv(path, picks_path=PICKS):
    """One row per swing pick, open or closed, for the dashboard's Swing tab."""
    rows = read_jsonl(picks_path) if pathlib.Path(picks_path).exists() else []
    closes = {r["close_of"]: r for r in rows if r.get("close_of")}
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PICK_FIELDS, extrasaction="ignore")
        w.writeheader()
        for p in (r for r in rows if not r.get("close_of")):
            c = closes.get(p["id"], {})
            w.writerow({**p, "status": "closed" if c else "open", "exit": c.get("exit", ""), "pnl": c.get("pnl", ""),
                        "reason": c.get("reason", "")})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", required=True)
    ap.add_argument("--bars", required=True)
    ap.add_argument("--earnings", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args(argv)
    earnings = json.loads(pathlib.Path(a.earnings).read_text())
    idx = chain_index(a.chains)
    exits = mark(idx, a.today, write=not a.no_log)
    results = []
    for sym in sorted({s for s, _ in idx}):
        exp = pick_expiry([e for s, e in idx if s == sym], a.today)
        if not exp:
            continue
        path, chain = idx[(sym, exp)]
        bars = pathlib.Path(a.bars) / f"{sym}.csv"
        closes = [b.close for b in load_csv(bars) if b.ts[:10] <= a.today] if bars.exists() else []
        r = screen_call(sym, chain, closes, earnings.get(sym), a.today)
        if r["status"] == "pass":
            r["ticket"] = (f"BUY TO OPEN 1 {sym} {r['expiry']} {r['strike']:g} CALL · LIMIT {r['ask']:.2f} or better · "
                           f"DAY · cost ${r['cost']:.0f}")
        r["asof"] = chain.get("asof")
        results.append(r)
    ranked = rank(results)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "swing_screen.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in ranked:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else ("" if v is None else v)) for k, v in r.items()})
    held = {p["ticker"] for p in open_picks(read_jsonl(PICKS))}
    pick = next((r for r in ranked if r.get("rank") and r["ticker"] not in held), None)
    if pick and not a.no_log:
        append_jsonl(PICKS, {
            "id": f"{a.today}-{pick['ticker']}-{pick['strike']:g}C", "date": a.today, "logged_at": pick["asof"],
            "ticker": pick["ticker"], "expiry": pick["expiry"], "strike": pick["strike"], "type": "call",
            "ask": pick["ask"], "cost": pick["cost"], "delta": pick["delta"], "breakeven": pick["breakeven"],
            "iv_rv": round(pick["iv_rv"], 3), "mom20": round(pick["mom20"], 2), "ticket": pick["ticket"],
            "take_profit_at": pick["take_profit_at"], "stop_at": pick["stop_at"], "time_exit": pick["time_exit"],
            "mode": "paper"})
    write_picks_csv(out / "swing_picks.csv")
    for e in exits:
        print(f"EXIT {e['close_of']}: {e['reason']} · P&L ${e['pnl']:+.0f}")
    for r in ranked:
        print(f"{r.get('rank') or '-':>2} {r['ticker']:<5} {r['status']:<4} {r['strike'] or '':>6} ask {r['ask']} "
              f"IV/RV {r['iv_rv'] and round(r['iv_rv'], 2)} mom20 {r['mom20'] and round(r['mom20'], 1)} {r['reason']}")
    print("PICK:", pick["ticket"] if pick else "none")


if __name__ == "__main__":
    main()
