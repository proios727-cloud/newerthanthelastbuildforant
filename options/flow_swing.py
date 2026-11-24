"""Flow-confirmed swing call: a pre-registered paper rule (research/flow-swing/RULE.md).

Signal (all must hold, read from the fallback flow board, options/fallback.py):
- options lean to calls: call_avg >= MIN_RATIO x put_avg, with at least MIN_ACTIVE call contracts trading above their
  open interest;
- price confirms: the stock is at least MIN_ABOVE_LOW % above its day low when the board is built (built at or after
  11:00 ET, so the low has had time to hold).
Ranking: call_avg / put_avg, highest first; one pick a day.
Contract (needs a quoted chain; without one the signal is logged as a candidate, never as a trade): a call expiring
14-30 days out, delta 0.30-0.50, ask $0.50-$2.00, open interest >= 500, spread <= 10% of mid. Closest to 0.40 delta.
Exits mirror the swing buyer: +60% / -50% on the bid, time exit 7 days before expiry.
Decision support only; nothing here places an order.
"""
import datetime as dt

from .swing import MIN_OI, _spread_ok

MIN_RATIO = 2.0
MIN_ACTIVE = 10
MIN_ABOVE_LOW = 1.0
DTE = (14, 30)
DELTA_BAND = (0.30, 0.50)
TARGET_DELTA = 0.40
MIN_ASK, MAX_ASK = 0.50, 2.00
TAKE_PROFIT, STOP, TIME_EXIT_DTE = 1.6, 0.5, 7


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def candidates(rows):
    """Board rows that pass the signal, ranked by call/put ratio. Each gets 'ratio'; failures are dropped."""
    out = []
    for r in rows:
        c, p = _num(r.get("call_avg")) or 0.0, _num(r.get("put_avg")) or 0.0
        active, above = _num(r.get("call_active")) or 0, _num(r.get("above_low_pct"))
        if c <= 0 or above is None:
            continue
        ratio = c / p if p > 0 else float("inf")
        if ratio >= MIN_RATIO and active >= MIN_ACTIVE and above >= MIN_ABOVE_LOW:
            out.append(dict(r, ratio=round(ratio, 2) if ratio != float("inf") else 999.0))
    out.sort(key=lambda r: -r["ratio"])
    return out


def pick_contract(chain, today):
    """The rule's call from a quoted chain ({"contracts": [...]}, rh_chain_from_transcript shape), or None."""
    t = dt.date.fromisoformat(today)
    ok = []
    for c in chain.get("contracts", []):
        if c.get("type") != "call" or c.get("delta") is None or c.get("ask") is None:
            continue
        dte = (dt.date.fromisoformat(c["expiry"]) - t).days
        if (DTE[0] <= dte <= DTE[1] and DELTA_BAND[0] <= c["delta"] <= DELTA_BAND[1]
                and MIN_ASK <= c["ask"] <= MAX_ASK and (c.get("oi") or 0) >= MIN_OI and _spread_ok(c)):
            ok.append(c)
    if not ok:
        return None
    c = min(ok, key=lambda c: (abs(c["delta"] - TARGET_DELTA), c["expiry"], c["strike"]))
    exp = dt.date.fromisoformat(c["expiry"])
    return {"expiry": c["expiry"], "strike": c["strike"], "ask": c["ask"], "bid": c["bid"], "delta": c["delta"],
            "oi": c.get("oi"), "cost": round(c["ask"] * 100, 2),
            "take_profit_at": round(c["ask"] * TAKE_PROFIT, 2), "stop_at": round(c["ask"] * STOP, 2),
            "time_exit": (exp - dt.timedelta(days=TIME_EXIT_DTE)).isoformat()}
