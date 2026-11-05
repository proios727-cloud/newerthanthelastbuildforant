"""Total-return versions of the daily files: back-adjust prices for cash dividends.

Price-only bars flatter anything that holds low-yield assets or sits in cash, because the benchmark's dividends are
missing (about 1.9%/yr for the ETF basket). `chart/data/meta/dividends.csv` lists each dividend in the daily span, from the
"dividend amount" column of Alpha Vantage's weekly adjusted series. Amounts are the vendor's raw per-share values; a
dividend before a split in `adjust.SPLITS` is divided by the split ratio here so it matches the split-adjusted files.

The weekly series gives the week, not the day: `ex_date` is the first session of that week. A real ex-date can be up to
four sessions later (SPY's falls on Fridays), which moves a 0.2-1.2% step by a few days and leaves yearly totals exact.

Adjustment is the standard back-adjustment: every bar before an ex-date is scaled by (1 - amount / previous close), so
returns across the ex-date include the dividend and the latest prices stay as traded.
"""
import csv
import pathlib

from . import Bar, load_csv
from .adjust import SPLITS, write_csv

TABLE = pathlib.Path(__file__).with_name("data") / "meta" / "dividends.csv"


def load(path=TABLE):
    """{symbol: [(ex_date, split-adjusted amount)]} in date order."""
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            amt = float(r["amount"])
            for when, ratio in SPLITS.get(r["symbol"], []):
                if r["ex_date"] < when:
                    amt /= ratio
            out.setdefault(r["symbol"], []).append((r["ex_date"], amt))
    return {s: sorted(v) for s, v in out.items()}


def total_return(bars, divs):
    """Back-adjusted copy of `bars` for the dividends `divs` [(ex_date, amount)]. Dividends outside the bars are ignored."""
    idx = {b.ts: i for i, b in enumerate(bars)}
    factor = [1.0] * len(bars)
    for ex, amt in divs:
        i = idx.get(ex)
        if not i:                                   # not in the file, or on its first bar (no previous close)
            continue
        k = 1 - amt / bars[i - 1].close
        for j in range(i):
            factor[j] *= k
    return [Bar(b.ts, b.open * f, b.high * f, b.low * f, b.close * f, b.volume) for b, f in zip(bars, factor)]


def apply(src, dst, table=TABLE):
    """Write total-return copies of every CSV in folder `src` into `dst`; returns {symbol: dividends applied}."""
    divs, report = load(table), {}
    pathlib.Path(dst).mkdir(parents=True, exist_ok=True)
    for f in sorted(pathlib.Path(src).glob("*.csv")):
        sym = f.stem.upper()
        bars = load_csv(f)
        use = [d for d in divs.get(sym, []) if bars[0].ts < d[0] <= bars[-1].ts]
        write_csv(pathlib.Path(dst) / f.name, total_return(bars, use))
        report[sym] = len(use)
    return report
