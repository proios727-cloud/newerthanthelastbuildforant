"""Paper short-put book on live Robinhood option quotes (the O2 survivor, forward-tested).

Rule (from backtest/options_lab.py, walk-forward picks): after a bullish shadow signal on yesterday's
close, sell a ~30-delta put ~30 days out at today's close. Cash-secured, whole contracts. Buy back at
50% of the credit, at 3x the credit, after 15 sessions or with 7 days left; expiry settles at intrinsic.

What makes it more honest than the backtest:
  - fills: sell at the bid, buy back at the ask (the real spread, not a modeled one)
  - whole contracts: one SPY put secures ~$73k, so on a $100k book it is skipped (logged as put_skip)
  - every fill logs the live implied vol against the symbol's 20-day realized vol: the lab priced
    single names off RV20 x (VIX / SPY RV20), so this ratio is what tells whether that held

Final pass before any entry (after the contract is chosen and sized):
  1. earnings gate (code): no new put when the company reports before the planned exit (the earlier of
     15 sessions ≈ 21 days and 7 days before expiry); an open put is bought back the session before a report
  2. JEV gate (TypeSafe): `judge_fn(symbol, headlines)` -> (rule, detail) or None. The CLI wires it to
     fund/catalyst.py; a live, confident "material headline risk" answer blocks the sale. Without a
     TypeSafe key the stub answers never count as confident, so the gate is logged but never vetoes.

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
    need = [{"symbol": s, "instrument_id": p["instrument_id"]}
            for book in (st["positions"], st.get("ghosts", {})) for s, p in book.items()]
    cands = []
    for s in EQUITIES:
        if s in st["positions"] or s in st.get("ghosts", {}) or s not in bars:
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
                      "try_strikes": [base + k * step for k in range(-4, 3)],
                      # long legs for the $500 spread book: 1, 2.5 and 5 below the three central strikes
                      "spread_strikes": sorted({round(base + k * step - w, 2) for k in (-1, 0, 1) for w in (1, 2.5, 5)}
                                               - {base + k * step for k in range(-4, 3)})})
    return {"today": today.isoformat(), "open": need, "candidates": cands}


def _close(st, sym, today, px, why, S=None, ghost=False):
    """Close a position, or a ghost: a sale JEV vetoed, tracked with no cash so its outcome can be scored."""
    p = (st["ghosts"] if ghost else st["positions"]).pop(sym)
    cost = p["contracts"] * (100 * px + (FEE if why != "expiry" else 0.0))
    if not ghost:
        st["cash"] -= cost
    pnl = round(p["credit"] - cost, 2)
    rec = {"symbol": sym, "strike": p["strike"], "expiration": p["expiration"], "entry": p["entry"],
           "exit": today.isoformat(), "why": why, "contracts": p["contracts"], "credit": p["credit"],
           "buyback": round(cost, 2), "pnl": pnl, "jev_p": p.get("jev_p"), "jev_mode": p.get("jev_mode")}
    if S is not None:
        rec["underlying_at_expiry"] = S
    st.setdefault("ghost_closed" if ghost else "closed", []).append(rec)
    st["log"].append({"date": today.isoformat(), "kind": "put_ghost_exit" if ghost else "put_exit", **rec})


def final_pass(quotes, sym, today, expiration, judge_fn=None):
    """Earnings gate, then JEV. Returns (skip, verdict), shared with the spread book.

    skip is a record ({"reason": ..., ...}) or None. verdict is {"p", "mode"} from the judge (None when it
    was not asked). judge_fn(sym, headlines) returns a veto (rule, detail), None, or
    {"veto": (rule, detail) | None, "p": P(material), "mode": "live" | "stub" | "error"}."""
    ev = quotes.get("events", {}).get(sym, {})
    er = ev.get("earnings_date")
    planned_exit = min(date.fromisoformat(expiration) - timedelta(days=MIN_DTE), today + timedelta(days=21))
    if er and today.isoformat() < er <= planned_exit.isoformat():
        return {"reason": "earnings before planned exit", "earnings_date": er,
                "planned_exit": planned_exit.isoformat()}, None
    if not judge_fn:
        return None, None
    r = judge_fn(sym, ev.get("headlines", []))
    veto, verdict = (r.get("veto"), {"p": r.get("p"), "mode": r.get("mode")}) if isinstance(r, dict) \
        else (r, {"p": None, "mode": None})
    if veto:
        return {"reason": f"jev {veto[0]}", "detail": veto[1], "jev_p": verdict["p"], "jev_mode": verdict["mode"]}, verdict
    return None, verdict


def ghosted(skip):
    """A JEV judgment (not an outage) blocked the sale: track it as a ghost so the veto can be scored."""
    return bool(skip) and skip["reason"].startswith("jev ") and skip.get("jev_mode") != "error"


def earnings_tomorrow(quotes, sym, today):
    er = quotes.get("events", {}).get(sym, {}).get("earnings_date")
    return bool(er) and 0 <= (date.fromisoformat(er) - today).days <= 1


def apply(st, bars, quotes, today, judge_fn=None):
    """quotes = {"marks": {instrument_id: {bid, ask}},
                 "chains": {SYM: [{instrument_id, strike, expiration, bid, ask, delta, iv}]},
                 "events": {SYM: {"earnings_date": "YYYY-MM-DD" | None, "headlines": [str, ...]}}}."""
    t = today.isoformat()
    if st["last_apply"] == t:
        return {"skipped": "already applied today"}
    marks, events = quotes.get("marks", {}), []

    # 1. exits: real positions, then ghosts (vetoed sales) under the identical rules
    for ghost in (False, True):
        book = st.get("ghosts", {}) if ghost else st["positions"]
        for s in list(book):
            p = book[s]
            exp = date.fromisoformat(p["expiration"])
            if exp < today or (exp == today and bars.get(s, {}).get("last") == t):
                S = bars[s]["closes"][-1]
                _close(st, s, today, max(p["strike"] - S, 0.0), "expiry", S, ghost)
                continue
            p["sessions"] += 1
            q = marks.get(p["instrument_id"])
            if q and q["ask"] > 0 and earnings_tomorrow(quotes, s, today):
                p["last_mid"] = round(mid(q), 4)
                _close(st, s, today, q["ask"], "earnings", ghost=ghost)
                continue
            if not q or q["ask"] <= 0:
                events.append({"symbol": s, "kind": "no_quote", "ghost": ghost})
                continue
            p["last_mid"] = round(mid(q), 4)
            ask, credit_px = q["ask"], p["credit_px"]
            why = ("target" if ask <= TP * credit_px else "stop" if ask >= STOP_X * credit_px
                   else "time" if p["sessions"] >= HOLD or (exp - today).days <= MIN_DTE else None)
            if why:
                _close(st, s, today, ask, why, ghost=ghost)

    # 2. entries
    for s, chain in quotes.get("chains", {}).items():
        if s in st["positions"] or s in st.get("ghosts", {}) or s not in EQUITIES:
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
        skip, verdict = final_pass(quotes, s, today, c["expiration"], judge_fn)
        credit = n * (100 * c["bid"] - FEE)
        pos = {"instrument_id": c["instrument_id"], "strike": c["strike"], "expiration": c["expiration"],
               "contracts": n, "credit_px": c["bid"], "credit": round(credit, 2), "entry": t,
               "sessions": 0, "last_mid": round(mid(c), 4), "delta": c["delta"],
               "jev_p": (verdict or {}).get("p"), "jev_mode": (verdict or {}).get("mode")}
        if skip:
            st["log"].append({"date": t, "kind": "put_skip", "symbol": s, **skip})
            if ghosted(skip):
                st.setdefault("ghosts", {})[s] = pos
                st["log"].append({"date": t, "kind": "put_ghost_entry", "symbol": s, "strike": c["strike"],
                                  "expiration": c["expiration"], "credit": round(credit, 2), "jev_p": pos["jev_p"]})
            continue
        st["cash"] += credit
        st["positions"][s] = pos
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
            "avg_iv_over_rv": round(sum(x["iv_over_rv"] for x in fills) / len(fills), 2) if fills else None,
            "jev_ghosts_open": len(st.get("ghosts", {})), "jev_ghosts_closed": len(st.get("ghost_closed", []))}


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else new_state()


def save(st, path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
