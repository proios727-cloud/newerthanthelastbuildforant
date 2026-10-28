"""Sanity checks for an OHLC CSV before anything is backtested on it.

Checks: strictly ascending dates, low <= open/close <= high, positive prices, no high/low more than
`max_wick` beyond the open/close (a bad print), no day-over-day close move larger than `max_move`,
and — when a reference file overlaps — closes that match it within `tol`.
"""
from . import load_csv


def check(path, ref=None, max_move=0.25, tol=0.02, max_wick=0.15):
    problems = []
    try:
        bars = load_csv(path)
    except ValueError as e:
        return {"file": str(path), "ok": False, "bars": 0, "problems": [str(e)]}
    for i, b in enumerate(bars):
        if min(b.open, b.high, b.low, b.close) <= 0:
            problems.append(f"{b.ts}: non-positive price")
        if not (b.low <= min(b.open, b.close) and max(b.open, b.close) <= b.high):
            problems.append(f"{b.ts}: OHLC out of order (o={b.open} h={b.high} l={b.low} c={b.close})")
        body_hi, body_lo = max(b.open, b.close), min(b.open, b.close)
        if b.high > body_hi * (1 + max_wick) or b.low < body_lo * (1 - max_wick):
            problems.append(f"{b.ts}: wick beyond {max_wick:.0%} of the open/close (h={b.high} l={b.low})")
        if i and abs(b.close / bars[i - 1].close - 1) > max_move:
            problems.append(f"{b.ts}: close moved {b.close / bars[i - 1].close - 1:+.1%} in one day")
    overlap = matched = 0
    if ref:
        theirs = {b.ts: b.close for b in load_csv(ref)}
        for b in bars:
            if b.ts in theirs:
                overlap += 1
                if abs(b.close - theirs[b.ts]) <= tol:
                    matched += 1
                else:
                    problems.append(f"{b.ts}: close {b.close} vs reference {theirs[b.ts]}")
    return {
        "file": str(path), "ok": not problems, "bars": len(bars),
        "from": bars[0].ts if bars else None, "to": bars[-1].ts if bars else None,
        "reference_overlap": overlap, "reference_matched": matched, "problems": problems[:20],
    }
