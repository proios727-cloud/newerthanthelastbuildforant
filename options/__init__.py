"""Options desk: Black-Scholes Greeks, implied vol and a dealer-gamma (GEX) map from a chain snapshot.

Ported from 456CASH `backend/options/greeks/calculator.py` without numpy/scipy, so it runs anywhere the
fund runs. Implied vol uses bisection (always converges inside its bracket) instead of an unguarded
Newton step. Recorded SPY chains live in `options/data/chains/`.

GEX convention (the usual dealer-short-puts / long-calls assumption): call gamma adds, put gamma
subtracts. Exposure per strike = gamma · OI · 100 · spot² · 1%, i.e. dollars of delta per 1% move.
"""
import json
import math
import pathlib
from dataclasses import dataclass

CHAINS = pathlib.Path(__file__).resolve().parent / "data" / "chains"


def _cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _pdf(x):
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    vega: float     # per 1 vol point
    theta: float    # per calendar day
    rho: float      # per 1% rate


def greeks(S, K, T, sigma, kind="call", r=0.05, q=0.0):
    if kind not in ("call", "put"):
        raise ValueError("kind must be call or put")
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
        itm = (S > K) if kind == "call" else (S < K)
        return Greeks(intrinsic, (1.0 if kind == "call" else -1.0) if itm else 0.0, 0.0, 0.0, 0.0, 0.0)
    sq = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + sigma * sigma / 2) * T) / (sigma * sq)
    d2 = d1 - sigma * sq
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    gamma = dq * _pdf(d1) / (S * sigma * sq)
    vega = S * dq * _pdf(d1) * sq / 100
    decay = -S * dq * _pdf(d1) * sigma / (2 * sq)
    if kind == "call":
        price = S * dq * _cdf(d1) - K * dr * _cdf(d2)
        delta = dq * _cdf(d1)
        theta = (decay + q * S * dq * _cdf(d1) - r * K * dr * _cdf(d2)) / 365
        rho = K * T * dr * _cdf(d2) / 100
    else:
        price = K * dr * _cdf(-d2) - S * dq * _cdf(-d1)
        delta = dq * (_cdf(d1) - 1)
        theta = (decay - q * S * dq * _cdf(-d1) + r * K * dr * _cdf(-d2)) / 365
        rho = -K * T * dr * _cdf(-d2) / 100
    return Greeks(price, delta, gamma, vega, theta, rho)


def implied_vol(price, S, K, T, kind="call", r=0.05, q=0.0, lo=1e-4, hi=5.0, tol=1e-6):
    """None when the price is outside what any vol in [lo, hi] can produce."""
    f = lambda v: greeks(S, K, T, v, kind, r, q).price - price
    flo, fhi = f(lo), f(hi)
    if T <= 0 or flo > 0 or fhi < 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def load_chain(name):
    return json.loads((CHAINS / name).read_text(encoding="utf-8"))


def gex_by_strike(chain):
    """{strike: (call_gex, put_gex)} in dollars per 1% move; put_gex is ≤ 0."""
    spot = chain["spot"]
    k = 100 * spot * spot * 0.01
    out = {}
    for c in chain["contracts"]:
        g = c.get("gamma") or 0.0
        oi = c.get("open_interest") or 0
        call, put = out.get(float(c["strike"]), (0.0, 0.0))
        if c["option_type"] == "call":
            call += g * oi * k
        else:
            put -= g * oi * k
        out[float(c["strike"])] = (call, put)
    return out


@dataclass(frozen=True)
class GexMap:
    net: float            # total dollars per 1% move; > 0 = dealers long gamma (dampening)
    king: float           # strike with the largest |net| exposure
    call_wall: float      # strike with the most call exposure
    put_wall: float       # strike with the most (negative) put exposure
    flip: float           # strike where cumulative net exposure (low→high) changes sign, else None


def gex_map(chain):
    by = gex_by_strike(chain)
    if not by:
        raise ValueError("chain has no contracts")
    strikes = sorted(by)
    net = {s: sum(by[s]) for s in strikes}
    flip, cum = None, 0.0
    for s in strikes:
        prev, cum = cum, cum + net[s]
        if prev < 0 <= cum or prev > 0 >= cum:
            flip = s if flip is None else flip
    return GexMap(
        net=sum(net.values()),
        king=max(strikes, key=lambda s: abs(net[s])),
        call_wall=max(strikes, key=lambda s: by[s][0]),
        put_wall=min(strikes, key=lambda s: by[s][1]),
        flip=flip,
    )


def regime(m):
    return "positive_gamma" if m.net > 0 else "negative_gamma"
