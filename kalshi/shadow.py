"""Live SHADOW runner for Rule B2 (read-only, public endpoints, never places orders).

    python -m kalshi.shadow --hours 6 --log shadow_b.jsonl   # run, logging one row per decision
    python -m kalshi.shadow --report shadow_b.jsonl          # summarise a log

Every 15 minutes, 60s before close, it reads each market's live order book and applies Rule B:
buy the favourite if its best ask is in [B_LO, B_HI). It records what `--qty` contracts would
have cost by walking the book, how late the read landed, then (after close) the taker-print VWAP
the backtest assumed, and finally the settlement and fee-inclusive P&L for both prices. The point
is to check the backtest's fills against what a live bot actually sees before any DEMO/LIVE step.

Rule B2 (from 2026-09-29) adds one trade per 15-minute window: when BTC and ETH both qualify, take
only the higher-priced favourite. The two move together, so a second trade doubles the bet rather
than spreading it. The skipped one is still settled and logged (take=False, alt=True) for comparison.
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
RULE = "B2"
# Exit while the market is still open: sell at the held side's best bid when the price is up `tp`¢,
# down `sl`¢, or `trail`¢ below its peak once the peak is at least `arm`¢ above entry. None = off.
# Chosen from the last-minute trade-print backtest; every record also keeps the hold-to-settle P&L.
EXIT = {"tp": None, "sl": None, "trail": None, "arm": 0}
POLL_S = 2
PERIOD = 900


def _c(p):
    return round(float(p) * 100, 2)          # "0.29" → 29.0, not 28.999999999999996


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
    if ya is None or na is None:
        return {"take": False, "why": "empty book"}
    side, ask, depth, avg = ("yes", ya, ydepth, yavg) if ya >= na else ("no", na, ndepth, navg)
    d = {"side": side, "ask": ask, "depth_at_ask": round(depth, 2), "book_avg": avg}
    if not B_LO <= ask < B_HI:
        return {**d, "take": False, "why": f"ask {ask}¢ outside {B_LO}–{B_HI}"}
    if avg is None:
        return {**d, "take": False, "why": f"book too thin for qty"}
    return {**d, "take": True}


def one_per_window(recs):
    """Keep the highest-priced taken record; demote the rest to settled-but-not-taken alternates."""
    taken = sorted((r for r in recs if r.get("take")), key=lambda r: r["ask"], reverse=True)
    for r in taken[1:]:
        r.update(take=False, alt=True, why=f"second trade in window (kept {taken[0]['ticker']})")
    return recs


def best_bid(book, side):
    bids = book.get("orderbook_fp", {}).get(side + "_dollars") or []
    return max((_c(p) for p, _ in bids), default=None)


def exit_hit(entry, peak, bid, ex=EXIT):
    """True when `bid` triggers the exit rule for a position bought at `entry` whose best bid peaked at `peak`."""
    if ex.get("tp") is not None and bid >= entry + ex["tp"]:
        return True
    if ex.get("sl") is not None and bid <= entry - ex["sl"]:
        return True
    return ex.get("trail") is not None and peak >= entry + ex.get("arm", 0) and bid <= peak - ex["trail"]


def watch_exit(rec, close, fetch, clock, sleep, ex=EXIT):
    """Poll the held side's best bid until close; record the exit on the rec if the rule fires."""
    if not any(ex.get(k) is not None for k in ("tp", "sl", "trail")):
        return rec
    entry, peak = round(rec["book_avg"]), None     # peak tracks bids only, so the spread can't trip the trail
    while clock() < close - POLL_S:
        sleep(POLL_S)
        try:
            bid = best_bid(fetch(f"/markets/{rec['ticker']}/orderbook", {"depth": 5}), rec["side"])
        except Exception:                          # noqa: BLE001 — a bad read must never end the shift
            continue
        if bid is None or clock() >= close:
            continue
        peak = bid if peak is None else max(peak, bid)
        if exit_hit(entry, peak, bid, ex):
            rec.update(exit_price=round(bid, 1), exit_secs_before_close=round(close - clock(), 1),
                       exit_peak=round(peak, 1))
            break
    return rec


def pnl_c(price, won, qty):
    """Fee-inclusive P&L in cents for `qty` contracts bought at an average of `price` ¢ (cost kept exact)."""
    return round(((100 if won else 0) - price) * qty - taker_fee_cents(round(price), qty))


def exit_pnl_c(entry, exit_price, qty):
    """Fee-inclusive P&L in cents for buying at `entry` and selling at `exit_price` before settlement."""
    e, x = round(entry), round(exit_price)
    return (x - e) * qty - taker_fee_cents(e, qty) - taker_fee_cents(x, qty)


def settle(rec, result, vwap):
    won = result == rec["side"]
    hold = pnl_c(rec["book_avg"], won, rec["qty"])
    out = {**rec, "result": result, "won": won, "vwap": vwap, "pnl_hold_c": hold,
           "pnl_book_c": exit_pnl_c(rec["book_avg"], rec["exit_price"], rec["qty"])
           if rec.get("exit_price") is not None else hold}
    out["pnl_vwap_c"] = pnl_c(vwap, won, rec["qty"]) if vwap is not None else None
    return out


def next_close(now):
    return (int(now) // PERIOD + 1) * PERIOD


def market_closing(series, close_ts, fetch):
    for m in fetch("/markets", {"series_ticker": series, "status": "open", "limit": 50}).get("markets", []):
        if calibration._ts(m["close_time"]) == close_ts:
            return m
    return None


def _read(s, close, qty, fetch, clock):
    m = market_closing(s, close, fetch)
    if not m:
        return None
    book = fetch(f"/markets/{m['ticker']}/orderbook", {"depth": 50})
    read_at = clock()
    return {"ts": datetime.now(timezone.utc).isoformat(), "ticker": m["ticker"], "close_ts": close,
            "secs_before_close": round(close - read_at, 2), "qty": qty, "rule": RULE, **decide(book, qty)}


def run(hours, log, qty, fetch=_get, clock=time.time, sleep=time.sleep):
    end, pending, last_close = clock() + hours * 3600, [], 0
    while clock() < end:
        close = max(next_close(clock() + AT_S), last_close + PERIOD)   # never the same window twice
        if close > end:                               # don't start a window the shift can't settle
            break
        last_close = close
        sleep(max(0, close - AT_S - clock()))
        window = []
        for s in SERIES:
            for attempt in (1, 2):                    # one fast retry: a backoff would miss T-60
                try:
                    rec = _read(s, close, qty, fetch, clock)
                    if rec:
                        window.append(rec)
                    break
                except Exception as e:                # noqa: BLE001 — a bad read must never end the shift
                    if attempt == 2:
                        print(f"{s}: read failed {e!r}", file=sys.stderr, flush=True)
                        _write(log, {"ts": datetime.now(timezone.utc).isoformat(), "series": s, "close_ts": close,
                                     "rule": RULE, "take": False, "why": f"read failed: {type(e).__name__}"})
                    else:
                        sleep(0.5)
        for rec in one_per_window(window):
            if rec["take"]:
                watch_exit(rec, close, fetch, clock, sleep)
            if rec["take"] or rec.get("alt"):
                pending.append(rec)
            else:
                _write(log, rec)
            print(f"{rec['ticker']:<30} {rec.get('side','-'):>3} ask {rec.get('ask','-')} "
                  f"{'TAKE' if rec['take'] else 'skip: ' + rec.get('why', '')}", flush=True)
        pending = _settle_ready(pending, log, fetch, clock)
    while pending and clock() < end + 1800:          # let the last trades settle
        sleep(30)
        pending = _settle_ready(pending, log, fetch, clock)
    for rec in pending:                               # never drop a decision: log it unsettled
        _write(log, {**rec, "result": None, "why": rec.get("why", "unsettled at end of shift")})


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
        except Exception:                             # noqa: BLE001 — retry next pass
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
    print(f"SHADOW Rule {RULE}: {', '.join(SERIES)}, T-{AT_S}s, ask {B_LO}–{B_HI}¢, qty {a.qty}. No orders are sent.",
          flush=True)
    run(a.hours, a.log, a.qty)
    return 0


if __name__ == "__main__":
    sys.exit(main())
