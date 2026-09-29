"""Paper short-put book on live Robinhood option quotes (the O2 survivor, forward-tested).

Rule (from backtest/options_lab.py, walk-forward picks): after a bullish shadow signal on yesterday's
close, sell a ~30-delta put ~30 days out at today's close. Cash-secured, whole contracts. Buy back at
50% of the credit, at 3x the credit, after 15 sessions or with 7 days left; expiry settles at intrinsic.

What makes it more honest than the backtest:
  - fills: sell at the bid, buy back at the ask (the real spread, not a modeled one)
  - whole contracts: one SPY put secures ~$73k, so on a $100k book it is skipped (logged as put_skip)
  - every fill logs the live implied vol against the symbol's 20-day realized vol: the lab priced
    single names off RV20 x (VIX / SPY RV20), so this ratio is what tells whether that held

Paper only. Nothing here can place an order; it reads quotes that the routine fetched.

Daily flow (after the close, once bars.json has today's bar):
  python -m fund putbook plan            → which quotes to fetch (open contracts + candidate strikes)
  python -m fund putbook apply FILE      → marks, exits, entries; state in ledger/putbook.json
"""
import json
import math
from datetime import date, timedelta

from . import shadow

EQUITIES = ("SPY", "QQQ", "IWM", "NVDA", "AMD", "AAPL", "MSFT", "TSLA")
START_NAV = 100_000.0
TARGET_DELTA, DTE_MIN, DTE_MAX, DTE_TARGET = 0.30, 21, 45, 30
TP, STOP_X, HOLD, MIN_DTE = 0.5, 3.0, 15, 7
# Secured notional per position / in total, as a share of NAV. Whole contracts force this far above the
# research's 5%: one SPY put secures ~$73k, so on $100k even 40% leaves SPY, QQQ, AMD and MSFT unsellable.
POS_CAP, TOTAL_CAP = 0.40, 1.00
MAX_SPREAD = 0.10                      # skip contracts whose spread is > 10% of mid
FEE = 0.03                             # $ per contract per side


def new_state():
    return {"cash": START_NAV, "positions": {}, "closed": [], "log": [], "last_apply": None}


def mid(q):
    return (q["bid"] + q["ask"]) / 2


def nav(st, marks):
    v = st["cash"]
    for p in st["positions"].values():
        m = marks.get(p["instrument_id"])
        v -= p["contracts"] * 100 * (mid(m) if m else p["last_mid"])
    return round(v, 2)


def plan(st, bars, today):
    """Quotes the routine should fetch: open contracts and candidate strikes for new entries."""
    need = [{"symbol": s, "instrument_id": p["instrument_id"]} for s, p in st["positions"].items()]
    cands = []
    for s in EQUITIES:
        if s in st["positions"] or s not in bars:
            continue
        c = bars[s]["closes"]
        if not shadow.signals(c[:-1]):  # causal: yesterday's close decides, today's close trades
            continue
        S = c[-1]
        sd = shadow.sigma(c) * math.sqrt(252) or 0.3
        est = S * math.exp(-0.52 * sd * math.sqrt(DTE_TARGET / 365))  # ~30-delta put
        step = 1 if S < 300 else 5
        base = round(est / step) * step
        cands.append({"symbol": s, "spot": S, "signal": shadow.signals(c[:-1])[0][0],
                      "expiry_window": [(today + timedelta(days=DTE_MIN)).isoformat(),
                                        (today + timedelta(days=DTE_MAX)).isoformat()],
                      "expiry_target": (today + timedelta(days=DTE_TARGET)).isoformat(),
                      "try_strikes": [base + k * step for k in range(-4, 3)]})
    return {"today": today.isoformat(), "open": need, "candidates": cands}


def _close(st, sym, today, px, why, S=None):
    p = st["positions"].pop(sym)
    cost = p["contracts"] * (100 * px + (FEE if why != "expiry" else 0.0))
    st["cash"] -= cost
    pnl = round(p["credit"] - cost, 2)
    rec = {"symbol": sym, "strike": p["strike"], "expiration": p["expiration"], "entry": p["entry"],
           "exit": today.isoformat(), "why": why, "contracts": p["contracts"], "credit": p["credit"],
           "buyback": round(cost, 2), "pnl": pnl}
    if S is not None:
        rec["underlying_at_expiry"] = S
    st["closed"].append(rec)
    st["log"].append({"date": today.isoformat(), "kind": "put_exit", **rec})


def apply(st, bars, quotes, today):
    """quotes = {"marks": {instrument_id: {bid, ask}},
                 "chains": {SYM: [{instrument_id, strike, expiration, bid, ask, delta, iv}]}}."""
    t = today.isoformat()
    if st["last_apply"] == t:
        return {"skipped": "already applied today"}
    marks, events = quotes.get("marks", {}), []

    # 1. exits
    for s in list(st["positions"]):
        p = st["positions"][s]
        exp = date.fromisoformat(p["expiration"])
        if exp < today or (exp == today and bars.get(s, {}).get("last") == t):
            S = bars[s]["closes"][-1]
            _close(st, s, today, max(p["strike"] - S, 0.0), "expiry", S)
            continue
        p["sessions"] += 1
        q = marks.get(p["instrument_id"])
        if not q or q["ask"] <= 0:
            events.append({"symbol": s, "kind": "no_quote"})
            continue
        p["last_mid"] = round(mid(q), 4)
        ask, credit_px = q["ask"], p["credit_px"]
        why = ("target" if ask <= TP * credit_px else "stop" if ask >= STOP_X * credit_px
               else "time" if p["sessions"] >= HOLD or (exp - today).days <= MIN_DTE else None)
        if why:
            _close(st, s, today, ask, why)

    # 2. entries
    for s, chain in quotes.get("chains", {}).items():
        if s in st["positions"] or s not in EQUITIES:
            continue
        ok = [c for c in chain
              if c["bid"] > 0.05 and c["ask"] >= c["bid"] and (c["ask"] - c["bid"]) <= MAX_SPREAD * mid(c)
              and DTE_MIN <= (date.fromisoformat(c["expiration"]) - today).days <= DTE_MAX]
        if not ok:
            st["log"].append({"date": t, "kind": "put_skip", "symbol": s, "reason": "no liquid contract in range"})
            continue
        c = min(ok, key=lambda x: (abs(abs(x["delta"]) - TARGET_DELTA),
                                   abs((date.fromisoformat(x["expiration"]) - today).days - DTE_TARGET)))
        v = nav(st, marks)
        secured = sum(p["strike"] * 100 * p["contracts"] for p in st["positions"].values())
        room = min(POS_CAP * v, TOTAL_CAP * v - secured)
        n = int(room // (c["strike"] * 100))
        if n < 1:
            st["log"].append({"date": t, "kind": "put_skip", "symbol": s, "reason": "size",
                              "one_contract_secures": c["strike"] * 100, "room": round(room, 2)})
            continue
        credit = n * (100 * c["bid"] - FEE)
        st["cash"] += credit
        st["positions"][s] = {"instrument_id": c["instrument_id"], "strike": c["strike"], "expiration": c["expiration"],
                              "contracts": n, "credit_px": c["bid"], "credit": round(credit, 2), "entry": t,
                              "sessions": 0, "last_mid": round(mid(c), 4), "delta": c["delta"]}
        rec = {"date": t, "kind": "put_entry", "symbol": s, "strike": c["strike"], "expiration": c["expiration"],
               "contracts": n, "bid": c["bid"], "ask": c["ask"], "delta": c["delta"], "credit": round(credit, 2)}
        if c.get("iv"):
            rv = shadow.sigma(bars[s]["closes"]) * math.sqrt(252)
            rec["iv"], rec["rv20"], rec["iv_over_rv"] = c["iv"], round(rv, 4), round(c["iv"] / rv, 2)
        st["log"].append(rec)
        events.append(rec)
    st["last_apply"] = t
    return {"nav": nav(st, marks), "events": events}


def summary(st, marks=None):
    wins = [c for c in st["closed"] if c["pnl"] > 0]
    fills = [x for x in st["log"] if x["kind"] == "put_entry" and "iv_over_rv" in x]
    return {"nav": nav(st, marks or {}), "return_pct": round(100 * (nav(st, marks or {}) / START_NAV - 1), 3),
            "open": {s: f"{p['contracts']}x {p['strike']}P {p['expiration']}" for s, p in st["positions"].items()},
            "closed_trades": len(st["closed"]), "win_rate": round(len(wins) / len(st["closed"]), 3) if st["closed"] else None,
            "secured_pct": round(100 * sum(p["strike"] * 100 * p["contracts"] for p in st["positions"].values())
                                 / max(nav(st, marks or {}), 1), 1),
            "avg_iv_over_rv": round(sum(x["iv_over_rv"] for x in fills) / len(fills), 2) if fills else None}


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else new_state()


def save(st, path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
