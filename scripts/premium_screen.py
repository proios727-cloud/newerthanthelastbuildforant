"""Run the daily premium-selling screener (research/premium-screener/RULE.md) and log the top picks.

    python3 scripts/premium_screen.py --chains DIR --bars DIR --earnings EARNINGS.json --out OUTDIR [--today YYYY-MM-DD]

- DIR (--chains): chain JSON files, one per ticker, from scripts/rh_chain_from_transcript.py (30-45 day expiry).
- DIR (--bars): daily bar CSVs (<TICKER>.csv), e.g. from scripts/tv_ohlcv_to_csv.py --all-hours.
- EARNINGS.json: {"AAPL": "2026-01-29", ...}, the next earnings date per ticker (missing means none found).
Writes OUTDIR/premium_screen.csv (every ticker, ranked, with the failed filter) and appends the top 5 to
research/premium-screener/picks.jsonl unless a pick for the same ticker and expiry is already open.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chart import load_csv  # noqa: E402
from options.premium import rank, screen  # noqa: E402

PICKS = ROOT / "research/premium-screener/picks.jsonl"


def latest_chains(folder):
    best = {}
    for p in sorted(pathlib.Path(folder).glob("*.json")):
        c = json.loads(p.read_text())
        best[c["symbol"]] = (p, c)                         # sorted by name, so the latest snapshot wins
    return best


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
    results = []
    for sym, (path, chain) in sorted(latest_chains(a.chains).items()):
        bars_path = pathlib.Path(a.bars) / f"{sym}.csv"
        closes = [b.close for b in load_csv(bars_path) if b.ts[:10] <= a.today] if bars_path.exists() else []
        r = screen(sym, chain, closes, earnings.get(sym), a.today)
        r["chain_file"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        r["asof"] = chain.get("asof")
        results.append(r)
    ranked = rank(results)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fields = ["rank", "ticker", "status", "reason", "structure", "legs", "expiry", "dte", "credit", "width", "max_loss",
              "return_on_risk", "pop", "iv30", "rv20", "iv_rv", "trend", "score", "spot", "earnings", "asof"]
    with open(out / "premium_screen.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in ranked:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else ("" if v is None else v))
                        for k, v in r.items()})
    if not a.no_log:
        open_keys = set()
        if PICKS.exists():
            for line in PICKS.read_text().splitlines():
                if line.strip():
                    p = json.loads(line)
                    if not p.get("closed"):
                        open_keys.add((p["ticker"], p["expiry"]))
        with open(PICKS, "a") as f:
            for r in ranked:
                if r.get("rank") and (r["ticker"], r["expiry"]) not in open_keys:
                    f.write(json.dumps({"id": f"{a.today}-{r['ticker']}", "date": a.today, "logged_at": r["asof"],
                                        "ticker": r["ticker"], "structure": r["structure"], "legs": r["legs"],
                                        "expiry": r["expiry"], "credit": r["credit"], "width": r["width"],
                                        "max_loss": r["max_loss"], "pop": r["pop"], "iv_rv": round(r["iv_rv"], 3),
                                        "rank": r["rank"], "exit_rules": "take 50% of credit; stop at 2x credit; "
                                        "close at 21 DTE; never hold through earnings", "closed": None}) + "\n")
    for r in ranked:
        print(f"{r.get('rank') or '-':>2} {r['ticker']:<5} {r['status']:<4} {r['structure'] or '':<18} "
              f"{r['legs'] or '':<38} cr {r['credit']} IV/RV {r['iv_rv'] and round(r['iv_rv'], 2)} {r['reason']}")


if __name__ == "__main__":
    main()
