"""Donchian breakout trend strategy, long/flat, all symbols.

Entry: close[i] > highest high of the prior `entry` bars (i-entry..i-1) and close[i] > SMA(100)
       -> buy at open[i+1].
Exit:  close[j] < lowest low of prior `exit` bars, or held `hold` bars -> sell at open[j+1].
       Positions are force-closed at close[end-1] so no trade reads past the scored window.
"""
from research import Trade

NAME = "trend_donchian"
PARAM_GRID = [{"entry": e, "exit": x, "hold": h, "sma": 100}
              for e in (20, 40, 55) for x in (10, 20) for h in (20, 60)]


def trades(bars, params, start, end):
    E, X, H, S = params["entry"], params["exit"], params["hold"], params["sma"]
    out = []
    for sym, rows in bars.items():
        last = min(end, len(rows)) - 1
        i = max(start - 1, E, S - 1)
        while i < last:
            c = rows[i][4]
            hh = max(r[2] for r in rows[i - E:i])
            sma = sum(r[4] for r in rows[i - S + 1:i + 1]) / S
            if not (c > hh and c > sma and i + 1 >= start):
                i += 1
                continue
            ei = i + 1                      # enter next open
            if ei > last:
                break
            ep = rows[ei][1]
            xi, xp = last, rows[last][4]     # default: forced close at window end
            for j in range(ei, last):
                ll = min(r[3] for r in rows[max(0, j - X):j])
                if rows[j][4] < ll or j - ei + 1 >= H:
                    xi, xp = j + 1, rows[j + 1][1]
                    break
            out.append(Trade(sym, rows[ei][0], rows[xi][0], xp / ep - 1))
            i = xi
    out.sort(key=lambda t: t.entry_date)
    return out
