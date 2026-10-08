"""Keyless market-data collectors: the desk's data spine.

Feeds (verified keyless):
  crypto  Binance public API  https://data-api.binance.vision/api/v3/ticker/bookTicker
          real-time bid/ask, 24/7, no key.
  equities yfinance (installed dep): Ticker.fast_info for quotes; history()
          for OHLCV. Crypto fallback: yfinance BTC-USD.
  funding  Binance fapi /premiumIndex for the carry strategy (keyless).

Everything writes through store.json so seats read one consistent view.
Quotes older than max_quote_age_sec (120s in desk.json) must be re-pulled
before previewing - fund/risk.py already rejects stale quotes.
"""
import json
import pathlib
import time
import urllib.parse

import requests

from fund import config

ROOT = config.ROOT
STORE = ROOT / "data" / "store.json"

BINANCE_BOOK = "https://data-api.binance.vision/api/v3/ticker/bookTicker"
# Binance fapi is geo-blocked (451) from this desk's location; OKX public API is keyless
# and returns the standard 8h funding rate. Hyperliquid (1h funding) is the fallback.
OKX_FUNDING = "https://www.okx.com/api/v5/public/funding-rate"
HYPERLIQUID_INFO = "https://api.hyperliquid.xyz/info"

SYMBOL_MAP = {"BTC/USD": "BTCUSDT", "ETH/USD": "ETHUSDT", "SOL/USD": "SOLUSDT"}
YF_MAP = {"SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "NVDA": "NVDA", "AMD": "AMD",
          "AAPL": "AAPL", "MSFT": "MSFT", "TSLA": "TSLA"}

_session = requests.Session()
_session.headers.update({"User-Agent": "paper-receipts-desk/1.0"})


def _load_store():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"quotes": {}, "funding": {}, "meta": {"fetches": 0}}


def _save_store(store):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    store["meta"]["fetches"] = store["meta"].get("fetches", 0) + 1
    STORE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _iso_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def crypto_quote(symbol):
    """symbol like 'BTC/USD' -> {'price','bid','ask','ts'} from Binance, or None."""
    pair = SYMBOL_MAP.get(symbol)
    if not pair:
        return None
    try:
        r = _session.get(BINANCE_BOOK, params={"symbol": pair}, timeout=10)
        if r.status_code != 200:
            return None
        j = r.json()
        bid, ask = float(j["bidPrice"]), float(j["askPrice"])
        if bid <= 0 or ask < bid:
            return None
        return {"price": (bid + ask) / 2, "bid": bid, "ask": ask, "ts": _iso_now()}
    except (requests.RequestException, KeyError, ValueError):
        return None


def _yf_quote(symbol):
    """Equity quote via yfinance fast_info; None on failure."""
    try:
        import yfinance as yf
        fi = yf.Ticker(YF_MAP[symbol]).fast_info
        price = float(fi["last_price"])
        if price <= 0:
            return None
        return {"price": price, "bid": None, "ask": None, "ts": _iso_now()}
    except (Exception,):
        return None


def equity_quote(symbol):
    return _yf_quote(symbol)


def quote(symbol, cfg):
    """Fresh quote for any universe symbol: crypto live, equities via yfinance."""
    asset = cfg.asset(symbol)
    if asset == "crypto":
        q = crypto_quote(symbol)
        if q is None:  # yfinance fallback
            try:
                import yfinance as yf
                ysym = {"BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD"}[symbol]
                fi = yf.Ticker(ysym).fast_info
                price = float(fi["last_price"])
                if price > 0:
                    return {"price": price, "bid": None, "ask": None, "ts": _iso_now()}
            except Exception:
                pass
        return q
    return _yf_quote(symbol)


def funding_rate(symbol):
    """Current perp funding for 'BTC/USD' or 'ETH/USD' -> {'rate_8h','ts'} or None.

    Primary: OKX USDT-margined swap (keyless, standard 8h funding).
    Fallback: Hyperliquid (1h funding scaled to 8h-equivalent).
    Binance fapi is geo-blocked (451) from this desk's location.
    """
    pair = SYMBOL_MAP.get(symbol)
    if not pair:
        return None
    okx_inst = {"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP", "SOLUSDT": "SOL-USDT-SWAP"}[pair]
    try:
        r = _session.get(OKX_FUNDING, params={"instId": okx_inst}, timeout=10)
        if r.status_code == 200:
            j = r.json()
            if j.get("code") == "0" and j.get("data"):
                return {"rate_8h": float(j["data"][0]["fundingRate"]), "ts": _iso_now()}
    except (requests.RequestException, KeyError, ValueError):
        pass
    try:
        r2 = _session.post(HYPERLIQUID_INFO, json={"type": "metaAndAssetCtxs"}, timeout=10)
        if r2.status_code == 200:
            meta, ctxs = r2.json()[0], r2.json()[1]
            coin = pair.replace("USDT", "")
            for m, c in zip(meta["universe"], ctxs):
                if m["name"] == coin:
                    rate_1h = float(c.get("funding") or 0)
                    return {"rate_8h": rate_1h * 8, "ts": _iso_now()}
    except (requests.RequestException, KeyError, ValueError, IndexError):
        pass
    return None


def mark_all(cfg, symbols=None):
    """Pull fresh quotes for universe + open positions, write store + return marks.

    Returns {symbol: quote-dict} for the symbols actually marked.
    """
    store = _load_store()
    symbols = symbols if symbols is not None else list(cfg.universe)
    marked = {}
    for sym in symbols:
        q = quote(sym, cfg)
        if q:
            store["quotes"][sym] = q
            marked[sym] = q
    _save_store(store)
    return marked


def store_funding(rates):
    store = _load_store()
    store["funding"] = rates
    _save_store(store)


def get_stored_quote(symbol):
    return _load_store()["quotes"].get(symbol)