#!/usr/bin/env python3
"""Plan a read-only GEX capture session. RESEARCH ONLY: prints JSON and steps; contacts nothing, places no orders.

Usage: python scripts/gex_plan.py SPOT [--expiries N=3] [--width 10] [--today YYYY-MM-DD]

Definitions (exact):
  expiries   the next N weekday dates starting today (New York date unless --today). Weekends are skipped; exchange
             holidays are NOT modeled (no holiday helper exists in this repo), so drop a holiday date by hand.
  strikes    the 2*width integer strikes nearest spot: strike_lo = round(SPOT) - width + 1 .. strike_hi = round(SPOT) + width.
  cursor     base64("p=%.4f" % (strike_lo - 4)); get_option_instruments pages ascend by strike and the cursor returns
             strikes above that value, so this lands 3 strikes under strike_lo. SPOT 732.38, width 10 -> strikes
             723..742, cursor p=719.0000 (cD03MTkuMDAwMA==).
  per expiry 2 instrument pages (call, put) + 2 quote calls, plus 1 equity quote for the session.
"""
import argparse
import base64
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo


def next_weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def make_plan(spot, expiries=3, width=10, today=None):
    today = today or dt.datetime.now(ZoneInfo("America/New_York")).date()
    lo, hi = round(spot) - width + 1, round(spot) + width
    cursor = base64.b64encode(("p=%.4f" % (lo - 4)).encode()).decode()
    exps = next_weekdays(today, expiries)
    return {
        "spot": spot, "expiries": exps, "cursor": cursor, "strike_lo": lo, "strike_hi": hi,
        "calls_per_expiry": {"instrument_pages": 2, "quote_calls": 2},
        "total_calls": 1 + 4 * len(exps),
    }


def steps(p):
    n = len(p["expiries"])
    return [
        "1. get_equity_quotes [SYM] (spot, venue_last_trade_time)",
        "2. for each expiry %s and type call/put: get_option_instruments chain_symbol=SYM expiration_dates=[expiry] "
        "type=<call|put> state=active cursor=%s (keep strikes %d..%d)" % (", ".join(p["expiries"]), p["cursor"], p["strike_lo"], p["strike_hi"]),
        "3. for each of those %d instrument lists: get_option_quotes for the ids (20 per call or fewer)" % (2 * n),
        "4. SINCE=<ISO time step 1 began> scripts/gex_nightly.sh SYM",
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spot", type=float)
    ap.add_argument("--expiries", type=int, default=3)
    ap.add_argument("--width", type=int, default=10)
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    today = dt.date.fromisoformat(a.today) if a.today else None
    p = make_plan(a.spot, a.expiries, a.width, today)
    print(json.dumps(p, indent=2))
    print("\nSteps:")
    for s in steps(p):
        print(s)


if __name__ == "__main__":
    sys.exit(main())
