"""Append the latest daily bars to chart/data CSVs from Alpha Vantage (free key: compact = last 100 sessions).

Only rows newer than a file's last date are added, so history from another vendor is never overwritten.
Needs ALPHAVANTAGE_API_KEY. Crypto symbols are skipped (the desk's crypto data comes from elsewhere).
"""
import csv
import io
import json
import os
import pathlib
import time
import urllib.parse
import urllib.request

from . import load_csv

URL = "https://www.alphavantage.co/query"


def parse_av_csv(text):
    """Alpha Vantage TIME_SERIES_DAILY csv → [(date, o, h, l, c, v)] ascending."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "timestamp" not in rows[0]:
        raise ValueError(f"unexpected Alpha Vantage response: {text[:200]!r}")
    out = [(r["timestamp"], float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
            float(r.get("volume") or 0)) for r in rows]
    return sorted(out)


def merge(path, new_rows):
    """Append rows dated after the file's last bar; returns how many were added."""
    path = pathlib.Path(path)
    last = load_csv(path)[-1].ts if path.exists() else ""
    add = [r for r in new_rows if r[0] > last]
    if not add:
        return 0
    write_header = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["date", "open", "high", "low", "close", "volume"])
        for r in add:
            w.writerow([r[0], *(f"{x:g}" for x in r[1:5]), int(r[5])])
    return len(add)


def fetch(symbol, key, opener=urllib.request.urlopen):
    q = urllib.parse.urlencode({"function": "TIME_SERIES_DAILY", "symbol": symbol,
                                "outputsize": "compact", "datatype": "csv", "apikey": key})
    with opener(f"{URL}?{q}", timeout=30) as r:
        text = r.read().decode()
    if text.lstrip().startswith("{"):
        raise ValueError(json.loads(text).get("Information") or json.loads(text).get("Note") or text[:200])
    return parse_av_csv(text)


def update(folder, universe, key=None, pause=1.2, opener=urllib.request.urlopen):
    key = key or os.environ.get("ALPHAVANTAGE_API_KEY")
    if not key:
        raise SystemExit("set ALPHAVANTAGE_API_KEY")
    report = {}
    for sym, meta in sorted(universe.items()):
        if meta.get("asset") != "equity":
            continue
        try:
            report[sym] = merge(pathlib.Path(folder) / f"{sym}.csv", fetch(sym, key, opener))
        except Exception as e:                      # one bad symbol must not stop the rest
            report[sym] = f"error: {e}"
        time.sleep(pause)
    return report
