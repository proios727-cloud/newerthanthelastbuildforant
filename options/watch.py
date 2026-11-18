"""Watchlist scoring: which liquid option chains have unusual action today.

Two separate grades per ticker, from the chain snapshots the daily runs already save:
- liquidity (can you get in and out cleanly): the at-the-money spread as a share of mid, open interest across the
  snapshot's strikes, and the day's option volume;
- action (is something unusual happening): option volume against the ticker's own recent level, volume against open
  interest (a sign new positions are opening), the call/put lean, and the change in at-the-money IV.
Volume is cumulative through the day, snapshots are taken at different times and cover different strikes, so relative
volume compares full-session volume per contract of open interest with the ticker's own median over its last 10 snapshots. A ticker that fails liquidity is dropped from the board however busy it is.
"""
import datetime as dt
import statistics
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
OPEN, CLOSE = dt.time(9, 30), dt.time(16, 0)
BUDGET = 200.0  # dollars for one call


def session_frac(asof):
    """Share of the regular session elapsed at an ISO UTC time, floored at 10% so an early snapshot is not blown up."""
    t = dt.datetime.fromisoformat(asof[:19]).replace(tzinfo=dt.timezone.utc).astimezone(ET)  # asof is UTC
    start = dt.datetime.combine(t.date(), OPEN, ET)
    total = (dt.datetime.combine(t.date(), CLOSE, ET) - start).total_seconds()
    return min(1.0, max(0.1, (t - start).total_seconds() / total))


def _mid(c):
    b, a = c.get("bid"), c.get("ask")
    return (b + a) / 2 if b is not None and a is not None and a > 0 else None


def atm(snap):
    """The contract nearest the money (calls preferred on a tie), or None."""
    cs = [c for c in snap.get("contracts", []) if _mid(c)]
    if not cs:
        return None
    s = snap["spot"]
    return min(cs, key=lambda c: (abs(c["strike"] - s), c["type"] != "call"))


def pace(snap):
    """Full-session volume pace per contract of open interest. Dividing by open interest keeps days comparable when a
    snapshot covers a different set of strikes; scaling by the session elapsed keeps early and late snapshots comparable."""
    cs = snap.get("contracts", [])
    oi = sum(c.get("oi") or 0 for c in cs)
    return sum(c.get("volume") or 0 for c in cs) / session_frac(snap["asof"]) / oi if oi else 0.0


def budget_call(snap, budget=BUDGET):
    """Cheapest call with delta 0.30-0.60 whose ask fits the budget: (strike, ask) or None."""
    ok = [c for c in snap.get("contracts", []) if c["type"] == "call" and c.get("ask") and
          0.30 <= abs(c.get("delta") or 0) <= 0.60 and c["ask"] * 100 <= budget]
    if not ok:
        return None
    c = min(ok, key=lambda c: c["ask"])
    return c["strike"], c["ask"]


def liquidity(snap):
    """(grade, spread_pct, oi, volume). A: spread <= 5% of mid, OI >= 1,000, volume >= 100. B: <= 10%, 500, 25."""
    c = atm(snap)
    oi = sum(c2.get("oi") or 0 for c2 in snap.get("contracts", []))
    vol = sum(c2.get("volume") or 0 for c2 in snap.get("contracts", []))
    if c is None:
        return "F", None, oi, vol
    m = _mid(c)
    spread = (c["ask"] - c["bid"]) / m
    if spread <= 0.05 and oi >= 1000 and vol >= 100:
        g = "A"
    elif spread <= 0.10 and oi >= 500 and vol >= 25:
        g = "B"
    else:
        g = "F"
    return g, spread, oi, vol


def score(today, history):
    """One board row from today's snapshot and the ticker's earlier snapshots (oldest first, same folder)."""
    grade, spread, oi, vol = liquidity(today)
    base = [pace(h) for h in history[-10:]]
    rel = pace(today) / statistics.median(base) if base and statistics.median(base) > 0 else None
    vol_oi = vol / oi if oi else None
    calls = sum(c.get("volume") or 0 for c in today["contracts"] if c["type"] == "call")
    puts = sum(c.get("volume") or 0 for c in today["contracts"] if c["type"] == "put")
    # The lean only means something when the snapshot covers both sides about evenly (premium snapshots are mostly puts).
    n_call = sum(c["type"] == "call" for c in today["contracts"])
    has_both = 0.3 <= n_call / len(today["contracts"]) <= 0.7
    call_share = calls / (calls + puts) if has_both and calls + puts else None
    a_now, a_prev = atm(today), (atm(history[-1]) if history else None)
    iv_chg = (a_now["iv"] - a_prev["iv"]) * 100 if a_now and a_prev and a_now.get("iv") and a_prev.get("iv") else None
    # Action: relative volume dominates; fresh positioning and an IV jump add to it.
    action = (rel or 1.0) + 2 * (vol_oi or 0) + 0.1 * abs(iv_chg or 0)
    tags = []
    if rel is not None and rel >= 2:
        tags.append(f"{rel:.1f}x volume" + (" (short history)" if len(base) < 5 else ""))
    if vol_oi is not None and vol_oi >= 0.5:
        tags.append("new positions (vol/OI)")
    if iv_chg is not None and abs(iv_chg) >= 3:
        tags.append(f"IV {iv_chg:+.0f} pt")
    if call_share is not None and (call_share >= 0.65 or call_share <= 0.35):
        tags.append("call-heavy" if call_share >= 0.65 else "put-heavy")
    bc = budget_call(today)
    return {"ticker": today["symbol"], "liq": grade, "spread_pct": spread, "oi": oi, "volume": vol,
            "rel_volume": rel, "vol_oi": vol_oi, "call_share": call_share, "iv_chg_pts": iv_chg,
            "action": round(action, 3), "busy": "yes" if tags else "no", "signals": "; ".join(tags) or "quiet",
            "budget_call": f"{today['symbol']} {bc[0]:g}C ${bc[1] * 100:,.0f}" if bc else "",
            "spot": today["spot"], "asof": today["asof"], "baseline_days": len(base)}


def board(rows, held=(), new=()):
    """Liquid rows (A or B) sorted by action, most unusual first, tagged held/new."""
    out = []
    for r in rows:
        if r["liq"] == "F":
            continue
        r = dict(r, source="new" if r["ticker"] in new else "core", held="yes" if r["ticker"] in held else "no")
        out.append(r)
    out.sort(key=lambda r: -r["action"])
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
