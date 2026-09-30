"""Live SHADOW runner for Rule B (read-only, public endpoints, never places orders).

    python -m kalshi.shadow --hours 6 --log shadow_b.jsonl   # run, logging one row per decision
    python -m kalshi.shadow --report shadow_b.jsonl          # summarise a log

Every 15 minutes, 60s before close, it reads each market's live order book and applies Rule B:
buy the favourite if its best ask is in [B_LO, B_HI). It records what `--qty` contracts would
have cost by walking the book, how late the read landed, then (after close) the taker-print VWAP
the backtest assumed, and finally the settlement and fee-inclusive P&L for both prices. The point
is to check the backtest's fills against what a live bot actually sees before any DEMO/LIVE step.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

from . import calibration, fills, taker_fee_cents
from .feed import _get

SERIES = ("KXBTC15M", "KXETH15M")
AT_S, B_LO, B_HI = 60, 50, 96          # must match scripts/build_kalshi48.py Rule B
PERIOD = 900


def _c(p):
    return float(p) * 100


def book_side(book, side, qty):
    """Best ask (¢), contracts at that ask, and avg ¢ to buy `qty` of `side` by walking the book.

    Kalshi's book lists bids only: buying YES at price P lifts a NO bid at 100−P, and vice versa."""
    other = book.get("orderbook_fp", {}).get(("no" if side == "yes" else "yes") + "_dollars") or []
    levels = sorted(((100 - _c(p), float(q)) for p, q in other), key=lambda x: x[0])  # cheapest ask first
    if not levels:
        return None, 0.0, None
    left, cost = qty, 0.0
    for price, q in levels:
        take = min(left, q)
        cost, left = cost + take * price, left - take
        if left <= 0:
            break
    avg = None if left > 0 else round(cost / qty, 2)
    return round(levels[0][0], 1), levels[0][1], avg


def decide(book, qty):
    """Favourite = side with the higher best ask. Returns a decision dict (take=False if Rule B skips)."""
    ya, ydepth, yavg = book_side(book, "yes", qty)
    na, ndepth, navg = book_side(book, "no", qty)
    if ya is None and na is None:
        return {"take": False, "why": "empty book"}
    if ya is None or na is None:  # nobody sells the favourite: market already decided, ask effectively 100¢
        return {"take": False, "why": f"{'yes' if ya is None else 'no'} has no asks (decided)"}
    side, ask, depth, avg = ("yes", ya, ydepth, yavg) if ya >= na else ("no", na, ndepth, navg)
    d = {"side": side, "ask": ask, "depth_at_ask": round(depth, 2), "book_avg": avg}
    if not B_LO <= ask < B_HI:
        return {**d, "take": False, "why": f"ask {ask}¢ outside {B_LO}–{B_HI}"}
    if avg is None:
        return {**d, "take": False, "why": f"book too thin for qty"}
    return {**d, "take": True}


def pnl_c(price, won, qty):
    """Fee-inclusive P&L in cents for `qty` contracts bought at `price` ¢ (rounded to a whole cent)."""
    p = round(price)
    return ((100 if won else 0) - p) * qty - taker_fee_cents(p, qty)


def settle(rec, result, vwap):
    won = result == rec["side"]
    out = {**rec, "result": result, "won": won, "vwap": vwap,
           "pnl_book_c": pnl_c(rec["book_avg"], won, rec["qty"])}
    out["pnl_vwap_c"] = pnl_c(vwap, won, rec["qty"]) if vwap is not None else None
    return out


def next_close(now):
    return (int(now) // PERIOD + 1) * PERIOD


def market_closing(series, close_ts, fetch):
    for m in fetch("/markets", {"series_ticker": series, "status": "open", "limit": 50}).get("markets", []):
        if calibration._ts(m["close_time"]) == close_ts:
            return m
    return None


def run(hours, log, qty, fetch=_get, clock=time.time, sleep=time.sleep):
    end, pending = clock() + hours * 3600, []
    while clock() < end:
        close = next_close(clock() + AT_S)            # next close we can still reach at T-60s
        sleep(max(0, close - AT_S - clock()))
        for s in SERIES:
            try:
                m = market_closing(s, close, fetch)
                if not m:
                    continue
                book = fetch(f"/markets/{m['ticker']}/orderbook", {"depth": 50})
                read_at = clock()
                d = decide(book, qty)
                rec = {"ts": datetime.now(timezone.utc).isoformat(), "ticker": m["ticker"], "close_ts": close,
                       "secs_before_close": round(close - read_at, 2), "qty": qty, **d}
                if d["take"]:
                    pending.append(rec)
                else:
                    _write(log, rec)
                print(f"{rec['ticker']:<30} {rec.get('side','-'):>3} ask {rec.get('ask','-')} "
                      f"{'TAKE' if d['take'] else 'skip: ' + d.get('why', '')}", flush=True)
            except OSError as e:
                print(f"{s}: read failed {e}", file=sys.stderr, flush=True)
        pending = _settle_ready(pending, log, fetch, clock)
    while pending and clock() < end + 1800:          # let the last trades settle
        sleep(30)
        pending = _settle_ready(pending, log, fetch, clock)


def _settle_ready(pending, log, fetch, clock):
    left = []
    for rec in pending:
        try:
            if clock() < rec["close_ts"] + 60:
                left.append(rec)
                continue
            result = fetch(f"/markets/{rec['ticker']}", None).get("market", {}).get("result")
            if result not in ("yes", "no"):
                left.append(rec)
                continue
            vwap, _ = fills.taker_vwap(fills.window_trades(rec["ticker"], rec["close_ts"], fetch=fetch), rec["side"])
            done = settle(rec, result, vwap)
            _write(log, done)
            print(f"{rec['ticker']:<30} settled {result}: book {done['pnl_book_c']:+}¢ vwap {done['pnl_vwap_c']}¢",
                  flush=True)
        except OSError:
            left.append(rec)
    return left


def _write(log, rec):
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def report(path):
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    t = [r for r in rows if r.get("take") and r.get("result")]
    lines = [f"{len(rows)} decisions, {len(t)} settled trades"]
    if t:
        n, q = len(t), t[0]["qty"]
        book, vw = sum(r["pnl_book_c"] for r in t), [r["pnl_vwap_c"] for r in t if r["pnl_vwap_c"] is not None]
        slip = [r["book_avg"] - r["vwap"] for r in t if r["vwap"] is not None]
        lag = sorted(r["secs_before_close"] for r in rows if "secs_before_close" in r)
        lines += [f"win rate {100 * sum(r['won'] for r in t) / n:.1f}%",
                  f"P&L at live book  {book:+}¢ total, {book / n / q:+.2f}¢/contract",
                  f"P&L at print VWAP {sum(vw):+}¢ total, {sum(vw) / max(1, len(vw)) / q:+.2f}¢/contract (backtest basis)",
                  f"book minus VWAP  {sum(slip) / max(1, len(slip)):+.2f}¢ avg (positive = live costs more)",
                  f"read landed {lag[len(lag) // 2]:.1f}s before close (median; target {AT_S}s)"]
        for s in SERIES:
            st = [r for r in t if r["ticker"].startswith(s)]
            if st:
                lines.append(f"  {s:<9} {len(st):>3} trades, {sum(r['won'] for r in st)} won, "
                             f"{sum(r['pnl_book_c'] for r in st):+}¢ at book")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6)
    ap.add_argument("--qty", type=int, default=10)
    ap.add_argument("--log", default="shadow_b.jsonl")
    ap.add_argument("--report", metavar="LOG")
    a = ap.parse_args(argv)
    if a.report:
        print(report(a.report))
        return 0
    print(f"SHADOW Rule B: {', '.join(SERIES)}, T-{AT_S}s, ask {B_LO}–{B_HI}¢, qty {a.qty}. No orders are sent.",
          flush=True)
    run(a.hours, a.log, a.qty)
    return 0


if __name__ == "__main__":
    sys.exit(main())
