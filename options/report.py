"""Weekly hit-rate report: the skill's five review questions, from the data.

Renders markdown from data/ledger.jsonl to fund/receipts/options_weekly_<isoweek>.md
and prints the headline. Joined by the daily loop on Fridays and runnable alone:

  python -m options.report            # resolve first, then report
  python -m options.report --no-resolve
"""
import argparse
import datetime as dt
import pathlib
from collections import Counter, defaultdict

from fund.config import ROOT

from . import ledger as L
from .resolve import resolve_all

RECEIPTS = ROOT / "fund" / "receipts"
MIN_SAMPLES = 10  # skill: fewer than ~10 instances of a setup is not yet evidence


def _isoweek(d=None):
    d = d or dt.date.today()
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def stats(rows):
    closed = [r for r in rows if r.get("outcome") in ("target", "stop", "scratch")]
    by_setup = defaultdict(list)
    for r in closed:
        by_setup[r.get("setup", "?")].append(r)
    out = {}
    for setup, rs in by_setup.items():
        wins = [r for r in rs if (r.get("r") or 0) > 0]
        total_r = sum(r.get("r") or 0 for r in rs)
        out[setup] = {
            "n": len(rs), "wins": len(wins),
            "hit_rate": len(wins) / len(rs) if rs else 0.0,
            "total_r": total_r,
            "enough_samples": len(rs) >= MIN_SAMPLES,
        }
    return out, closed


def render(rows, week):
    per_setup, closed = stats(rows)
    open_n = sum(1 for r in rows if r.get("outcome") is None and r.get("source") != "ledger")
    no_trades = sum(1 for r in rows if r.get("outcome") == "no-trade")
    lines = [f"# Options ledger weekly - {week}", ""]
    lines.append(f"- Signals logged: {len(rows)} | resolved: {len(closed)} | open: {open_n} | "
                 f"board no-trades: {no_trades}")
    lines.append("")
    lines.append("## Per-setup (resolved only)")
    lines.append("| Setup | N | Wins | Hit rate | Total R | Evidence? |")
    lines.append("|---|---|---|---|---|---|")
    for setup, s in sorted(per_setup.items(), key=lambda kv: -kv[1]["total_r"]):
        flag = "yes" if s["enough_samples"] else f"NO (<{MIN_SAMPLES})"
        lines.append(f"| {setup} | {s['n']} | {s['wins']} | {s['hit_rate']*100:.0f}% | "
                     f"{s['total_r']:+.1f} | {flag} |")
    if not per_setup:
        lines.append(f"| (none resolved yet - fewer than {MIN_SAMPLES} samples means no conclusions) | | | | | |")
    lines.append("")
    lines.append("## The five review questions")
    lines.append(f"1. **Which setups paid?** "
                 + ("; ".join(f"{k}: {v['total_r']:+.1f}R on {v['n']}" for k, v in
                              sorted(per_setup.items(), key=lambda kv: -kv[1]["total_r"]))
                    if per_setup else "no resolved trades yet")
                 + ". Counts under 10 are not evidence - flagged above.")
    gates = [r for r in rows if r.get("outcome") == "no-trade"]
    lines.append(f"2. **Gate rejections that would have worked?** {len(gates)} no-trade rows "
                 "logged; needs outcome-replay against bars (not yet automated).")
    posgex = [r for r in closed if "+GEX" in str(r.get("regime", ""))]
    neggex = [r for r in closed if "-GEX" in str(r.get("regime", ""))]
    lines.append(f"3. **Exit-policy failures?** {len(posgex)} +GEX and {len(neggex)} -GEX resolved; "
                 "giveback/early-cut analysis needs per-bar exits (TV backtest provides the visual).")
    lines.append("4. **Entry slippage?** Signal-time prices are delayed snapshot/quote; "
                 "compare against the TV backtest entries for a read.")
    lines.append("5. **Map confidence vs outcome?** Vanna axis not yet computed; revisit "
                 "once contested-vs-stable maps can be distinguished.")
    lines.append("")
    lines.append("_All numbers from data/ledger.jsonl. Under 10 samples per setup, nothing "
                 "here is evidence of an edge - it is bookkeeping toward one._")
    return "\n".join(lines), per_setup


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m options.report")
    ap.add_argument("--no-resolve", action="store_true")
    ap.add_argument("--week", default=None, help="e.g. 2026-W41 (defaults to current)")
    a = ap.parse_args(argv)
    if not a.no_resolve:
        resolved = resolve_all(None)
        for _, row, outcome, r, note in resolved:
            print(f"resolved {row.get('ticker')} {row.get('setup')}: {outcome} ({r:+.1f}R)" if r is not None
                  else f"resolved {row.get('ticker')} {row.get('setup')}: {outcome}")
    rows = L.rows()
    week = a.week or _isoweek()
    md, per_setup = render(rows, week)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    out = RECEIPTS / f"options_weekly_{week}.md"
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}")
    total_r = sum(s["total_r"] for s in per_setup.values())
    n = sum(s["n"] for s in per_setup.values())
    print(f"headline: {n} resolved, {total_r:+.1f}R total" if n else "headline: no resolved signals yet")


if __name__ == "__main__":
    main()