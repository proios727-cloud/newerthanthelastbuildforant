"""Stage 1 recorder: Kalshi public trades (+ books when live). Read-only, never places orders.

    python -m gmdesk.record backfill --series KXBTC15M KXETH15M --markets 300 --out data/gm
    python -m gmdesk.record live --series KXBTC15M --minutes 60 --out data/gm

Backfill stores one gzip JSON per settled market: data/gm/<series>/<ticker>.json.gz
  {ticker, series, close_ts, result, t: [[ts, p, q, s], ...]}  (compact: ~34k trades per BTC window)
Live mode appends JSONL lines {ticker, series, ts, p, q, s, close_ts} plus top-of-book snapshots.
  p = YES price in [0,1], q = contracts, s = +1 taker bought YES / -1 taker bought NO.
Kalshi tags the aggressor (`taker_side`), so no tick-rule classification is needed.
"""
import argparse
import calendar
import gzip
import json
import os
import sys
import time
from datetime import datetime

from kalshi.calibration import settled_markets, throttled
from kalshi.feed import _get, open_markets


def ts_of(s):
    s = s.rstrip("Z")
    base, _, frac = s.partition(".")
    t = calendar.timegm(datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").timetuple())
    return t + (float("0." + frac) if frac else 0.0)


def norm_trade(t, series, result=None, close_ts=None):
    return {
        "id": t["trade_id"], "ticker": t["ticker"], "series": series,
        "ts": round(ts_of(t["created_time"]), 3),
        "p": float(t["yes_price_dollars"]), "q": float(t.get("count_fp") or t.get("count") or 0),
        "s": 1 if t["taker_side"] == "yes" else -1,
        "result": result, "close_ts": close_ts,
    }


def market_trades(ticker, fetch, min_ts=None):
    out, cursor = [], None
    while True:
        p = {"ticker": ticker, "limit": 1000}
        if cursor:
            p["cursor"] = cursor
        if min_ts:
            p["min_ts"] = int(min_ts)
        body = fetch("/markets/trades", p)
        out += body.get("trades", [])
        cursor = body.get("cursor")
        if not cursor:
            return out


def _path(out, series):
    os.makedirs(out, exist_ok=True)
    return os.path.join(out, f"trades_{series}.jsonl")


def market_file(out, series, ticker):
    d = os.path.join(out, series)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{ticker}.json.gz")


def backfill(series, n, out, fetch=None, log=print):
    fetch = fetch or throttled()
    ms = [m for m in settled_markets(series, n, fetch)
          if not os.path.exists(market_file(out, series, m["ticker"]))]
    added = 0
    for i, m in enumerate(ms):
        rows = sorted((norm_trade(t, series) for t in market_trades(m["ticker"], fetch)), key=lambda r: r["ts"])
        doc = {"ticker": m["ticker"], "series": series, "close_ts": ts_of(m["close_time"]), "result": m["result"],
               "t": [[r["ts"], r["p"], r["q"], r["s"]] for r in rows]}
        tmp = market_file(out, series, m["ticker"]) + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"))
        os.replace(tmp, market_file(out, series, m["ticker"]))
        added += len(rows)
        if i % 10 == 0:
            log(f"{series}: {i + 1}/{len(ms)} markets, {added} trades", flush=True)
    log(f"{series}: done, {len(ms)} new markets, {added} trades", flush=True)
    return added


def book_top(book):
    ob = book.get("orderbook_fp") or book.get("orderbook") or {}
    def best(levels):
        return max((float(px) for px, *_ in levels), default=None) if levels else None
    return best(ob.get("yes_dollars") or []), best(ob.get("no_dollars") or [])


def live(series_list, minutes, out, poll_s=5, fetch=None, clock=time.time, sleep=time.sleep, log=print):
    """Poll open markets: append new trades (deduped) and a top-of-book snapshot per poll."""
    fetch = fetch or throttled(delay=0.1)
    seen, end = set(), clock() + minutes * 60
    books = os.path.join(out, "books.jsonl")
    os.makedirs(out, exist_ok=True)
    while clock() < end:
        for s in series_list:
            for m in open_markets(s, fetch):
                close_ts = ts_of(m["close_time"])
                trades = market_trades(m["ticker"], fetch, min_ts=clock() - 120)
                new = [t for t in trades if t["trade_id"] not in seen]
                seen.update(t["trade_id"] for t in new)
                with open(_path(out, s + "_live"), "a", encoding="utf-8") as f:
                    for t in sorted(new, key=lambda t: t["created_time"]):
                        f.write(json.dumps(norm_trade(t, s, None, close_ts)) + "\n")
                yb, nb = book_top(fetch(f"/markets/{m['ticker']}/orderbook"))
                with open(books, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": round(clock(), 3), "ticker": m["ticker"], "yes_bid": yb,
                                        "no_bid": nb, "close_ts": close_ts}) + "\n")
        sleep(poll_s)
    log("live recording finished")


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("backfill"); b.add_argument("--series", nargs="+", default=["KXBTC15M", "KXETH15M"])
    b.add_argument("--markets", type=int, default=300); b.add_argument("--out", default="data/gm")
    lv = sp.add_parser("live"); lv.add_argument("--series", nargs="+", default=["KXBTC15M"])
    lv.add_argument("--minutes", type=float, default=60); lv.add_argument("--out", default="data/gm")
    lv.add_argument("--poll", type=float, default=5)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "backfill":
            for s in a.series:
                backfill(s, a.markets, a.out)  # run one process per series to parallelise
        else:
            live(a.series, a.minutes, a.out, a.poll)
    except OSError as e:
        print(f"Kalshi unreachable: {e}. Allow api.elections.kalshi.com in the network policy.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
