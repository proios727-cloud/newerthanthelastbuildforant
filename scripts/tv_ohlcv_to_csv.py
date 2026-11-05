"""Write TradingView connector OHLCV responses (format=columns) as intraday CSVs, verbatim, in US/Eastern time.

Connector results are saved as JSON files by the session (or a subagent) instead of being retyped. This reads them and writes
chart/data/intraday/<interval>/<SYMBOL>.csv with columns timestamp,open,high,low,close,volume, regular hours only (09:30-16:00 ET).
    python3 scripts/tv_ohlcv_to_csv.py OUTROOT RESPONSE.json [RESPONSE.json ...]
    python3 scripts/tv_ohlcv_to_csv.py --all-hours OUTROOT RESPONSE.json ...   # crypto: every bar, timestamps in UTC
    python3 scripts/tv_ohlcv_to_csv.py --merge OUTROOT RESPONSE.json ...       # add new bars to an existing CSV
--merge keeps the existing rows, replaces any for the same instant, and drops a final bar that is still forming
(its interval has not ended yet), so a daily job can append each new session. Rows are matched by instant, not by text,
and the merged file is written in this run's zone (UTC with --all-hours, else ET), so a file never holds one bar twice.
"""
import csv
import datetime as dt
import json
import pathlib
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from chart.intraday import INTERVAL_MINUTES  # noqa: E402

ET = ZoneInfo("America/New_York")
RTH_OPEN, RTH_CLOSE = dt.time(9, 30), dt.time(16, 0)


def load_response(path):
    body = json.loads(pathlib.Path(path).read_text())
    if isinstance(body, list) and body and isinstance(body[0], dict) and "text" in body[0]:
        body = json.loads(body[0]["text"])
    if not body.get("success", True) or "bars" not in body:
        raise ValueError(f"{path}: not a successful OHLCV response")
    return body


def rows_from(body, all_hours=False):
    b = body["bars"]
    keys = ("t", "o", "h", "l", "c", "v")
    if isinstance(b, list):  # format="rows": one dict per bar
        b = {k: [bar.get(k) for bar in b] for k in keys}
    cols = [b[k] for k in keys]
    if len({len(c) for c in cols}) != 1:
        raise ValueError("column lengths differ")
    out = []
    for t, o, h, l, c, v in zip(*cols):
        ts = dt.datetime.fromtimestamp(int(t), dt.timezone.utc if all_hours else ET)
        if all_hours or RTH_OPEN <= ts.time() < RTH_CLOSE:
            out.append((ts.isoformat(), o, h, l, c, v))
    return out


def merge_rows(old, new, tz):
    """Existing CSV rows + new rows -> one row per instant, sorted, timestamps rewritten in `tz`. New rows win."""
    by_instant = {}
    for r in list(old) + list(new):
        t = dt.datetime.fromisoformat(r[0])
        by_instant[t.timestamp()] = [t.astimezone(tz).isoformat(), *r[1:]]
    return [by_instant[k] for k in sorted(by_instant)]


def main(argv):
    all_hours, merge = "--all-hours" in argv, "--merge" in argv
    argv = [a for a in argv if a not in ("--all-hours", "--merge")]
    if len(argv) < 3:
        raise SystemExit(__doc__)
    root = pathlib.Path(argv[1])
    for path in argv[2:]:
        body = load_response(path)
        sym = body["symbol"].split(":")[-1].upper()
        rows = rows_from(body, all_hours)
        dest = root / body["interval"] / f"{sym}.csv"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if merge:
            ivl = INTERVAL_MINUTES[body["interval"]] * 60
            now = dt.datetime.now(dt.timezone.utc)
            rows = [r for r in rows if dt.datetime.fromisoformat(r[0]) + dt.timedelta(seconds=ivl) <= now]
            old = []
            if dest.exists():
                with open(dest, newline="") as f:
                    old = list(csv.reader(f))[1:]
            rows = merge_rows(old, rows, dt.timezone.utc if all_hours else ET)
        with open(dest, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            w.writerows(rows)
        print(f"{dest}: {len(rows)} bars, {rows[0][0]} -> {rows[-1][0]}")


if __name__ == "__main__":
    main(sys.argv)
