"""Write the dashboard's open paper positions from research/paper/positions.jsonl.

The journal is append-only: an "open" event adds a position, a later {"id", "event": "close", "date", "exit"} closes it.
Positions come from the premium screener's paper log, Heat Seeker trades and fills the owner reports from their paper
account (source "my paper fill"). No brokerage account is read.
    python3 scripts/positions_csv.py OUT.csv
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chart import read_jsonl  # noqa: E402

JOURNAL = ROOT / "research/paper/positions.jsonl"
FIELDS = ["id", "source", "date", "ticker", "contract", "instrument_id", "type", "strike", "expiry", "side", "qty", "entry",
          "take_profit_at", "stop_at", "time_exit", "cash_needed"]


def open_positions(path=None):
    """Open events without a later close event for the same id."""
    rows = read_jsonl(path or JOURNAL)
    closed = {r["id"] for r in rows if r.get("event") == "close"}
    return [r for r in rows if r.get("event") == "open" and r["id"] not in closed]


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    pos = open_positions()
    with open(argv[1], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(pos)
    ids = [p["instrument_id"] for p in pos if p.get("instrument_id")]
    print(f"{argv[1]}: {len(pos)} open positions; quote ids: {json.dumps(ids)}; "
          f"symbols: {json.dumps(sorted({p['ticker'] for p in pos} | {'SPY', 'QQQ'}))}")
    missing = [p["id"] for p in pos if not p.get("instrument_id")]
    if missing:
        print(f"no instrument_id (no live quote until it's added from get_option_instruments): {', '.join(missing)}")


if __name__ == "__main__":
    main(sys.argv)
