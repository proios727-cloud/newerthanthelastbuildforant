"""Fill reality check: what did takers actually pay for the favourite in a short window?

Minute-candle asks can be stale or thin, so a backtest on them can promise fills that never
existed. This reads Kalshi's public trade prints (read-only) and prices an entry at the
volume-weighted price takers paid for the favourite side in [T-`at_s`, T-`at_s`+`window_s`].
"""
from . import taker_fee_cents
from .feed import _get


def side_price_c(trade, side):
    return int(round(float(trade[f"{side}_price_dollars"]) * 100))


def taker_vwap(trades, side):
    """VWAP (cents) and contract count of trades where the taker bought `side`; None if none."""
    got = [(side_price_c(t, side), float(t["count_fp"])) for t in trades if t.get("taker_side") == side]
    qty = sum(q for _, q in got)
    return (round(sum(p * q for p, q in got) / qty), qty) if qty else (None, 0)


def window_trades(ticker, close_ts, at_s=60, window_s=10, fetch=_get):
    lo = close_ts - at_s
    body = fetch("/markets/trades", {"ticker": ticker, "min_ts": lo, "max_ts": lo + window_s, "limit": 1000})
    return body.get("trades", [])


def price_entry(snap, trades, min_qty=1):
    """Re-price a calibration snapshot at real taker prints. Returns the row with `fill`/`pnl_c`, or unfilled."""
    vwap, qty = taker_vwap(trades, snap["side"])
    if vwap is None or qty < min_qty:
        return {**snap, "fill": None, "qty": qty, "pnl_c": None}
    pnl = (100 if snap["won"] else 0) - vwap - taker_fee_cents(vwap, 1)
    return {**snap, "fill": vwap, "qty": round(qty, 2), "pnl_c": pnl}
