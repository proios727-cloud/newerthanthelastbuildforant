"""Live market-data loop: plan which symbols are due, fetch within the request budget, mark the ledger.

The free Alpha Vantage key allows 25 requests a day and 1 a second, so the planner paces calls
across the fund day (00:00 ET roll), fetches held positions first, then the stalest symbols.
Equities are fetched only in regular hours; crypto around the clock.

Sources:
  AlphaVantage — HTTP, key from the env var named in desk.json fund.feed.key_env. Counts against the budget.
  load_quotes  — quotes pushed in by an agent (e.g. a Routine using the Alpha Vantage MCP). No budget.
"""
import json
import math
import pathlib
import time as _time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import clock
from .ledger import parse_ts

DEFAULTS = {
    "provider": "alphavantage",
    "key_env": "ALPHAVANTAGE_API_KEY",
    "daily_requests": 25,
    "min_interval_sec": 1.2,
    "cadence_sec": {"crypto": 900, "equity": 1800},
    "backoff_sec": 60,
}


class FeedError(Exception):
    pass


class RateLimited(FeedError):
    pass


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    ts: datetime
    bid: float = None
    ask: float = None
    source: str = ""
    note: str = ""


def feed_config(desk_fund):
    f = {**DEFAULTS, **desk_fund.get("feed", {})}
    f["cadence_sec"] = {**DEFAULTS["cadence_sec"], **f.get("cadence_sec", {})}
    return f


# ---- budget state (ledger/feed.json) ---------------------------------------
def new_state():
    return {"date": None, "used": 0, "last_fetch": {}, "backoff_until": None}


def load_state(path):
    path = pathlib.Path(path)
    return {**new_state(), **json.loads(path.read_text())} if path.exists() else new_state()


def save_state(state, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _roll(state, now):
    d = clock.fund_day(now)
    if state["date"] != d:
        state["date"], state["used"] = d, 0


def pace_allowance(daily, now):
    """Requests allowed so far today: an even spread across the ET day, plus one so a tick can always start."""
    et = clock.to_et(now)
    frac = (et.hour * 3600 + et.minute * 60 + et.second) / 86400
    return min(daily, math.floor(daily * frac) + 1)


def plan(universe, held, state, now, fcfg):
    """Symbols to fetch this tick, in priority order, capped by the budget and the pace."""
    _roll(state, now)
    if state.get("backoff_until") and now < parse_ts(state["backoff_until"]):
        return []
    daily = fcfg["daily_requests"]
    cap = max(0, min(daily - state["used"], pace_allowance(daily, now) - state["used"]))
    due = []
    for sym, meta in universe.items():
        asset = meta["asset"]
        if not clock.can_trade(asset, now):
            continue
        last = state["last_fetch"].get(sym)
        age = math.inf if last is None else (now - parse_ts(last)).total_seconds()
        if age >= fcfg["cadence_sec"][asset]:
            due.append((sym not in held, -age, sym))
    return [s for _, _, s in sorted(due)][:cap]


# ---- sources ---------------------------------------------------------------
def _http_get(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


class AlphaVantage:
    URL = "https://www.alphavantage.co/query"
    name = "alphavantage"

    def __init__(self, key, http_get=_http_get):
        if not key:
            raise FeedError("no Alpha Vantage key: set the env var named in desk.json fund.feed.key_env")
        self.key, self.http_get = key, http_get

    def _call(self, **params):
        data = self.http_get(self.URL + "?" + urllib.parse.urlencode({**params, "apikey": self.key}))
        for k in ("Note", "Information"):
            if k in data:
                raise RateLimited(data[k])
        if "Error Message" in data:
            raise FeedError(data["Error Message"])
        return data

    def quote(self, symbol, asset, now):
        if asset == "crypto":
            base, quote_ccy = symbol.split("/")
            r = self._call(function="CURRENCY_EXCHANGE_RATE", from_currency=base, to_currency=quote_ccy)
            r = r.get("Realtime Currency Exchange Rate") or {}
            price = _num(r.get("5. Exchange Rate"))
            if price is None:
                raise FeedError(f"{symbol}: empty exchange-rate response")
            ts = now
            if r.get("6. Last Refreshed") and r.get("7. Time Zone", "UTC") == "UTC":
                ts = datetime.fromisoformat(r["6. Last Refreshed"]).replace(tzinfo=timezone.utc)
            return Quote(symbol, price, ts, _num(r.get("8. Bid Price")), _num(r.get("9. Ask Price")), self.name)
        r = self._call(function="GLOBAL_QUOTE", symbol=symbol).get("Global Quote") or {}
        price = _num(r.get("05. price"))
        if price is None:
            raise FeedError(f"{symbol}: empty quote response")
        # GLOBAL_QUOTE carries only a trading date, so the mark is stamped with the fetch time.
        return Quote(symbol, price, now, source=self.name, note=f"latest trading day {r.get('07. latest trading day')}")


def load_quotes(data, now):
    """Parse agent-pushed quotes: {SYM: {price, bid?, ask?, ts?}} or [{symbol, price, ...}]."""
    items = data.items() if isinstance(data, dict) else ((d["symbol"], d) for d in data)
    out = []
    for sym, d in items:
        price = _num(d.get("price"))
        if price is None:
            raise FeedError(f"{sym}: price must be a positive number")
        ts = parse_ts(d["ts"]) if d.get("ts") else now
        if ts.tzinfo is None:
            raise FeedError(f"{sym}: ts must include a timezone")
        out.append(Quote(sym, price, ts, _num(d.get("bid")), _num(d.get("ask")), d.get("source", "pushed")))
    return out


# ---- applying quotes -------------------------------------------------------
def apply(ledger, quotes, universe):
    """Mark the ledger. Skips unknown symbols and quotes older than the current mark."""
    marked, skipped = [], []
    for q in quotes:
        if q.symbol not in universe:
            skipped.append({"symbol": q.symbol, "reason": "not in universe"})
            continue
        cur = ledger.marks.get(q.symbol)
        if cur and parse_ts(cur["ts"]) >= q.ts:
            skipped.append({"symbol": q.symbol, "reason": "older than current mark"})
            continue
        ledger.mark(q.symbol, q.price, q.ts, q.bid, q.ask)
        marked.append({"symbol": q.symbol, "price": q.price, "bid": q.bid, "ask": q.ask,
                       "ts": q.ts.isoformat(), "source": q.source, **({"note": q.note} if q.note else {})})
    return marked, skipped


def tick(ledger, state, source, universe, fcfg, now, sleep=_time.sleep):
    """One loop pass: plan → fetch (spaced, budget-counted) → mark. Returns a report."""
    held = {s for s, p in ledger.positions.items() if p["qty"]}
    todo = plan(universe, held, state, now, fcfg)
    quotes, errors, limited = [], [], False
    for i, sym in enumerate(todo):
        if i:
            sleep(fcfg["min_interval_sec"])
        state["used"] += 1
        try:
            quotes.append(source.quote(sym, universe[sym]["asset"], now))
            state["last_fetch"][sym] = now.isoformat()
        except RateLimited as e:
            limited = True
            state["backoff_until"] = (now + timedelta(seconds=fcfg["backoff_sec"])).isoformat()
            errors.append({"symbol": sym, "error": f"rate_limit: {e}"})
            break
        except Exception as e:  # network or parse failure: skip the symbol, keep the tick going
            errors.append({"symbol": sym, "error": str(e)})
    marked, skipped = apply(ledger, quotes, universe)
    return {"ts": now.isoformat(), "planned": todo, "marked": marked, "skipped": skipped, "errors": errors,
            "rate_limited": limited, "used": state["used"], "daily": fcfg["daily_requests"]}
