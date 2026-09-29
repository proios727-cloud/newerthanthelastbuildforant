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
SHORT_DELTA = (0.16, 0.35)             # short-leg delta band; nearest to TARGET_DELTA (0.30) tried first
MAX_WIDTH = 2.0                        # 1- to 2-wide only: 5-wide risks ~81% of a $500 account
MIN_CREDIT_FRAC = 0.20                 # collect at least 20% of the width
STRATEGY_ID = "pcs12-v1"               # 1-2 wide put credit spread; bump when the rules change
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
    """Both legs of every open spread and every ghost (a JEV-vetoed spread, tracked for scoring)."""
    return [{"symbol": s, "instrument_id": i} for book in (st["positions"], st.get("ghosts", {}))
            for s, p in book.items() for i in (p["short_id"], p["long_id"])]


def _close(st, sym, today, px, why, S=None, ghost=False, expected=None):
    p = (st["ghosts"] if ghost else st["positions"]).pop(sym)
    cost = p["contracts"] * (100 * px + (2 * FEE if why != "expiry" else 0.0))
    if not ghost:
        st["cash"] -= cost
    rec = {"symbol": sym, "short": p["short_strike"], "long": p["long_strike"], "expiration": p["expiration"],
           "entry": p["entry"], "exit": today.isoformat(), "why": why, "contracts": p["contracts"],
           "credit": p["credit"], "buyback": round(cost, 2), "pnl": round(p["credit"] - cost, 2), "max_loss": p["max_loss"],
           "jev_p": p.get("jev_p"), "jev_mode": p.get("jev_mode"), "jev_answers": p.get("jev_answers"),
           "strategy_id": p.get("strategy_id"), "decision_id": p.get("decision_id"),
           "entry_slip": p.get("entry_slip"), "exit_slip": round(px - expected, 4) if expected is not None else None}
    if S is not None:
        rec["underlying_at_expiry"] = S
    st.setdefault("ghost_closed" if ghost else "closed", []).append(rec)
    st["log"].append({"date": today.isoformat(), "kind": "spread_ghost_exit" if ghost else "spread_exit", **rec})


def best_spread(chain, today, room):
    """(short, long, width, credit_px, max_loss_per_contract) or None.

    Shorts are tried nearest-to-30-delta first, inside the 16-35 delta band; the first short with any valid
    long leg wins, and among its longs the best credit per dollar of max loss (ties: narrower)."""
    ok = [c for c in chain if _liquid(c) and DTE_MIN <= (date.fromisoformat(c["expiration"]) - today).days <= DTE_MAX]
    shorts = sorted((c for c in ok if c["bid"] > 0.05 and c.get("delta") is not None
                     and SHORT_DELTA[0] <= abs(c["delta"]) <= SHORT_DELTA[1]),
                    key=lambda x: (abs(abs(x["delta"]) - TARGET_DELTA),
                                   abs((date.fromisoformat(x["expiration"]) - today).days - DTE_TARGET)))
    for short in shorts:
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
        if best:
            return best[1]
    return None


def apply(st, bars, quotes, today, judge_fn=None, kill=None):
    t = today.isoformat()
    if st["last_apply"] == t:
        return {"skipped": "already applied today"}
    marks, events = quotes.get("marks", {}), []

    for ghost in (False, True):          # real spreads, then ghosts under the identical rules
        book = st.get("ghosts", {}) if ghost else st["positions"]
        for s in list(book):
            p = book[s]
            exp = date.fromisoformat(p["expiration"])
            if exp < today or (exp == today and bars.get(s, {}).get("last") == t):
                S = bars[s]["closes"][-1]
                _close(st, s, today, max(p["short_strike"] - S, 0.0) - max(p["long_strike"] - S, 0.0), "expiry", S, ghost)
                continue
            p["sessions"] += 1
            qs, ql = marks.get(p["short_id"]), marks.get(p["long_id"])
            if not qs or not ql or qs["ask"] <= 0:
                events.append({"symbol": s, "kind": "no_quote", "ghost": ghost})
                continue
            p["last_debit"] = round(mid(qs) - mid(ql), 4)
            debit = max(round(qs["ask"] - ql["bid"], 4), 0.0)
            why = ("earnings" if putbook.earnings_tomorrow(quotes, s, today)
                   else "target" if debit <= TP * p["credit_px"]
                   else "stop" if debit >= STOP_X * p["credit_px"]
                   else "time" if p["sessions"] >= HOLD or (exp - today).days <= MIN_DTE else None)
            if why:
                _close(st, s, today, debit, why, ghost=ghost, expected=mid(qs) - mid(ql))

    if kill:
        st["log"].append({"date": t, "kind": "spread_skip", "symbol": "*", "reason": f"kill switch: {kill}"})
    for s, chain in ({} if kill else quotes.get("chains", {})).items():
        if s in st["positions"] or s in st.get("ghosts", {}) or s not in EQUITIES:
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
        skip, verdict = putbook.final_pass(quotes, s, today, short["expiration"], judge_fn,
                                           putbook.context(bars, s, [short, lg], today,
                                                           f"sell 1 put credit spread, {width:g} wide"))
        n = max(1, int(room // max_loss))
        credit = round(n * (100 * credit_px - 2 * FEE), 2)
        v = verdict or {}
        exp_px = round(mid(short) - mid(lg), 4)
        pos = {"short_id": short["instrument_id"], "long_id": lg["instrument_id"],
               "short_strike": short["strike"], "long_strike": lg["strike"], "width": width,
               "expiration": short["expiration"], "contracts": n, "credit_px": credit_px,
               "credit": credit, "max_loss": round(n * max_loss, 2), "entry": t, "sessions": 0,
               "last_debit": exp_px, "delta": short["delta"],
               "strategy_id": STRATEGY_ID, "decision_id": putbook.decision_id(STRATEGY_ID, today, s),
               "model_version": v.get("model"), "expected_px": exp_px, "fill_px": credit_px,
               "entry_slip": round(exp_px - credit_px, 4),
               "jev_p": v.get("p"), "jev_mode": v.get("mode"), "jev_answers": v.get("answers"),
               "jev_escalate": v.get("escalate") or []}
        if skip:
            st["log"].append({"date": t, "kind": "spread_skip", "symbol": s, **skip})
            if putbook.ghosted(skip):
                st.setdefault("ghosts", {})[s] = pos
                st["log"].append({"date": t, "kind": "spread_ghost_entry", "symbol": s, "short": short["strike"],
                                  "long": lg["strike"], "credit": credit, "jev_p": pos["jev_p"]})
            continue
        st["cash"] += credit
        st["positions"][s] = pos
        rec = {"date": t, "kind": "spread_entry", "symbol": s, "short": short["strike"], "long": lg["strike"],
               "expiration": short["expiration"], "contracts": n, "credit": credit, "max_loss": round(n * max_loss, 2),
               "delta": short["delta"], "decision_id": pos["decision_id"], "expected_px": exp_px,
               "entry_slip": pos["entry_slip"], "jev_escalate": pos["jev_escalate"]}
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
            "at_risk_pct": round(100 * reserved(st) / max(v, 1), 1),
            "jev_ghosts_open": len(st.get("ghosts", {})), "jev_ghosts_closed": len(st.get("ghost_closed", [])),
            "slippage_pct_of_credit": putbook.slippage_pct(st["closed"])}


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else new_state()


save = putbook.save
