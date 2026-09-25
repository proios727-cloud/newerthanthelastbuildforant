"""Session clock (America/New_York). Crypto trades 24/7; equities in regular hours only.

Exchange holidays and half-days are not modeled — the scheduler must skip them.
"""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
RTH_OPEN, RTH_CLOSE = time(9, 30), time(16, 0)


def now():
    return datetime.now(timezone.utc)


def to_et(ts):
    if ts.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return ts.astimezone(ET)


def equity_session_open(ts):
    et = to_et(ts)
    return et.weekday() < 5 and RTH_OPEN <= et.time() < RTH_CLOSE


def can_trade(asset, ts):
    return asset == "crypto" or equity_session_open(ts)


def fund_day(ts):
    """The fund's P&L day rolls at 00:00 ET (the crypto day roll)."""
    return to_et(ts).date().isoformat()
