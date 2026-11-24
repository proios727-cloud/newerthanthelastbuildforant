"""Build the fallback option-activity board when Robinhood is offline (see docs/heatseeker-daily.md section 9).

    python3 scripts/fallback_board.py --today YYYY-MM-DD --quotes QUOTES.json AV_FILE:TICKER [AV_FILE:TICKER ...]
        [--max-expiry YYYY-MM-DD] [--out DIR] [--offline RUN]

AV_FILE is a saved Alpha Vantage REALTIME_VOLUME_OPEN_INTEREST_RATIO result ({"symbol", "data": [...]}), as the
harness writes it when the result is too large to show. QUOTES.json is a TradingView get_symbol_data_batch result
({"data": {"EXCH:TICKER": {close, change, high, low}}}). Writes OUT/flow_board.csv (default
research/fallback/<today>/). --offline RUN appends one line to research/connector_status.jsonl recording that RUN
(e.g. "premium") ran on fallback data because Robinhood was offline. Read-only: nothing here places an order.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from options.fallback import board, summarize  # noqa: E402

FIELDS = ["rank", "ticker", "source", "lean", "call_avg", "put_avg", "call_active", "put_active", "close", "change_pct",
          "day_low", "day_high", "above_low_pct", "top_contracts", "data_date"]
STATUS = ROOT / "research/connector_status.jsonl"


def load_quotes(path):
    """{TICKER: quote} from a TradingView batch result, with the exchange prefix dropped."""
    data = json.loads(pathlib.Path(path).read_text()).get("data", {})
    return {k.split(":")[-1].upper(): v for k, v in data.items()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", required=True)
    ap.add_argument("--quotes", required=True)
    ap.add_argument("--max-expiry")
    ap.add_argument("--out")
    ap.add_argument("--offline")
    ap.add_argument("av", nargs="+", help="AV_FILE:TICKER")
    a = ap.parse_args(argv)
    max_exp = a.max_expiry or (dt.date.fromisoformat(a.today) + dt.timedelta(days=30)).isoformat()
    tomorrow = (dt.date.fromisoformat(a.today) + dt.timedelta(days=1)).isoformat()
    quotes = load_quotes(a.quotes)
    scores, missing = {}, []
    for spec in a.av:
        path, _, tic = spec.rpartition(":")
        tic = tic.upper()
        spot = (quotes.get(tic) or {}).get("close")
        if not path or not spot or not pathlib.Path(path).is_file():
            missing.append(tic)
            continue
        try:
            rows = json.loads(pathlib.Path(path).read_text()).get("data", [])
        except (json.JSONDecodeError, AttributeError):
            missing.append(tic)
            continue
        scores[tic] = summarize(rows, spot, max_exp, min_expiry=tomorrow)
    out = pathlib.Path(a.out) if a.out else ROOT / "research/fallback" / a.today
    out.mkdir(parents=True, exist_ok=True)
    b = board(scores, quotes)
    with open(out / "flow_board.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in b:
            w.writerow({k: "" if v is None else v for k, v in r.items()})
    if a.offline:
        with open(STATUS, "a") as f:
            f.write(json.dumps({"date": a.today, "run": a.offline, "robinhood": "offline",
                                "fallback": str((out / "flow_board.csv").relative_to(ROOT))
                                if out.is_relative_to(ROOT) else str(out / "flow_board.csv")}) + "\n")
    print(f"{out / 'flow_board.csv'}: {len(b)} tickers" + (f"; skipped (no quote or file): {','.join(missing)}"
                                                         if missing else ""))
    for r in b:
        print(f"{r['rank']:>2} {r['ticker']:<5} {r['lean']:<5} C {r['call_avg']:>6} P {r['put_avg']:>6}  {r['top_contracts']}")


if __name__ == "__main__":
    main()
