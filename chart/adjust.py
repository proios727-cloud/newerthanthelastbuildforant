"""Split adjustment and recorded data corrections, applied once when a vendor file is imported.

Vendors that report raw prices (ThetaData EOD, Alpha Vantage TIME_SERIES_DAILY) show a split as a
one-day crash. Dividing every earlier bar by the ratio (and multiplying its volume) makes history
continuous with today's raw prices, so later raw bars can still be appended unchanged.
Every change is listed here and in chart/data/SOURCES.md; nothing is altered silently.
"""
from . import Bar

SPLITS = {
    "NVDA": [("2024-06-10", 10.0)],     # 10-for-1, first split-adjusted session 2024-06-10
    # Select Sector SPDRs, 2-for-1 effective 2025-12-05 (close halves, volume doubles; re-fetches identical)
    **{s: [("2025-12-05", 2.0)] for s in ("XLK", "XLE", "XLU", "XLB", "XLY")},
}

# (symbol, date) → why. Bad vendor rows with no usable fix are removed rather than guessed.
DROPS = {
    ("XLF", "2026-10-06"): "ThetaData row prices every field at 0.0002 (created 00:02, not the usual 17:15)",
    ("XLC", "2026-10-05"): "ThetaData row at ~76 on ~0.2M shares between ~111 days on ~5M shares; re-fetch identical",
}

# (symbol, date) → field fixes. "body" caps the high at max(open, close) / floors the low at min(open, close).
CORRECTIONS = {
    ("NVDA", "2024-06-10"): {"high": "body",
                             "why": "ThetaData high 195.95 on a 120.45 → 121.79 day is a bad print; "
                                    "intraday bars to confirm the true high need a paid plan"},
    ("SPY", "2026-02-02"): {"low": "body",
                            "why": "ThetaData low 69.005 on a ~690 day is a dropped digit; re-fetch returned the same value"},
}


def split_adjust(bars, splits):
    """Divide OHLC (and multiply volume) of every bar before each split date by its ratio."""
    out = []
    for b in bars:
        f = 1.0
        for date, ratio in splits:
            if b.ts < date:
                f *= ratio
        out.append(b if f == 1.0 else Bar(b.ts, b.open / f, b.high / f, b.low / f, b.close / f, b.volume * f))
    return out


def correct(bars, symbol, corrections=CORRECTIONS):
    out, applied = [], []
    for b in bars:
        fix = corrections.get((symbol, b.ts))
        if fix:
            hi = max(b.open, b.close) if fix.get("high") == "body" else b.high
            lo = min(b.open, b.close) if fix.get("low") == "body" else b.low
            applied.append({"date": b.ts, "high": [b.high, hi], "low": [b.low, lo], "why": fix["why"]})
            b = Bar(b.ts, b.open, hi, lo, b.close, b.volume)
        out.append(b)
    return out, applied


def prepare(bars, symbol):
    """Drops, then corrections (stated in raw vendor prices), then split adjustment."""
    dropped = [b.ts for b in bars if (symbol, b.ts) in DROPS]
    bars = [b for b in bars if (symbol, b.ts) not in DROPS]
    fixed, applied = correct(bars, symbol)
    applied += [{"date": d, "dropped": True, "why": DROPS[(symbol, d)]} for d in dropped]
    return split_adjust(fixed, SPLITS.get(symbol, [])), applied


def write_csv(path, bars):
    with open(path, "w", newline="") as f:
        f.write("date,open,high,low,close,volume\n")
        for b in bars:
            f.write(f"{b.ts},{b.open:.6g},{b.high:.6g},{b.low:.6g},{b.close:.6g},{int(round(b.volume))}\n")
