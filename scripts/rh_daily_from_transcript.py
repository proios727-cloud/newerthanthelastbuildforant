"""Merge Robinhood daily bars (get_equity_historicals, interval "day") from a session transcript into the daily CSVs.

    python3 scripts/rh_daily_from_transcript.py TRANSCRIPT.jsonl [OUTROOT] [--since ISO_TIME]

OUTROOT defaults to chart/data/daily_tv (files land in OUTROOT/1D/<SYMBOL>.csv, the files the screens already read).
Each bar is stamped at that session's 09:30 ET open in UTC, the same instant TradingView daily bars use, so the merge
replaces a day instead of duplicating it. Interpolated (gap-fill) bars are skipped. Robinhood returns only completed
daily bars, so there is no forming bar to drop. A result too large to stay in the transcript is read from the file the
harness saved it to. Up to 10 symbols fit in one call, which keeps the daily runs off the TradingView quota.
"""
import csv
import datetime as dt
import json
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _transcript import tool_results  # noqa: E402
from tv_ohlcv_to_csv import merge_rows  # noqa: E402

ROOT = HERE.parent
ET = ZoneInfo("America/New_York")
SAVED = re.compile(r"(/[^\s\"']+\.(?:txt|json))")


def parse(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = SAVED.search(raw)
        if m and pathlib.Path(m.group(1)).exists():
            body = json.loads(pathlib.Path(m.group(1)).read_text())
            if isinstance(body, list) and body and isinstance(body[0], dict) and "text" in body[0]:
                body = json.loads(body[0]["text"])
            return body
    return None


def daily_rows(body):
    """{symbol: [(iso_utc_open, o, h, l, c, v), ...]} for the day-interval results in one response."""
    out = {}
    for res in (body.get("data") or {}).get("results", []):
        if res.get("interval") != "day":
            continue
        rows = []
        for b in res.get("bars", []):
            if b.get("interpolated"):
                continue
            day = dt.date.fromisoformat(b["begins_at"][:10])
            ts = dt.datetime.combine(day, dt.time(9, 30), ET).astimezone(dt.timezone.utc)
            rows.append((ts.isoformat(), float(b["open_price"]), float(b["high_price"]), float(b["low_price"]),
                         float(b["close_price"]), int(b["volume"])))
        out.setdefault(res["symbol"].upper(), []).extend(rows)
    return out


def main(argv):
    since = argv[argv.index("--since") + 1] if "--since" in argv else ""
    args = [a for i, a in enumerate(argv) if a != "--since" and (i == 0 or argv[i - 1] != "--since")]
    if len(args) < 2:
        raise SystemExit(__doc__)
    root = pathlib.Path(args[2]) if len(args) > 2 else ROOT / "chart/data/daily_tv"
    found = {}
    with open(args[1]) as f:
        for _, _, raw in tool_results(f, lambda n: n.endswith("get_equity_historicals"), since):
            body = parse(raw)
            if body:
                for sym, rows in daily_rows(body).items():
                    found.setdefault(sym, []).extend(rows)
    for sym, rows in sorted(found.items()):
        dest = root / "1D" / f"{sym}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        old = []
        if dest.exists():
            with open(dest, newline="") as f:
                old = list(csv.reader(f))[1:]
        merged = merge_rows(old, rows, dt.timezone.utc)
        with open(dest, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            w.writerows(merged)
        print(f"{dest}: {len(merged)} bars, {merged[0][0]} -> {merged[-1][0]} (+{len(rows)} from Robinhood)")
    if not found:
        print("no Robinhood daily bars found")


if __name__ == "__main__":
    main(sys.argv)
