"""Run the daily premium-selling screener (research/premium-screener/RULE.md) and log the top picks.

    python3 scripts/premium_screen.py --chains DIR --bars DIR --earnings EARNINGS.json --out OUTDIR [--today YYYY-MM-DD]

- DIR (--chains): chain JSON files, one per ticker, from scripts/rh_chain_from_transcript.py (30-45 day expiry).
- DIR (--bars): daily bar CSVs (<TICKER>.csv), e.g. from scripts/tv_ohlcv_to_csv.py --all-hours.
- EARNINGS.json: {"AAPL": "2026-01-29", ...}, the next earnings date per ticker (missing means none found).
Writes OUTDIR/premium_screen.csv (every ticker, ranked, with the failed filter) and appends the top 5 to
research/premium-screener/picks.jsonl unless a pick for the same ticker and expiry is already open. Each ticker is screened
on its newest snapshot of the earliest expiry 30-45 days out (options.chain_index, options.premium.pick_expiry).
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
from options.premium import open_picks, pick_expiry, rank, screen, screen_put  # noqa: E402

PICKS = ROOT / "research/premium-screener/picks.jsonl"


def chains_to_screen(folder, today):
    """{symbol: (path, chain)}: each symbol's rule expiry, from its newest snapshot of that expiry."""
    idx = chain_index(folder)
    out = {}
    for sym in sorted({s for s, _ in idx}):
        exp = pick_expiry([e for s, e in idx if s == sym], today)
        out[sym] = idx[(sym, exp)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", required=True)
    ap.add_argument("--bars", required=True)
    ap.add_argument("--earnings", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--no-log", action="store_true")
    ap.add_argument("--mode", choices=("put", "spread"), default="put",
                    help="put: single-leg cash-secured puts (RULE.md amendment 2, default); spread: the original rule")
    a = ap.parse_args(argv)
    earnings = json.loads(pathlib.Path(a.earnings).read_text())
    results = []
    for sym, (path, chain) in chains_to_screen(a.chains, a.today).items():
        bars_path = pathlib.Path(a.bars) / f"{sym}.csv"
        closes = [b.close for b in load_csv(bars_path) if b.ts[:10] <= a.today] if bars_path.exists() else []
        r = (screen_put if a.mode == "put" else screen)(sym, chain, closes, earnings.get(sym), a.today)
        if r["status"] == "pass" and a.mode == "put":
            r["ticket"] = (f"SELL TO OPEN 1 {sym} {r['expiry']} {r['strike']:g} PUT · LIMIT {r['credit']:.2f} or better · GTC · "
                           f"cash secured ${r['cash_needed']:,}")
        r["chain_file"] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        r["asof"] = chain.get("asof")
        results.append(r)
    ranked = rank(results)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fields = (["rank", "ticker", "status", "reason", "structure", "legs", "expiry", "dte", "credit", "cash_needed",
               "breakeven", "return_on_cash", "annualized", "pop", "iv30", "rv20", "iv_rv", "trend", "score", "spot",
               "earnings", "ticket", "asof"] if a.mode == "put" else
              ["rank", "ticker", "status", "reason", "structure", "legs", "expiry", "dte", "credit", "width", "max_loss",
               "return_on_risk", "pop", "iv30", "rv20", "iv_rv", "trend", "score", "spot", "earnings", "asof"])
    with open(out / "premium_screen.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in ranked:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else ("" if v is None else v))
                        for k, v in r.items()})
    if not a.no_log:
        held = {(p["ticker"], p["expiry"]) for p in open_picks(read_jsonl(PICKS))}
        append_jsonl(PICKS, *[
            {"id": f"{a.today}-{r['ticker']}", "date": a.today, "logged_at": r["asof"], "ticker": r["ticker"],
             "structure": r["structure"], "legs": r["legs"], "expiry": r["expiry"], "credit": r["credit"],
             "width": r.get("width"), "max_loss": r.get("max_loss") or r.get("breakeven"),
             "cash_needed": r.get("cash_needed"), "breakeven": r.get("breakeven"), "ticket": r.get("ticket"),
             "mode": "paper", "pop": r["pop"], "iv_rv": round(r["iv_rv"], 3), "rank": r["rank"],
             "exit_rules": "take 50% of credit; stop at 2x credit; close at 21 DTE; never hold through earnings"}
            for r in ranked if r.get("rank") and (r["ticker"], r["expiry"]) not in held])
    for r in ranked:
        print(f"{r.get('rank') or '-':>2} {r['ticker']:<5} {r['status']:<4} {r['structure'] or '':<18} "
              f"{r['legs'] or '':<38} cr {r['credit']} IV/RV {r['iv_rv'] and round(r['iv_rv'], 2)} {r['reason']}")


if __name__ == "__main__":
    main()
