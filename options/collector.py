"""Live chain collector: yfinance -> the desk's chain JSON format.

Honesty rules:
- yfinance quotes are delayed and open_interest is from the prior close. The board
  labels this on every render; the flow panel's vol:OI comparison uses that
  overnight OI on purpose (fresh positioning = volume >= OI).
- Gamma is computed from yfinance's impliedVolatility via options.greeks(); rows
  without a usable IV get gamma 0 (they contribute nothing to the map).
- Expiries: all dated within +14 days, aggregated per strike. 0DTE dominates.
"""
import json
import math
import pathlib
from datetime import datetime, timedelta

from . import greeks

CHAINS = pathlib.Path(__file__).resolve().parent / "data" / "chains"
SOURCE = "yfinance (delayed; OI from prior close)"


def _expiry_dt(expiry, now_et):
    """Expiration assumed at 16:00 ET on the expiry date."""
    y, m, d = (int(x) for x in expiry.split("-"))
    return datetime(y, m, d, 16, 0, tzinfo=now_et.tzinfo)


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def collect(symbol, now_et=None, max_days_out=14, max_expiries=None):
    """Fetch near-expiry chains for `symbol`; return the desk chain dict.

    {symbol, source, spot, captured_at, snapshot_date, contracts: [...]}
    """
    import yfinance as yf

    if now_et is None:
        from fund import clock
        now_et = clock.to_et(clock.now())

    tk = yf.Ticker(symbol)
    fi = tk.fast_info
    spot = 0.0
    for key in ("lastPrice", "last_price", "previousClose", "previous_close",
                "regularMarketPreviousClose"):
        try:
            v = _num(fi[key])
        except (KeyError, Exception):
            continue
        if v > 0:
            spot = v
            break
    if spot <= 0:
        raise RuntimeError(f"no spot for {symbol}")

    wanted = []
    for exp in tk.options:
        ed = _expiry_dt(exp, now_et)
        days_out = (ed - now_et).total_seconds() / 86400
        if -1 < days_out <= max_days_out:
            wanted.append(exp)
        if max_expiries and len(wanted) >= max_expiries:
            break
    if not wanted:
        raise RuntimeError(f"no expiries within {max_days_out} days for {symbol}")

    contracts = []
    for exp in wanted:
        ed = _expiry_dt(exp, now_et)
        T = max((ed - now_et).total_seconds(), 3600) / (365 * 86400)
        ch = tk.option_chain(exp)
        for otype, rows in (("call", ch.calls), ("put", ch.puts)):
            for _, r in rows.iterrows():
                K = _num(r["strike"])
                if K <= 0:
                    continue
                bid, ask = _num(r["bid"]), _num(r["ask"])
                iv = _num(r["impliedVolatility"])
                mid = (bid + ask) / 2 if bid > 0 and ask > 0 else _num(r.get("lastPrice"))
                g = 0.0
                if iv > 0.01:
                    g = greeks(spot, K, T, iv, kind=otype).gamma
                contracts.append({
                    "strike": K,
                    "option_type": otype,
                    "expiration": exp,
                    "bid": bid,
                    "ask": ask,
                    "mark": mid,
                    "iv": iv,
                    "gamma": g,
                    "open_interest": int(_num(r["openInterest"])),
                    "volume": int(_num(r["volume"])),
                    "bid_size": None,
                    "ask_size": None,
                    "delta": None,
                    "theta": None,
                    "vega": None,
                })

    return {
        "symbol": symbol,
        "source": SOURCE,
        "spot": spot,
        "captured_at": now_et.isoformat(),
        "snapshot_date": now_et.date().isoformat(),
        "contracts": contracts,
    }


def rvol_5m(symbol, lookback_days=10):
    """Last completed 5m bar volume / mean 5m volume over the lookback.

    Returns (rvol, note). Honest, simple index - not time-of-day adjusted.
    """
    import yfinance as yf

    tk = yf.Ticker(symbol)
    try:
        hist = tk.history(period="5d", interval="5m")
    except Exception:
        hist = tk.history(period="5d", interval="5m", prepost=False)
    if hist is None or hist.empty:
        return (None, "no 5m bars")
    volcol = "Volume" if "Volume" in hist.columns else ("volume" if "volume" in hist.columns else None)
    if volcol is None:
        return (None, "no 5m volume data")
    vols = hist[volcol].astype(float).dropna()
    vols = vols[vols > 0]
    if len(vols) < 20:
        return (None, "insufficient nonzero bars")
    last = vols.iloc[-1]
    mean = vols.iloc[:-1].mean()
    if mean <= 0:
        return (None, "zero mean volume")
    return (last / mean, f"last 5m bar vs {lookback_days}d mean")


def gap_pct(symbol):
    """Today's open vs prior close, from daily bars. None when unavailable."""
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d")
    except Exception:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d", prepost=False)
    if hist is None or hist.empty or len(hist) < 2 or "Close" not in hist.columns:
        return None
    prev_close = float(hist["Close"].iloc[-2])
    open_ = float(hist["Open"].iloc[-1])
    if prev_close <= 0:
        return None
    return (open_ - prev_close) / prev_close


def save_chain(chain, name=None):
    CHAINS.mkdir(parents=True, exist_ok=True)
    sym, ts = chain["symbol"], chain["captured_at"].replace(":", "").replace("-", "")[:13]
    name = name or f"{sym}-{ts}.json"
    (CHAINS / name).write_text(json.dumps(chain), encoding="utf-8")
    return name