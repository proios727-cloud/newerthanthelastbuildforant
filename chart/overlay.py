"""Monthly trend overlay on one fund: hold it while its monthly close is above its N-month average, else cash.

Runs on weekly total-return bars. Each month has one decision bar: its last weekly bar by default, or its first,
second or third (`week`) to test whether the day of the month matters. The average uses the closes of the last N
decision bars, including the current one. A change of position fills at the next weekly bar's open, with fees and
slippage per side. While out, cash earns `cash_rate` a year (0 by default, which understates the overlay).
"""
from datetime import date, timedelta

from .backtest import _stats
from .scan import _risk_verdict

STRESS = (("2000–02 dot-com", "2000-03-01", "2002-10-31"), ("2008 crash", "2007-10-01", "2009-03-31"),
          ("2011 debt scare", "2011-05-01", "2011-10-31"), ("2015–16 slump", "2015-07-01", "2016-02-29"),
          ("2018 Q4", "2018-10-01", "2018-12-31"), ("2020 Covid crash", "2020-02-01", "2020-04-30"),
          ("2022 bear", "2022-01-01", "2022-10-31"))


def _month_complete(ts):
    """True when the next weekday after date `ts` falls in another month (exchange holidays are not modelled)."""
    d = date.fromisoformat(ts[:10]) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.month != int(ts[5:7])


def decisions(bars, months=10, week=-1):
    """{bar index: 1 hold / 0 cash} on each month's decision bar, once `months` decisions of history exist."""
    by_month = {}
    for i, b in enumerate(bars):
        by_month.setdefault(b.ts[:7], []).append(i)
    groups = list(by_month.values())
    if week < 0 and groups and not _month_complete(bars[groups[-1][-1]].ts):
        groups.pop()                                       # the last month isn't over: its last bar isn't month-end
    picks = []
    for idx in groups:
        if -len(idx) <= week < len(idx):
            picks.append(idx[week])
    out = {}
    for k in range(months - 1, len(picks)):
        closes = [bars[j].close for j in picks[k - months + 1:k + 1]]
        out[picks[k]] = int(bars[picks[k]].close > sum(closes) / months)
    return out


def run(bars, months=10, week=-1, start=0, fee_bps=1.0, slippage_bps=2.0, cash_rate=0.0, ppy=52, cash=None):
    """Equity per bar from `start`, the overlay's stats, and buy-and-hold's over the same bars.
    `cash` (bars of a T-bill fund such as BIL) makes time out of the market earn that fund's return on the same dates;
    dates it doesn't cover fall back to `cash_rate`."""
    cash_close = {b.ts: b.close for b in cash} if cash else {}
    sig = decisions(bars, months, week)
    cost = (fee_bps + slippage_bps) / 1e4
    weekly_cash = (1 + cash_rate) ** (1 / ppy) - 1
    pos, pending, eq, held, trades = 0, None, [1.0], 0, []
    # The position going into `start` is the last decision before it, so every config starts from a known state.
    prior = [i for i in sig if i < start]
    pos = sig[max(prior)] if prior else 0
    for i in range(start + 1, len(bars)):
        e = eq[-1]
        if pending is not None and pending != pos:
            e *= 1 - cost
            if pending:                                    # buy at the open, ride to the close
                e *= bars[i].close / bars[i].open
            else:                                          # sell at the open: last week's close → this open
                e *= bars[i].open / bars[i - 1].close
                trades.append((None, bars[i].ts, "", 0, 0, 0))
            pos = pending
        elif pos:
            e *= bars[i].close / bars[i - 1].close
        else:
            a, b = cash_close.get(bars[i - 1].ts), cash_close.get(bars[i].ts)
            e *= b / a if a and b else 1 + weekly_cash
        pending = sig.get(i)
        held += pos
        eq.append(e)
    stats = _stats(eq, trades, held, 1.0, ppy)
    hold_eq = [bars[i].close / bars[start].close for i in range(start, len(bars))]
    hold = _stats(hold_eq, [], len(hold_eq), 1.0, ppy)
    return {"equity": eq, "hold_equity": hold_eq, "dates": [b.ts for b in bars[start:]], "stats": stats, "hold": hold}


def windows(res, spans=STRESS):
    """Overlay vs hold over each stress window: total return and worst drawdown inside the window."""
    out = []
    d, eq, hq = res["dates"], res["equity"], res["hold_equity"]
    for name, a, b in spans:
        ix = [i for i, t in enumerate(d) if a <= t <= b]
        if len(ix) < 2:
            continue
        i0, i1 = ix[0], ix[-1]

        def dd(series):
            peak, worst = series[i0], 0.0
            for v in series[i0:i1 + 1]:
                peak = max(peak, v)
                worst = min(worst, v / peak - 1)
            return round(worst, 4)

        out.append({"window": name, "overlay": round(eq[i1] / eq[i0] - 1, 4), "hold": round(hq[i1] / hq[i0] - 1, 4),
                    "overlay_dd": dd(eq), "hold_dd": dd(hq)})
    return out


def verdict(res):
    """The scan's risk-filter rule, applied to the overlay against holding the same fund."""
    reasons = _risk_verdict(res["stats"], res["hold"])
    return {"risk_filter": not reasons, "why_not": reasons}


def status(bars, months=10):
    """Where the overlay stands today: the latest month-end decision and how far the last close is from the average."""
    sig = decisions(bars, months, -1)
    ends = sorted(sig)
    last = ends[-1]
    # If the month ended at the latest close: that close against it and the previous months-1 month-end closes.
    prev = [bars[j].close for j in ends[-(months - 1):]] if ends[-1] != len(bars) - 1 else \
        [bars[j].close for j in ends[-months:-1]]
    avg = (sum(prev) + bars[-1].close) / months
    return {"decided": bars[last].ts, "hold": bool(sig[last]), "last_bar": bars[-1].ts,
            "close_vs_average_now": round(bars[-1].close / avg - 1, 4), "months": months}
