"""Outcome resolver: walk open ledger rows against 5m bars.

For each open row with entry/stop/target, pull the ticker's 5m bars since the
signal ts and mark the first structural outcome touched after entry:
  target  - price reached the target level
  stop    - price hit the structural stop
  scratch - signal never triggered / entry never filled (approx: price never
            traded through signal_price by more than one bar's range)
  open    - still unresolved

R = realized move / initial risk, on the UNDERLYING distance entry->stop,
per the skill (comparable across tickers; premium % is not). Short setups
invert the arithmetic. Bars are delayed yfinance data; outcomes are labeled
with the resolver version so future upgrades can re-score old rows.
"""
import math
from datetime import datetime, timezone

RESOLVER = "resolve-v1 (5m delayed bars, structural levels)"


def _parse_ts(s):
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _bars_since(ticker, since):
    """(times, highs, lows, closes) after `since`, oldest first."""
    import yfinance as yf
    tk = yf.Ticker(ticker)
    hist = tk.history(period="5d", interval="5m")
    if hist is None or hist.empty:
        return None
    idx = hist.index.tz_convert("UTC") if hist.index.tz else hist.index
    mask = [t.to_pydatetime() >= since for t in idx]
    if not any(mask):
        return None
    h = hist[mask]
    return {
        "t": [t.to_pydatetime() for t in (h.index.tz_convert("UTC") if h.index.tz else h.index)],
        "high": h["High"].astype(float).tolist() if "High" in h.columns else [],
        "low": h["Low"].astype(float) if "Low" in h.columns else [],
        "close": h["Close"].astype(float).tolist() if "Close" in h.columns else [],
    }


def resolve_row(row, bars):
    """(outcome, r, note) for one open row given its bars since signal."""
    if not all(isinstance(row.get(k), (int, float)) for k in ("signal_price", "stop", "target")):
        return ("open", None, "missing levels")
    entry, stop, tgt = float(row["signal_price"]), float(row["stop"]), float(row["target"])
    if not bars or len(bars["t"]) < 2:
        return ("open", None, "no bars yet")
    is_short = (tgt < entry) or ("sell" in str(row.get("side", "")).lower())
    # direction from levels: short if target below entry
    is_short = tgt < entry
    risk = abs(entry - stop)
    if risk <= 0:
        return ("open", None, "zero risk distance")

    for i in range(len(bars["t"])):
        hi, lo = bars["high"][i], bars["low"][i]
        if is_short:
            if lo <= tgt:
                mv = entry - tgt
                return ("target", mv / risk, "target hit")
            if hi >= stop:
                mv = entry - stop
                return ("stop", mv / risk, "structural stop")
        else:
            if hi >= tgt:
                mv = tgt - entry
                return ("target", mv / risk, "target hit")
            if lo <= stop:
                mv = stop - entry
                return ("stop", mv / risk, "structural stop")

    # never went anywhere: scratch if it's been > 1 trading day
    elapsed = (bars["t"][-1] - _parse_ts(row.get("ts", "")))
    if elapsed and elapsed.total_seconds() > 26 * 3600:
        return ("scratch", 0.0, "no fill/trigger within a day")
    return ("open", None, "in flight")


def resolve_all(ledger_module, path=None, since_key="ts"):
    """Resolve every open row; returns list of (index, row, outcome, r, note)."""
    from . import ledger as L
    mod = ledger_module or L
    p = path or mod.LEDGER
    all_rows = mod.rows(p)
    resolved = []
    by_ticker = {}
    for i, row in enumerate(all_rows):
        if row.get("outcome") is not None or row.get("source") == "ledger":
            continue
        if row.get("source") == "gex-board":
            # structure-only board states have no tradeable levels -> record as no-trade
            mod.mark_resolved(i, "no-trade", None, "board state; live gates not confirmed", p)
            resolved.append((i, row, "no-trade", None, "board state; live gates not confirmed"))
            continue
        ts = _parse_ts(row.get(since_key, ""))
        if ts is None:
            continue
        ticker = row["ticker"]
        if ticker not in by_ticker:
            by_ticker[ticker] = _bars_since(ticker, ts)
        bars = by_ticker[ticker]
        if bars is None:
            continue
        outcome, r, note = resolve_row(row, bars)
        if outcome in ("target", "stop", "scratch"):
            note = note + " | " + RESOLVER
            mod.mark_resolved(i, outcome, r, note, p)
            resolved.append((i, row, outcome, r, note))
    return resolved