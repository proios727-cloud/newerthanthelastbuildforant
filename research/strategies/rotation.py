"""Cross-sectional rotation: every K bars rank symbols by trailing N-day return (optionally / vol),
hold the top `top` from the next open until the open after the next rebalance decision.
Cash when the leader's trailing return <= 0 or SPY close < its 100-day SMA.
Consecutive periods holding the same symbol are merged into one Trade."""
import math
from research import Trade

NAME = "xs_rotation"
PARAM_GRID = [{"n": n, "k": k, "top": t, "riskadj": False}
              for n in (20, 60, 120) for k in (5, 10) for t in (1, 2)]


def _score(c, i, n, riskadj):
    r = c[i] / c[i - n] - 1
    if not riskadj:
        return r
    rets = [c[j] / c[j - 1] - 1 for j in range(i - n + 1, i + 1)]
    m = sum(rets) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / n) or 1e-9
    return r / sd


def trades(bars, params, start, end):
    n, k, top, ra = params["n"], params["k"], params["top"], params["riskadj"]
    syms = sorted(bars)
    L = min(len(v) for v in bars.values())
    end = min(end, L)
    close = {s: [r[4] for r in bars[s][:L]] for s in syms}
    opn = {s: [r[1] for r in bars[s][:L]] for s in syms}
    date = [r[0] for r in bars[syms[0]][:L]]
    spy = close["SPY"]
    out, held = [], {}                      # held: sym -> entry index
    warm = max(n, 100)
    for d in range(warm, end - 1):          # d = decision bar (uses closes <= d)
        if d % k:
            continue
        e = d + 1                           # act at next open
        want = set()
        if e >= start:
            sma = sum(spy[d - 99:d + 1]) / 100
            ranked = sorted(syms, key=lambda s: _score(close[s], d, n, ra), reverse=True)
            if spy[d] >= sma and close[ranked[0]][d] / close[ranked[0]][d - n] - 1 > 0:
                want = {s for s in ranked[:top] if close[s][d] / close[s][d - n] - 1 > 0}
        for s in list(held):
            if s not in want:
                i0 = held.pop(s)
                out.append(Trade(s, date[i0], date[e], opn[s][e] / opn[s][i0] - 1))
        for s in want:
            if s not in held:
                held[s] = e
    last = end - 1                          # close out anything still open at the window's last close
    for s, i0 in held.items():
        out.append(Trade(s, date[i0], date[last], close[s][last] / opn[s][i0] - 1))
    return sorted(out, key=lambda t: t.entry_date)
