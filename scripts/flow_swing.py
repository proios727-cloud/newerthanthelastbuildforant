"""Log today's flow-confirmed swing signal (research/flow-swing/RULE.md) from the fallback flow board.

    python3 scripts/flow_swing.py --today YYYY-MM-DD --board research/fallback/<date>/flow_board.csv
        [--chains DIR] [--log research/flow-swing/signals.jsonl] [--dry-run]

Picks the top candidate (one a day). If DIR holds a quoted chain for that ticker dated today (any *.json whose symbol
matches), the rule's contract is chosen and logged as a paper pick; otherwise the line is logged as a candidate with
no contract, because the rule never invents a price. A day already in the log is not logged again. Append-only.
"""
import argparse
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from options.flow_swing import candidates, pick_contract  # noqa: E402

LOG = ROOT / "research/flow-swing/signals.jsonl"


def todays_chain(folder, ticker, today):
    """Newest chain snapshot in folder for ticker dated today, or None."""
    best = None
    for p in sorted(pathlib.Path(folder).glob("*.json")):
        snap = json.loads(p.read_text())
        if snap.get("symbol", "").upper() == ticker and str(snap.get("asof", ""))[:10] == today:
            best = snap
    return best


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", required=True)
    ap.add_argument("--board", required=True)
    ap.add_argument("--chains")
    ap.add_argument("--log", default=str(LOG))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    with open(a.board, newline="") as f:
        cands = candidates(list(csv.DictReader(f)))
    log = pathlib.Path(a.log)
    done = {json.loads(line)["date"] for line in log.read_text().splitlines() if line.strip()} if log.exists() else set()
    if not cands:
        line = {"date": a.today, "status": "no signal", "board": a.board}
    else:
        top = cands[0]
        line = {"date": a.today, "ticker": top["ticker"], "ratio": top["ratio"], "call_avg": top["call_avg"],
                "put_avg": top["put_avg"], "close": top.get("close"), "day_low": top.get("day_low"),
                "backup": cands[1]["ticker"] if len(cands) > 1 else None, "board": a.board}
        chain = todays_chain(a.chains, top["ticker"], a.today) if a.chains else None
        contract = pick_contract(chain, a.today) if chain else None
        if contract:
            line.update(status="paper pick", **contract,
                        ticket=f"BUY TO OPEN 1 {top['ticker']} {contract['expiry']} {contract['strike']:g} CALL · "
                               f"LIMIT {contract['ask']:.2f} or better · DAY · cost ${contract['cost']:.0f}")
        else:
            line.update(status="candidate (no quoted chain)" if not chain else "candidate (no call fits)")
    print(json.dumps(line))
    if a.dry_run:
        return
    if a.today in done:
        print(f"{a.today} already logged; nothing appended")
        return
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(json.dumps(line) + "\n")


if __name__ == "__main__":
    main()
