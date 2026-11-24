"""Fallback option-activity board for days the Robinhood connector is down.

Inputs the desk can still reach without Robinhood:
- Alpha Vantage REALTIME_VOLUME_OPEN_INTEREST_RATIO: one row per contract with today's volume / open interest
  (no prices, no bid/ask, no greeks);
- TradingView quotes: last, change %, day high and low.

From those it scores, per ticker, where today's option trading is concentrated and which side leans:
- call_avg / put_avg: mean volume/OI over contracts expiring after today and by `max_expiry`, with strikes within
  `band` of spot;
- call_active / put_active: how many of those contracts traded more than their open interest (ratio > 1);
- lean: "calls" when call_avg >= LEAN x put_avg, "puts" for the reverse, else "mixed".
A high ratio on a strike that had little open interest means new trading, not size: the board says where activity is,
not who bought or sold. It never replaces the Robinhood chain runs; rows are tagged source "fallback".
"""
LEAN = 1.5


def _ratio(row):
    try:
        return float(row.get("volume_open_interest_ratio") or 0)
    except (TypeError, ValueError):
        return 0.0


def summarize(rows, spot, max_expiry, band=0.12, top=5, min_expiry=""):
    """Score one ticker's Alpha Vantage rows. Returns None when no contract falls inside the window.

    Contracts expiring before `min_expiry` are skipped (the script passes tomorrow, so same-day closing and expiry trades
    do not swamp the board)."""
    near = []
    for r in rows:
        try:
            strike = float(r["strike"])
        except (KeyError, TypeError, ValueError):
            continue
        if min_expiry <= r.get("expiration", "") <= max_expiry and spot > 0 and abs(strike / spot - 1) <= band:
            near.append(r)
    if not near:
        return None
    out = {}
    for side in ("call", "put"):
        xs = [_ratio(r) for r in near if r.get("type") == side]
        out[f"{side}_avg"] = sum(xs) / len(xs) if xs else 0.0
        out[f"{side}_active"] = sum(1 for x in xs if x > 1)
        out[f"{side}_n"] = len(xs)
    c, p = out["call_avg"], out["put_avg"]
    out["lean"] = "calls" if c >= LEAN * p and c > 0 else "puts" if p >= LEAN * c and p > 0 else "mixed"
    busiest = sorted(near, key=_ratio, reverse=True)[:top]
    out["top"] = "; ".join(f"{r['expiration']} {float(r['strike']):g}{r['type'][0].upper()} {_ratio(r):.0f}x"
                           for r in busiest)
    out["dates"] = sorted({r.get("date", "") for r in rows if r.get("date")})
    return out


def board(scores, quotes):
    """Rank tickers by total activity (call_avg + put_avg), joined with their TradingView quote.

    scores: {ticker: summarize() result}; quotes: {ticker: {close, change, high, low}} (missing quotes stay blank).
    """
    rows = []
    for tic, s in scores.items():
        if not s:
            continue
        q = quotes.get(tic, {})
        close, low = q.get("close"), q.get("low")
        rows.append({"ticker": tic, "source": "fallback", "lean": s["lean"],
                     "call_avg": round(s["call_avg"], 2), "put_avg": round(s["put_avg"], 2),
                     "call_active": s["call_active"], "put_active": s["put_active"],
                     "close": close, "change_pct": round(q["change"], 2) if q.get("change") is not None else None,
                     "day_low": low, "day_high": q.get("high"),
                     "above_low_pct": round((close / low - 1) * 100, 2) if close and low else None,
                     "top_contracts": s["top"], "data_date": ",".join(s["dates"])})
    rows.sort(key=lambda r: -(r["call_avg"] + r["put_avg"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
