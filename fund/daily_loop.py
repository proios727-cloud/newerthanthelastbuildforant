"""The desk's daily loop - one process, in funnel order.

  python -m fund loop --once
  python -m fund loop --watch        # intraday: marks + stop/target checks, 15 min

Order of work:
  1. collect   (auto-mark quotes)
  2. signal    (each strategy in strategies/ emits signals)
  3. propose   (risk-sized previews queued for EXECUTE)
  4. review    (nightly review via research/review.py only if a model is wired)
  5. board     (sync-board)
  6. receipt   (fund/receipts/YYYY-MM-DD.md - the paper receipt)
"""
import argparse
import json
import pathlib

from . import clock, config
from .config import ROOT
from .ledger import Ledger, parse_ts

DIR = ROOT / "ledger"
STATE, PREVIEWS = DIR / "state.json", DIR / "previews.json"
RECEIPTS = ROOT / "fund" / "receipts"


def _positions_summary(L):
    rows = []
    for sym, p in L.positions.items():
        if p.get("qty"):
            try:
                mv = L.market_value(sym)
            except KeyError:
                mv = 0.0
            rows.append(f"| {sym} | {p['qty']:+.6g} | {mv:+,.0f} |")
    return rows


def run_loop(mode="full", now=None):
    now = now or clock.now()
    cfg = config.load()
    from . import funnel
    L = Ledger.load(STATE)
    digest = {"ts": now.isoformat(), "mode": mode, "steps": []}

    # 1. collect + mark
    from data import collectors
    symbols = sorted(set(cfg.universe) | {s for s, p in L.positions.items() if p.get("qty")})
    marked = collectors.mark_all(cfg, symbols)
    from datetime import datetime, timezone
    for sym, q in marked.items():
        L.mark(sym, q["price"], now, q.get("bid"), q.get("ask"))
    L.save(STATE)
    digest["steps"].append(f"marked {len(marked)} symbols")

    # 2-3. strategies -> signals -> proposals (full mode only; watch mode just marks + checks)
    proposals = []
    if mode == "full" and clock.equity_session_open(now) or mode == "full":
        import importlib
        import pkgutil
        import strategies as strategies_pkg
        for m in pkgutil.iter_modules(strategies_pkg.__path__):
            mod = importlib.import_module(f"strategies.{m.name}.signal")
            for sig in mod.signals(cfg):
                try:
                    pv = __import__("fund.propose", fromlist=["propose"]).propose(
                        sig, L, cfg, PREVIEWS, now=now)
                    proposals.append(pv["id"])
                except Exception as e:
                    funnel.log_stage("scan_hit", symbol=sig.get("symbol"),
                                     strategy=sig.get("strategy"), dropped=str(e)[:120])
        digest["steps"].append(f"{len(proposals)} previews queued")

    # 4. nightly review (only when a model is wired; research/review.py)
    if mode == "full" and config.env("JUDGE_API_KEY"):
        try:
            from research import review
            review.run(now=now)
            digest["steps"].append("nightly review ran")
        except Exception as e:
            digest["steps"].append(f"review skipped: {str(e)[:80]}")

    # 5. board sync
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "fund", "sync-board"], check=True, cwd=ROOT)
    digest["steps"].append("board synced")

    # 6. receipt
    day = clock.fund_day(now)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    snap = L.snapshot()
    counts = funnel.counts(day=day)
    lines = [
        f"# Paper receipt - {day} ({mode})",
        "",
        f"- NAV: ${snap['nav']:,.0f}  |  Day P&L: {snap['day_pnl']:+,.0f} ({snap['day_pnl_pct']:+.2f}%)",
        f"- Gross exposure: {snap['gross_pct']:.1f}%  |  Drawdown from peak: {snap['drawdown_pct']:.2f}%",
        f"- Funnel: scanned {counts.get('Scanned', 0)} / thesis {counts.get('Thesis written', 0)} / "
        f"risk-passed {counts.get('Risk-passed', 0)} / previewed {counts.get('Previewed', 0)} / "
        f"filled {counts.get('Filled (paper)', 0)}",
        "",
    ]
    pos = _positions_summary(L)
    lines += ["| Symbol | Qty | Market value |", "|---|---|---|"] + (pos or ["| (flat) | | |"])
    lines += ["", f"_Generated {now.isoformat()} by fund loop. All numbers from the ledger._"]
    (RECEIPTS / f"{day}.md").write_text("\n".join(lines), encoding="utf-8")
    digest["steps"].append(f"receipt written: fund/receipts/{day}.md")
    return digest


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fund loop")
    ap.add_argument("--once", action="store_true", help="run one full loop")
    ap.add_argument("--watch", action="store_true", help="run one intraday mark-and-check pass")
    a = ap.parse_args(argv)
    if a.watch:
        d = run_loop(mode="watch")
    else:
        d = run_loop(mode="full")
    print(json.dumps(d, indent=2))


if __name__ == "__main__":
    main()