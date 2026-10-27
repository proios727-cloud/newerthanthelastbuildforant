"""Signal builders beyond the two baselines: regime filters, breakouts, band reversion.

Each returns a list of {+1, 0, None} the same length as its input, decided at bar i's close
from bars <= i only. None means hold whatever position is on.
"""
from . import indicators as ind


def regime(close, n=50):
    """True when close is above its n-bar SMA (an uptrend), None while the SMA warms up."""
    s = ind.sma(close, n)
    return [None if m is None else c > m for c, m in zip(close, s)]


def rsi_dip_trend(close, n=7, lo=30, hi=60, trend=50):
    """Buy RSI dips only in an uptrend; exit on RSI recovery or when the trend breaks."""
    r, up = ind.rsi(close, n), regime(close, trend)
    out = []
    for v, u in zip(r, up):
        if v is None or u is None:
            out.append(None)
        elif not u or v > hi:
            out.append(0)
        elif v < lo:
            out.append(1)
        else:
            out.append(None)
    return out


def macd_trend(close, fast=12, slow=26, signal=9, trend=50):
    """Long while MACD is above its signal line and price is above the trend SMA."""
    line, sig, _ = ind.macd(close, fast, slow, signal)
    up = regime(close, trend)
    out = []
    for a, b, u in zip(line, sig, up):
        out.append(None if a is None or b is None or u is None else (1 if a > b and u else 0))
    return out


def bollinger_revert(close, n=20, k=2.0):
    """Buy a close below the lower band; exit at the middle band."""
    mid, _, lower = ind.bollinger(close, n, k)
    out = []
    for c, m, lo in zip(close, mid, lower):
        out.append(None if m is None else 1 if c < lo else 0 if c >= m else None)
    return out


def donchian_breakout(bars, n=20, exit_n=10):
    """Long on a close above the prior n-bar high; flat on a close below the prior exit_n-bar low."""
    out = [None] * len(bars)
    for i in range(max(n, exit_n), len(bars)):
        hi = max(b.high for b in bars[i - n:i])
        lo = min(b.low for b in bars[i - exit_n:i])
        c = bars[i].close
        out[i] = 1 if c > hi else 0 if c < lo else None
    return out


CLOSE_STRATEGIES = {
    "rsi_dip_trend": rsi_dip_trend,
    "macd_trend": macd_trend,
    "bollinger_revert": bollinger_revert,
}
BAR_STRATEGIES = {"donchian_breakout": donchian_breakout}
