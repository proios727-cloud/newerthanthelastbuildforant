"""Paper put-credit-spread book sized for a $500 account (the defined-risk version of the put book).

Same signal and final pass as fund/putbook.py; the difference is the structure and the sizing:
  - sell the ~30-delta put ~30 days out and buy a lower put in the same expiry, at most $2 wide, one spread open at a time
  - max loss = width x 100 - credit, and that amount is reserved from cash, so the book can never owe more
  - pick the width with the best credit / max loss that still collects >= 20% of the width and fits the room
  - exits: buy back at 50% of the credit, at 2x the credit, after 15 sessions or with 7 days left, or the
    session before earnings; expiry settles at intrinsic (short intrinsic - long intrinsic)

Fills are at the natural price: open = short bid - long ask, close = short ask - long bid. Paper only; a
real account needs options level 3 for spreads. Nothing here can place an order.
"""
import json
from datetime import date

from . import putbook
from .putbook import DTE_MAX, DTE_MIN, DTE_TARGET, EQUITIES, FEE, HOLD, MIN_DTE, TARGET_DELTA, mid

START_NAV = 500.0
TP, STOP_X = 0.5, 2.0
POS_RISK = 0.20                        # max loss per spread as a share of NAV (~$100 on $500)
MAX_OPEN = 1                           # one spread at a time (docs/research/500-growth.md)
MAX_WIDTH = 2.0                        # 1- to 2-wide only: 5-wide risks ~81% of a $500 account
MIN_CREDIT_FRAC = 0.20                 # collect at least 20% of the width
MAX_LEG_SPREAD = 0.10                  # each leg's bid-ask <= max(10% of mid, $0.05)


def new_state():
    return {"cash": START_NAV, "positions": {}, "closed": [], "log": [], "last_apply": None}


def _liquid(c):
    return c["bid"] >= 0 and c["ask"] >= c["bid"] and c["ask"] > 0 and \
        (c["ask"] - c["bid"]) <= max(MAX_LEG_SPREAD * mid(c), 0.05)


def debit_mid(p, marks):
    s, l = marks.get(p["short_id"]), marks.get(p["long_id"])
    return mid(s) - mid(l) if s and l else p["last_debit"]


def reserved(st):
    return sum(p["max_loss"] for p in st["positions"].values())


def nav(st, marks):
    """Cash (including reserved collateral) minus the cost to close every spread at mid."""
    return round(st["cash"] - sum(p["contracts"] * 100 * debit_mid(p, marks) for p in st["positions"].values()), 2)


def open_legs(st):
    return [{"symbol": s, "instrument_id": i} for s, p in st["positions"].items() for i in (p["short_id"], p["long_id"])]


def _close(st, sym, today, px, why, S=None):
    p = st["positions"].pop(sym)
    cost = p["contracts"] * (100 * px + (2 * FEE if why != "expiry" else 0.0))
    st["cash"] -= cost
    rec = {"symbol": sym, "short": p["short_strike"], "long": p["long_strike"], "expiration": p["expiration"],
           "entry": p["entry"], "exit": today.isoformat(), "why": why, "contracts": p["contracts"],
           "credit": p["credit"], "buyback": round(cost, 2), "pnl": round(p["credit"] - cost, 2), "max_loss": p["max_loss"]}
    if S is not None:
        rec["underlying_at_expiry"] = S
    st["closed"].append(rec)
    st["log"].append({"date": today.isoformat(), "kind": "spread_exit", **rec})


def best_spread(chain, today, room):
    """(short, long, width, credit_px, max_loss_per_contract) or None."""
    ok = [c for c in chain if _liquid(c) and DTE_MIN <= (date.fromisoformat(c["expiration"]) - today).days <= DTE_MAX]
    shorts = [c for c in ok if c["bid"] > 0.05 and c.get("delta") is not None]
    if not shorts:
        return None
    short = min(shorts, key=lambda x: (abs(abs(x["delta"]) - TARGET_DELTA),
                                       abs((date.fromisoformat(x["expiration"]) - today).days - DTE_TARGET)))
    best = None
    for lg in ok:
        if lg["expiration"] != short["expiration"] or lg["strike"] >= short["strike"]:
            continue
        width = round(short["strike"] - lg["strike"], 2)
        credit = round(short["bid"] - lg["ask"], 2)
        if width > MAX_WIDTH or credit < MIN_CREDIT_FRAC * width:
            continue
        max_loss = round(width * 100 - credit * 100 + 2 * FEE, 2)
        if max_loss > room:
            continue
        key = (credit * 100 / max_loss, -width)
        if best is None or key > best[0]:
            best = (key, (short, lg, width, credit, max_loss))
    return best[1] if best else None


def apply(st, bars, quotes, today, judge_fn=None):
    t = today.isoformat()
    if st["last_apply"] == t:
        return {"skipped": "already applied today"}
    marks, events = quotes.get("marks", {}), []

    for s in list(st["positions"]):
        p = st["positions"][s]
        exp = date.fromisoformat(p["expiration"])
        if exp < today or (exp == today and bars.get(s, {}).get("last") == t):
            S = bars[s]["closes"][-1]
            _close(st, s, today, max(p["short_strike"] - S, 0.0) - max(p["long_strike"] - S, 0.0), "expiry", S)
            continue
        p["sessions"] += 1
        qs, ql = marks.get(p["short_id"]), marks.get(p["long_id"])
        if not qs or not ql or qs["ask"] <= 0:
            events.append({"symbol": s, "kind": "no_quote"})
            continue
        p["last_debit"] = round(mid(qs) - mid(ql), 4)
        debit = max(round(qs["ask"] - ql["bid"], 4), 0.0)
        why = ("earnings" if putbook.earnings_tomorrow(quotes, s, today)
               else "target" if debit <= TP * p["credit_px"]
               else "stop" if debit >= STOP_X * p["credit_px"]
               else "time" if p["sessions"] >= HOLD or (exp - today).days <= MIN_DTE else None)
        if why:
            _close(st, s, today, debit, why)

    for s, chain in quotes.get("chains", {}).items():
        if s in st["positions"] or s not in EQUITIES:
            continue
        if len(st["positions"]) >= MAX_OPEN:
            break
        v = nav(st, marks)
        room = min(POS_RISK * v, v - reserved(st))
        pick = best_spread(chain, today, room)
        if not pick:
            st["log"].append({"date": t, "kind": "spread_skip", "symbol": s,
                              "reason": "no liquid spread with >=20% credit inside the risk room", "room": round(room, 2)})
            continue
        short, lg, width, credit_px, max_loss = pick
        skip = putbook.final_pass(quotes, s, today, short["expiration"], judge_fn)
        if skip:
            st["log"].append({"date": t, "kind": "spread_skip", "symbol": s, **skip})
            continue
        n = max(1, int(room // max_loss))
        credit = round(n * (100 * credit_px - 2 * FEE), 2)
        st["cash"] += credit
        st["positions"][s] = {"short_id": short["instrument_id"], "long_id": lg["instrument_id"],
                              "short_strike": short["strike"], "long_strike": lg["strike"], "width": width,
                              "expiration": short["expiration"], "contracts": n, "credit_px": credit_px,
                              "credit": credit, "max_loss": round(n * max_loss, 2), "entry": t, "sessions": 0,
                              "last_debit": round(mid(short) - mid(lg), 4), "delta": short["delta"]}
        rec = {"date": t, "kind": "spread_entry", "symbol": s, "short": short["strike"], "long": lg["strike"],
               "expiration": short["expiration"], "contracts": n, "credit": credit, "max_loss": round(n * max_loss, 2),
               "delta": short["delta"]}
        st["log"].append(rec)
        events.append(rec)
    st["last_apply"] = t
    return {"nav": nav(st, marks), "events": events}


def summary(st, marks=None):
    marks = marks or {}
    wins = [c for c in st["closed"] if c["pnl"] > 0]
    v = nav(st, marks)
    return {"nav": v, "return_pct": round(100 * (v / START_NAV - 1), 3),
            "open": {s: f"{p['contracts']}x {p['short_strike']}/{p['long_strike']}P {p['expiration']}"
                     for s, p in st["positions"].items()},
            "closed_trades": len(st["closed"]),
            "win_rate": round(len(wins) / len(st["closed"]), 3) if st["closed"] else None,
            "at_risk_pct": round(100 * reserved(st) / max(v, 1), 1)}


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else new_state()


save = putbook.save
