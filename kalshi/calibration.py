"""Late-window calibration backtest (read-only, public endpoints, never places orders).

    python -m kalshi.calibration --series KXBTC15M --markets 300 --cache /tmp/cal.jsonl

For settled 15-minute markets, look at the favourite at T-N minutes before close, "buy" it at the
ask (taker, fee included) and record the outcome. Buckets show whether favourites are priced at
their true hit rate; a positive net EV per contract in a bucket is the only case for a late-window
strategy. Uses Kalshi's own 1-minute candles, so no outside price feed is required.
"""
import argparse
import calendar
import json
import sys
import time
from datetime import datetime

from . import taker_fee_cents
from .feed import _get

BUCKETS = ((50, 80), (80, 90), (90, 95), (95, 99))


def _ts(s):
    return calendar.timegm(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").timetuple())


def _c(v):
    return None if v in (None, "") else int(round(float(v) * 100))


def throttled(fetch=_get, delay=0.25, tries=6):
    def go(path, params=None):
        for i in range(tries):
            try:
                time.sleep(delay)
                return fetch(path, params)
            except Exception as e:  # 429 → back off
                if "429" not in str(e) or i == tries - 1:
                    raise
                time.sleep(2 ** i)
    return go


def settled_markets(series, n, fetch=_get, since_ts=None):
    """Newest-first settled markets; with `since_ts`, stop once a market closed before it."""
    out, cursor = [], None
    while len(out) < n:
        p = {"series_ticker": series, "status": "settled", "limit": min(200, n - len(out))}
        if cursor:
            p["cursor"] = cursor
        body = fetch("/markets", p)
        out += [m for m in body.get("markets", []) if m.get("result") in ("yes", "no")]
        cursor = body.get("cursor")
        if not cursor:
            break
    if since_ts:
        out = [m for m in out if _ts(m["close_time"]) >= since_ts]
    return sorted(out, key=lambda m: m["close_time"], reverse=True)[:n]


def snapshots(m, minutes, fetch=_get):
    """Favourite side, its ask and the book spread (cents) at each `minutes` before close (one request)."""
    o, c = _ts(m["open_time"]), _ts(m["close_time"])
    body = fetch(f"/series/{m['ticker'].split('-')[0]}/markets/{m['ticker']}/candlesticks",
                 {"start_ts": o, "end_ts": c, "period_interval": 1})
    by_end = {k["end_period_ts"]: k for k in body.get("candlesticks", [])}
    out = []
    for n in minutes:
        k = by_end.get(c - 60 * n)
        if not k:
            continue
        ya, yb = _c(k["yes_ask"]["close_dollars"]), _c(k["yes_bid"]["close_dollars"])
        if ya is None or yb is None:
            continue
        no_ask = 100 - yb
        side, ask = ("yes", ya) if ya >= no_ask else ("no", no_ask)
        out.append({"ticker": m["ticker"], "close_ts": c, "minutes_left": n, "side": side, "ask": ask,
                    "spread": ya - yb, "won": m["result"] == side})
    return out


def snapshot(m, minutes_left, fetch=_get):
    r = snapshots(m, [minutes_left], fetch)
    return r[0] if r else None


def summarize(rows):
    """Per bucket: n, hit rate, mean ask, net EV/contract (cents) after taker fee, worst streak-free."""
    out = []
    for lo, hi in BUCKETS:
        b = [r for r in rows if lo <= r["ask"] < hi]
        if not b:
            out.append({"bucket": f"{lo}-{hi}", "n": 0})
            continue
        pnl = [(100 if r["won"] else 0) - r["ask"] - taker_fee_cents(r["ask"], 1) for r in b]
        out.append({"bucket": f"{lo}-{hi}", "n": len(b),
                    "hit": round(sum(r["won"] for r in b) / len(b), 3),
                    "avg_ask": round(sum(r["ask"] for r in b) / len(b), 1),
                    "ev_c": round(sum(pnl) / len(pnl), 2), "worst_c": min(pnl)})
    return out


def render(minutes_left, rows):
    lines = [f"T-{minutes_left}min favourite, buy at ask, fee included ({len(rows)} markets)",
             f"{'ask¢':<8}{'n':>5}{'hit':>8}{'avg ask':>9}{'net EV¢':>9}{'worst¢':>8}"]
    for s in summarize(rows):
        lines.append(f"{s['bucket']:<8}{s['n']:>5}" + (
            f"{s['hit']:>8}{s['avg_ask']:>9}{s['ev_c']:>9}{s['worst_c']:>8}" if s["n"] else ""))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="KXBTC15M")
    ap.add_argument("--markets", type=int, default=300)
    ap.add_argument("--minutes", type=int, nargs="+", default=[3, 2, 1])
    ap.add_argument("--cache", help="jsonl of snapshots; reused so reruns don't refetch")
    a = ap.parse_args(argv)
    fetch = throttled()
    cached = {}
    if a.cache:
        try:
            with open(a.cache, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    cached[(r["ticker"], r["minutes_left"])] = r
        except FileNotFoundError:
            pass
    try:
        markets = settled_markets(a.series, a.markets, fetch)
        for m in markets:
            need = [n for n in a.minutes if (m["ticker"], n) not in cached]
            for s in snapshots(m, need, fetch) if need else []:
                cached[(m["ticker"], s["minutes_left"])] = s
                if a.cache:
                    with open(a.cache, "a", encoding="utf-8") as f:
                        f.write(json.dumps(s) + "\n")
    except OSError as e:
        print(f"Kalshi unreachable: {e}", file=sys.stderr)
        return 2
    tickers = {m["ticker"] for m in markets}
    for n in a.minutes:
        print(render(n, [r for (t, k), r in cached.items() if k == n and t in tickers]), end="\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
