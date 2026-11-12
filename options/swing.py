"""Daily swing buyer: one long call under the owner's budget when the trend is up and options are cheap.
Rule: research/swing-buyer/RULE.md. Decision support only; nothing here places an order.

Inputs per ticker: a chain JSON (scripts/rh_chain_from_transcript.py shape) for one 21-45 day expiry, daily closes
(oldest first) and the next earnings date if any.
"""
import datetime as dt

from . import mid
from .premium import iv_atm, rv, sma

BUDGET = 200.0
TARGET_DELTA = 0.45
DELTA_BAND = (0.30, 0.60)
MIN_ASK = 0.50
MIN_OI = 500
MAX_SPREAD = 0.10
MAX_IV_RV = 1.00
TAKE_PROFIT = 1.6
STOP = 0.5
TIME_EXIT_DTE = 10


def pick_expiry(expiries, today, dte=(21, 45), target=30):
    """Closest to `target` days out within the window (the earlier on a tie), else None."""
    t = dt.date.fromisoformat(today)
    days = {e: (dt.date.fromisoformat(e) - t).days for e in expiries}
    ok = [e for e in sorted(expiries) if dte[0] <= days[e] <= dte[1]]
    return min(ok, key=lambda e: (abs(days[e] - target), e)) if ok else None


def _spread_ok(c):
    b, a, m = c.get("bid"), c.get("ask"), mid(c)
    if m is None or b is None or b <= 0 or a is None:
        return False
    return (a - b) <= (0.05 if m < 0.50 else MAX_SPREAD * m)


def screen_call(ticker, chain, closes, earnings=None, today=None, budget=BUDGET):
    """Screen one ticker. Returns a dict with status 'pass' or 'fail', the failed reason, and the contract if any."""
    spot = chain.get("spot")
    contracts = chain.get("contracts", [])
    expiry = contracts[0]["expiry"] if contracts else None
    today = today or dt.date.today().isoformat()
    out = {"ticker": ticker, "status": "fail", "reason": "", "spot": spot, "expiry": expiry, "dte": None,
           "strike": None, "ask": None, "bid": None, "delta": None, "oi": None, "cost": None, "breakeven": None,
           "breakeven_pct": None, "iv30": None, "rv20": None, "iv_rv": None, "mom20": None, "score": None,
           "earnings": earnings, "take_profit_at": None, "stop_at": None, "time_exit": None}

    def fail(why):
        out["reason"] = why
        return out

    if not spot or not expiry:
        return fail("no chain")
    out["dte"] = (dt.date.fromisoformat(expiry) - dt.date.fromisoformat(today)).days
    if len(closes) < 51:
        return fail("not enough bars")
    s20, s50 = sma(closes, 20), sma(closes, 50)
    out["mom20"] = (closes[-1] / closes[-21] - 1) * 100
    iv, r = iv_atm(contracts, spot), rv(closes)
    out["iv30"], out["rv20"] = iv, r
    out["iv_rv"] = iv / r if iv and r else None
    if not (closes[-1] > s20 > s50):
        return fail("no uptrend: needs close > 20-day > 50-day average")
    if earnings and earnings <= expiry:
        return fail(f"earnings {earnings} before expiry")
    if out["iv_rv"] is None:
        return fail("no IV/RV")
    if out["iv_rv"] > MAX_IV_RV:
        return fail(f"options not cheap: IV/RV {out['iv_rv']:.2f} > {MAX_IV_RV:.2f}")
    ok = [c for c in contracts if c["type"] == "call" and c.get("delta") is not None
          and DELTA_BAND[0] <= c["delta"] <= DELTA_BAND[1] and c.get("ask") is not None
          and MIN_ASK <= c["ask"] and c["ask"] * 100 <= budget and (c.get("oi") or 0) >= MIN_OI and _spread_ok(c)]
    if not ok:
        return fail(f"no call fits: delta {DELTA_BAND[0]}-{DELTA_BAND[1]}, ask ${MIN_ASK:.2f}-${budget / 100:.2f}, "
                    f"OI >= {MIN_OI}, tight spread")
    c = min(ok, key=lambda c: (abs(c["delta"] - TARGET_DELTA), c["strike"]))
    out.update(status="pass", strike=c["strike"], ask=c["ask"], bid=c["bid"], delta=c["delta"], oi=c.get("oi"),
               cost=round(c["ask"] * 100, 2), breakeven=round(c["strike"] + c["ask"], 2))
    out["breakeven_pct"] = (out["breakeven"] / spot - 1) * 100
    out["score"] = out["mom20"] / out["iv_rv"]
    out["take_profit_at"] = round(c["ask"] * TAKE_PROFIT, 2)
    out["stop_at"] = round(c["ask"] * STOP, 2)
    out["time_exit"] = (dt.date.fromisoformat(expiry) - dt.timedelta(days=TIME_EXIT_DTE)).isoformat()
    return out


def rank(results):
    """Passing results by score, highest first, with rank 1 (pick) and 2 (backup); failures after, unranked."""
    passed = sorted((r for r in results if r["status"] == "pass"), key=lambda r: -r["score"])
    for i, r in enumerate(passed, 1):
        r["rank"] = i if i <= 2 else None
    failed = sorted((r for r in results if r["status"] != "pass"), key=lambda r: r["ticker"])
    for r in failed:
        r["rank"] = None
    return passed + failed


def exit_check(pick, bid, today):
    """The exit rule a pick has hit at this bid, or None."""
    if bid is not None and bid >= pick["take_profit_at"]:
        return f"take profit: bid {bid:.2f} >= {pick['take_profit_at']:.2f}"
    if bid is not None and bid <= pick["stop_at"]:
        return f"stop: bid {bid:.2f} <= {pick['stop_at']:.2f}"
    if today >= pick["time_exit"]:
        return f"time exit: {TIME_EXIT_DTE} days to expiry"
    return None


def open_picks(rows):
    closed = {r["close_of"] for r in rows if r.get("close_of")}
    return [r for r in rows if not r.get("close_of") and r["id"] not in closed]
