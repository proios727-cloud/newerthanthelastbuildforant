"""Indicators and order-book metrics that go into the Drex state."""
from __future__ import annotations

import numpy as np


def ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2 / (n + 1)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def atr(h, l, c, n=14) -> np.ndarray:
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
    return ema(tr, n)


def rsi(c: np.ndarray, n=14) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    up, dn = ema(np.clip(d, 0, None), n), ema(np.clip(-d, 0, None), n)
    return 100 - 100 / (1 + up / np.where(dn == 0, 1e-12, dn))


def adx(h, l, c, n=14) -> float:
    up, dn = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, l, c, n)
    pdi, ndi = 100 * ema(pdm, n) / a, 100 * ema(ndm, n) / a
    dx = 100 * abs(pdi - ndi) / np.where(pdi + ndi == 0, 1e-12, pdi + ndi)
    return float(ema(dx, n)[-1])


def arrays(candles: list[dict]):
    return tuple(np.array([k[f] for k in candles], dtype=float) for f in ("o", "h", "l", "c", "v"))


def candle_features(candles: list[dict], atr_n: int = 14) -> dict:
    o, h, l, c, v = arrays(candles)
    a = atr(h, l, c, atr_n)
    sma20, sd20 = np.convolve(c, np.ones(20) / 20, "valid"), np.array([c[i - 19:i + 1].std() for i in range(19, len(c))])
    e20, e50 = ema(c, 20), ema(c, 50)
    rets = np.diff(np.log(c))
    last = candles[-1]
    return {
        "close": round(c[-1], 2),
        "ret_1": round(float(rets[-1]) * 100, 3),
        "ret_12": round(float(np.log(c[-1] / c[-13])) * 100, 3),
        "ret_48": round(float(np.log(c[-1] / c[-49])) * 100, 3),
        "atr": round(float(a[-1]), 2),
        "atr_pct": round(float(a[-1] / c[-1]) * 100, 3),
        "atr_ratio_vs_100": round(float(a[-1] / a[-100:].mean()), 3),
        "realized_vol_24_pct": round(float(rets[-24:].std()) * 100, 3),
        "adx14": round(adx(h, l, c, 14), 2),
        "rsi14": round(float(rsi(c)[-1]), 2),
        "ema20": round(float(e20[-1]), 2),
        "ema50": round(float(e50[-1]), 2),
        "ema20_slope_pct": round(float((e20[-1] / e20[-6] - 1) * 100), 3),
        "bb_mid": round(float(sma20[-1]), 2),
        "bb_upper": round(float(sma20[-1] + 2 * sd20[-1]), 2),
        "bb_lower": round(float(sma20[-1] - 2 * sd20[-1]), 2),
        "bb_width_pct": round(float(4 * sd20[-1] / sma20[-1] * 100), 3),
        "vol_ratio_vs_50": round(float(v[-1] / v[-50:].mean()), 3),
        "taker_buy_share": round(last["taker_buy_v"] / last["v"], 3) if last["v"] else None,
        "range_pct_last": round(float((h[-1] - l[-1]) / c[-1] * 100), 3),
        "drawdown_from_48h_high_pct": round(float((c[-1] / h[-48:].max() - 1) * 100), 3),
    }


def book_features(book: dict) -> dict:
    bids, asks = book["bids"], book["asks"]
    bb, ba = bids[0][0], asks[0][0]
    mid = (bb + ba) / 2

    def within(side, pct):
        lim = mid * pct / 100
        return sum(q for p, q in side if abs(p - mid) <= lim)

    out = {"best_bid": bb, "best_ask": ba, "mid": round(mid, 2),
           "spread_bps": round((ba - bb) / mid * 1e4, 3)}
    for pct in (0.1, 0.5, 1.0):
        b, a = within(bids, pct), within(asks, pct)
        out[f"bid_btc_{pct}pct"] = round(b, 3)
        out[f"ask_btc_{pct}pct"] = round(a, 3)
        out[f"imbalance_{pct}pct"] = round((b - a) / (b + a), 3) if b + a else 0.0
    biggest_bid = max(bids, key=lambda x: x[1])
    biggest_ask = max(asks, key=lambda x: x[1])
    out["largest_bid_wall"] = {"price": biggest_bid[0], "btc": round(biggest_bid[1], 3)}
    out["largest_ask_wall"] = {"price": biggest_ask[0], "btc": round(biggest_ask[1], 3)}
    return out
