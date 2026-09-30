"""Connors-style RSI(2) pullback: buy oversold dips in an uptrend, sell on the bounce.

Signal on bar i's close: RSI(2) < rsi_th and close > SMA(trend). Enter at bar i+1's open.
Exit: first close above SMA(5) -> sell next bar's open; or at the open `max_hold` bars after entry.
One position per symbol at a time. Index ETFs only (SPY, QQQ, IWM).
"""
import itertools
import research

NAME = "meanrev_rsi2"
SYMBOLS = ("SPY", "QQQ", "IWM")
PARAM_GRID = [{"rsi_th": r, "trend": t, "max_hold": h}
              for r, t, h in itertools.product((5, 10, 20), (50, 100), (5, 10))]


def _rsi2(closes, i):
    # Wilder-free simple RSI over the last 2 changes ending at bar i (uses bars <= i only)
    up = dn = 0.0
    for k in (i - 1, i):
        d = closes[k] - closes[k - 1]
        up += max(d, 0.0)
        dn += max(-d, 0.0)
    if up + dn == 0:
        return 50.0
    return 100.0 * up / (up + dn)


def _sma(closes, i, n):
    return sum(closes[i - n + 1:i + 1]) / n


def trades(bars, params, start, end):
    out = []
    th, tr, hold = params["rsi_th"], params["trend"], params["max_hold"]
    for sym in SYMBOLS:
        rows = bars.get(sym)
        if not rows:
            continue
        c = [r[4] for r in rows]
        o = [r[1] for r in rows]
        n = len(rows)
        i = max(tr, 5, start - 1)          # signal bar; entry is i+1
        while i + 1 < min(end, n):
            if c[i] > _sma(c, i, tr) and _rsi2(c, i) < th:
                e = i + 1
                x = None
                for j in range(e, n - 1):   # evaluate exit on close j, fill at open j+1
                    if c[j] > _sma(c, j, 5) or j + 1 - e >= hold:
                        x = j + 1
                        break
                if x is None:
                    break                    # no fill available yet; drop open trade
                out.append(research.Trade(sym, rows[e][0], rows[x][0], o[x] / o[e] - 1))
                i = x                        # next signal no earlier than exit bar
                continue
            i += 1
    out.sort(key=lambda t: t.entry_date)
    return out
