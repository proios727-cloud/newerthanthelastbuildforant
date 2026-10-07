"""Modeled SPY weekly put credit spread (defined risk).

Rules: at the close of bar i, sell the 1-point-strike put nearest `delta` (abs) and buy a put
`width` points lower, both expiring `hold` trading days later; price both legs with Black-Scholes
at sigma = trailing 20-day realized vol (closes up to and including bar i) x `markup`.
Settle at intrinsic on the SPY close of bar i+hold. One spread at a time (no overlap).
gross = (credit - haircut - settlement loss) / (width - credit), so a full loss is about -1.0.
There is NO historical option data: prices are modeled, not observed.
"""
import math
from options import greeks
from research import Trade

NAME = "spy_put_credit_spread_modeled"
SYMBOL = "SPY"
HAIRCUT = 0.05       # $/share total bid-ask on the 4 fills (2 legs in; settlement assumed cash)
RV_WIN = 20

PARAM_GRID = [{"delta": d, "width": w, "markup": m, "hold": 5}
              for d in (0.15, 0.20, 0.25) for w in (2.0, 5.0) for m in (1.0, 1.2)]


def _rv(closes, i):
    rets = [math.log(closes[k] / closes[k - 1]) for k in range(i - RV_WIN + 1, i + 1)]
    mu = sum(rets) / len(rets)
    return math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1) * 252)


def _short_strike(S, T, sig, target):
    best, bd = None, None
    for K in range(int(S * 0.80), int(S) + 1):
        d = abs(greeks(S, K, T, sig, "put").delta)
        if bd is None or abs(d - target) < bd:
            best, bd = K, abs(d - target)
    return float(best)


def trades(bars, params, start, end):
    rows = bars[SYMBOL]
    closes = [r[4] for r in rows]
    hold, width = params["hold"], params["width"]
    T = hold / 252.0
    out, i = [], max(start, RV_WIN)
    while i < end and i + hold < len(rows):
        S = closes[i]                                   # data only through bar i
        sig = _rv(closes, i) * params["markup"]
        Ks = _short_strike(S, T, sig, params["delta"])
        Kl = Ks - width
        credit = greeks(S, Ks, T, sig, "put").price - greeks(S, Kl, T, sig, "put").price - HAIRCUT
        risk = width - credit
        if credit <= 0 or risk <= 0:
            i += 1
            continue
        ST = closes[i + hold]
        loss = min(max(Ks - ST, 0.0), width)
        out.append(Trade(SYMBOL, rows[i][0], rows[i + hold][0], (credit - loss) / risk))
        i += hold
    return out
