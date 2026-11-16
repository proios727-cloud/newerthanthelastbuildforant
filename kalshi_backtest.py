"""Kalshi BTC line-movement replay backtest. Research only: public market data, no key, no orders.

Replays settled Kalshi BTC price markets (default series KXBTCD, "BTC above $K at time T") candle by candle.
At every candle it knows only what was known then: the market's yes bid/ask and its recent moves, and the
Binance BTC price and realised volatility up to that minute. It then scores simple rules held to settlement:

  model_edge  buy the side whose ask is cheaper than a lognormal fair value (Binance spot + trailing 24h vol)
  momentum    follow the last candle's move in the market's mid price
  fade        bet against that move
  longshot    sell overpriced longshots / buy heavy favourites (the favourite-longshot bias)

Each rule takes at most one trade per market (its first signal), pays the ask (taker), and pays Kalshi's taker
fee 0.07 * P * (1 - P) per contract. Thresholds are walk-forward: each month uses the threshold that did best
on all earlier months. Also reports calibration (Brier score) of the market's own price vs the model.

  python kalshi_backtest.py [--series KXBTCD] [--days 60] [--max-markets 2000] [--out kalshi_report.md]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.elections.kalshi.com/trade-api/v2"
BINANCE = "https://data-api.binance.vision"
S = requests.Session()
S.headers["User-Agent"] = "research-backtest/1.0"
CALLS = {"kalshi": 0, "binance": 0}


def get(url, **params):
    for attempt in range(6):
        try:
            r = S.get(url, params={k: v for k, v in params.items() if v is not None}, timeout=20)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(str(r.status_code))
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt == 5:
                print(f"  giving up on {url}: {e}", file=sys.stderr)
                return None
            time.sleep(1.5 * 2 ** attempt)


def kget(path, **params):
    CALLS["kalshi"] += 1
    time.sleep(0.07)  # stay well under the public read limit
    return get(API + path, **params)


def ts(iso: str | None) -> int | None:
    if not iso:
        return None
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def cents(d: dict | None, key="close"):
    """Kalshi candle price fields come as cents ints, or as *_dollars strings in newer responses."""
    if not d:
        return None
    v = d.get(key)
    if v is None and d.get(f"{key}_dollars") is not None:
        v = float(d[f"{key}_dollars"]) * 100
    return None if v is None else float(v)


# ---------- data ----------

def list_markets(series: str, days: int) -> list[dict]:
    now = int(time.time())
    out = []
    for base in ("/markets", "/historical/markets"):
        cursor = None
        while True:
            r = kget(base, series_ticker=series, status="settled" if base == "/markets" else None,
                     limit=1000, cursor=cursor, min_close_ts=now - days * 86400)
            if not r:
                break
            ms = r.get("markets") or []
            out += ms
            cursor = r.get("cursor")
            if not cursor or not ms:
                break
        if out:
            break
    seen, uniq = set(), []
    for m in out:
        if m["ticker"] not in seen and m.get("result") in ("yes", "no"):
            seen.add(m["ticker"]); uniq.append(m)
    print(f"{series}: {len(uniq)} settled markets in the last {days} days ({len(out)} listed)", file=sys.stderr)
    return uniq


def candles(series: str, m: dict, period: int) -> list[dict]:
    t0, t1 = ts(m.get("open_time")), ts(m.get("close_time"))
    for path in (f"/series/{series}/markets/{m['ticker']}/candlesticks", f"/historical/markets/{m['ticker']}/candlesticks"):
        r = kget(path, start_ts=t0, end_ts=t1, period_interval=period)
        if r and r.get("candlesticks"):
            return r["candlesticks"]
    return []


def binance_1m(start_s: int, end_s: int) -> dict[int, float]:
    """Close price of each 1m bar keyed by the bar's CLOSE second (open + 60)."""
    out, t = {}, start_s * 1000
    while t < end_s * 1000:
        CALLS["binance"] += 1
        raw = get(BINANCE + "/api/v3/klines", symbol="BTCUSDT", interval="1m", startTime=t, limit=1000)
        if not raw:
            break
        for k in raw:
            out[k[0] // 1000 + 60] = float(k[4])
        t = raw[-1][0] + 60_000
    return out


class Spot:
    def __init__(self, px: dict[int, float]):
        self.px = px
        self.keys = sorted(px)
        self.lr = {}
        for a, b in zip(self.keys, self.keys[1:]):
            if b - a == 60:
                self.lr[b] = math.log(px[b] / px[a])

    def at(self, t: int) -> float | None:
        m = t - t % 60
        for k in (m, m - 60, m - 120):
            if k in self.px:
                return self.px[k]
        return None

    def vol(self, t: int, window_min=1440) -> float | None:
        """Annualised realised vol from 1m log returns over the trailing window (causal)."""
        m = t - t % 60
        xs = [self.lr[k] for k in range(m - window_min * 60 + 60, m + 60, 60) if k in self.lr]
        if len(xs) < window_min // 2:
            return None
        v = math.sqrt(sum(x * x for x in xs) / len(xs) * 525_600)
        return min(3.0, max(0.1, v))


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def p_above(s, k, sig, tau_s):
    if k <= 0:
        return 1.0
    st = sig * math.sqrt(max(tau_s, 1) / 31_536_000)
    return phi((math.log(s / k) - 0.5 * st * st) / st)


def fair_value(m: dict, s: float, sig: float, tau: int) -> float | None:
    st, lo, hi = m.get("strike_type"), m.get("floor_strike"), m.get("cap_strike")
    if st in ("greater", "greater_or_equal") and lo is not None:
        return p_above(s, float(lo), sig, tau)
    if st in ("less", "less_or_equal") and hi is not None:
        return 1 - p_above(s, float(hi), sig, tau)
    if st == "between" and lo is not None and hi is not None:
        return max(0.0, p_above(s, float(lo), sig, tau) - p_above(s, float(hi), sig, tau))
    return None


def strike_mid(m):
    lo, hi = m.get("floor_strike"), m.get("cap_strike")
    vals = [float(x) for x in (lo, hi) if x is not None]
    return sum(vals) / len(vals) if vals else None


def build_rows(series: str, days: int, max_markets: int, per_event: int) -> tuple[list[dict], dict]:
    ms = [m for m in list_markets(series, days) if fair_value(m, 1.0, 0.5, 3600) is not None]
    if not ms:
        return [], {"markets_listed": 0}
    opens = [ts(m["open_time"]) for m in ms]
    closes = [ts(m["close_time"]) for m in ms]
    print(f"fetching Binance 1m {datetime.fromtimestamp(min(opens), timezone.utc):%Y-%m-%d} → now", file=sys.stderr)
    spot = Spot(binance_1m(min(opens) - 86_400 - 120, max(closes) + 120))
    # Near-the-money at OPEN (causal), at most `per_event` strikes per event, most recent events first.
    by_ev = defaultdict(list)
    for m in ms:
        s0 = spot.at(ts(m["open_time"]))
        k = strike_mid(m)
        if s0 and k:
            by_ev[m["event_ticker"]].append((abs(k / s0 - 1), m))
    chosen = []
    for ev in sorted(by_ev, key=lambda e: -max(ts(m["close_time"]) for _, m in by_ev[e])):
        chosen += [m for _, m in sorted(by_ev[ev], key=lambda x: x[0])[:per_event]]
        if len(chosen) >= max_markets:
            break
    chosen = chosen[:max_markets]
    print(f"replaying {len(chosen)} markets from {len(by_ev)} events", file=sys.stderr)
    rows = []
    for n, m in enumerate(chosen):
        life = ts(m["close_time"]) - ts(m["open_time"])
        period = 1 if life <= 3 * 3600 else 60
        cs = candles(series, m, period)
        prev_mid = None
        close_t = ts(m["close_time"])
        for c in cs:
            t = int(c["end_period_ts"])
            bid, ask = cents(c.get("yes_bid")), cents(c.get("yes_ask"))
            tau = close_t - t
            if bid is None or ask is None or not (0 < bid < ask < 100) or tau < 60:
                prev_mid = None
                continue
            mid = (bid + ask) / 200
            s, sig = spot.at(t), spot.vol(t)
            if s is None or sig is None:
                prev_mid = mid
                continue
            rows.append({"ticker": m["ticker"], "event": m["event_ticker"], "t": t, "tau": tau, "life": life,
                         "bid": bid / 100, "ask": ask / 100, "mid": mid, "prev_mid": prev_mid,
                         "fair": fair_value(m, s, sig, tau), "spot": s, "vol": sig,
                         "y": 1.0 if m["result"] == "yes" else 0.0, "oi": c.get("open_interest")})
            prev_mid = mid
        if n % 100 == 0:
            print(f"  {n}/{len(chosen)} markets, {len(rows)} decision rows", file=sys.stderr)
    return rows, {"markets_listed": len(ms), "markets_replayed": len(chosen), "events": len(by_ev)}


# ---------- strategies ----------

def fee(p):
    return 0.07 * p * (1 - p)


def signal(rule, r, th, max_spread):
    """Return ('yes'|'no', price) or None, using only this row."""
    if r["ask"] - r["bid"] > max_spread:
        return None
    if rule == "model_edge":
        if r["fair"] - r["ask"] >= th:
            return "yes", r["ask"]
        if (1 - r["fair"]) - (1 - r["bid"]) >= th:
            return "no", 1 - r["bid"]
    elif rule in ("momentum", "fade"):
        if r["prev_mid"] is None:
            return None
        d = r["mid"] - r["prev_mid"]
        if abs(d) < th:
            return None
        up = d > 0 if rule == "momentum" else d < 0
        return ("yes", r["ask"]) if up else ("no", 1 - r["bid"])
    elif rule == "longshot":
        if r["ask"] <= th:          # yes is a longshot: sell it (buy NO)
            return "no", 1 - r["bid"]
        if r["bid"] >= 1 - th:      # yes is a heavy favourite: buy it
            return "yes", r["ask"]
    return None


RULES = {"model_edge": [0.03, 0.05, 0.08, 0.12, 0.18], "momentum": [0.03, 0.05, 0.08, 0.12],
         "fade": [0.03, 0.05, 0.08, 0.12], "longshot": [0.05, 0.10, 0.15]}


def trades_for(rows_by_mkt, rule, th, max_spread):
    out = []
    for tk, rs in rows_by_mkt.items():
        for r in rs:
            sg = signal(rule, r, th, max_spread)
            if sg:
                side, p = sg
                win = r["y"] if side == "yes" else 1 - r["y"]
                out.append({"t": r["t"], "ticker": tk, "side": side, "price": p, "pnl": win - p - fee(p),
                            "tau": r["tau"], "life": r["life"]})
                break
    return out


def summarise(tr):
    if not tr:
        return {"n": 0}
    pn = [x["pnl"] for x in tr]
    n = len(pn)
    mu = sum(pn) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in pn) / max(1, n - 1))
    cost = sum(x["price"] for x in tr)
    return {"n": n, "win": sum(1 for x in tr if x["pnl"] > 0) / n, "avg_c": mu * 100, "total": sum(pn),
            "roi": sum(pn) / cost if cost else 0, "t": mu / (sd / math.sqrt(n)) if sd > 0 else 0}


def month(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m")


def walk_forward(rows_by_mkt, rule, max_spread):
    """Each month trades with the threshold that had the best total P&L on all earlier months."""
    by_th = {th: trades_for(rows_by_mkt, rule, th, max_spread) for th in RULES[rule]}
    months = sorted({month(x["t"]) for trs in by_th.values() for x in trs})
    oos, picks = [], []
    for i, mo in enumerate(months[1:], 1):
        past = set(months[:i])
        best = max(RULES[rule], key=lambda th: sum(x["pnl"] for x in by_th[th] if month(x["t"]) in past))
        picks.append((mo, best))
        oos += [x for x in by_th[best] if month(x["t"]) == mo]
    return by_th, oos, picks


def brier(rows, key):
    return sum((r[key] - r["y"]) ** 2 for r in rows) / len(rows)


def calibration(rows, key, edges=(0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001)):
    out = []
    for a, b in zip(edges, edges[1:]):
        xs = [r for r in rows if a <= r[key] < b]
        if xs:
            out.append((a, b, len(xs), sum(r[key] for r in xs) / len(xs), sum(r["y"] for r in xs) / len(xs)))
    return out


def report(series, days, rows, meta, max_spread):
    L = [f"# Kalshi line-movement replay — {series}, last {days} days",
         "", f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Research only: public data, no orders.", ""]
    if not rows:
        L += ["**No usable data.** " + json.dumps(meta), ""]
        return "\n".join(L), {"meta": meta}
    by_mkt = defaultdict(list)
    for r in rows:
        by_mkt[r["ticker"]].append(r)
    for v in by_mkt.values():
        v.sort(key=lambda r: r["t"])
    t0, t1 = min(r["t"] for r in rows), max(r["t"] for r in rows)
    L += [f"{meta.get('markets_replayed')} markets from {meta.get('events')} events "
          f"({datetime.fromtimestamp(t0, timezone.utc):%Y-%m-%d} → {datetime.fromtimestamp(t1, timezone.utc):%Y-%m-%d}), "
          f"{len(rows):,} candle decision points. Spread filter ≤ {max_spread * 100:.0f}¢. "
          "Each rule: one trade per market at its first signal, pays the ask, Kalshi taker fee, held to settlement.", ""]
    # Calibration
    L += ["## Who forecasts better: the market price or the model?", "",
          f"Brier score (lower is better) over all decision points — market mid **{brier(rows, 'mid'):.4f}**, "
          f"lognormal model **{brier(rows, 'fair'):.4f}**, always-50% {brier([dict(r, h=0.5) for r in rows], 'h'):.4f}.", ""]
    L += ["| market price bucket | points | avg price | actually settled YES |", "|---|---|---|---|"]
    for a, b, n, p, y in calibration(rows, "mid"):
        L.append(f"| {a:.0%}–{min(b, 1):.0%} | {n:,} | {p:.1%} | {y:.1%} |")
    # Does line movement predict anything beyond the price?
    mv = [(r["mid"] - r["prev_mid"], r["y"] - r["mid"]) for r in rows if r["prev_mid"] is not None]
    if len(mv) > 30:
        mx = sum(a for a, _ in mv) / len(mv); my = sum(b for _, b in mv) / len(mv)
        cov = sum((a - mx) * (b - my) for a, b in mv)
        va = math.sqrt(sum((a - mx) ** 2 for a, _ in mv)); vb = math.sqrt(sum((b - my) ** 2 for _, b in mv))
        corr = cov / (va * vb) if va and vb else 0
        L += ["", f"Line movement vs what was left to win: correlation of the last candle's price move with "
              f"(outcome − price) = **{corr:+.3f}** over {len(mv):,} points "
              "(positive = moves under-react, so following them pays; negative = moves over-react, so fading pays)."]
    # Strategies
    L += ["", "## Rules, walk-forward (threshold picked on earlier months only)", "",
          "| rule | trades | win rate | avg P&L / contract | total $ per 1 contract | ROI on cost | t-stat | thresholds used |",
          "|---|---|---|---|---|---|---|---|"]
    out = {"meta": meta, "rules": {}}
    detail = []
    for rule in RULES:
        by_th, oos, picks = walk_forward(by_mkt, rule, max_spread)
        s = summarise(oos)
        used = ", ".join(f"{mo}:{th:g}" for mo, th in picks) or "–"
        if s["n"]:
            L.append(f"| {rule} | {s['n']} | {s['win']:.0%} | {s['avg_c']:+.2f}¢ | {s['total']:+.2f} | {s['roi']:+.1%} | {s['t']:+.2f} | {used} |")
        else:
            L.append(f"| {rule} | 0 | – | – | – | – | – | {used} |")
        out["rules"][rule] = {"walk_forward": s, "picks": picks,
                              "by_threshold": {str(th): summarise(v) for th, v in by_th.items()}}
        detail.append((rule, by_th))
    L += ["", "## Every threshold, whole period (in-sample — for context, not for picking)", "",
          "| rule | threshold | trades | win rate | avg P&L / contract | ROI | t-stat | first 60% avg | last 40% avg |",
          "|---|---|---|---|---|---|---|---|---|"]
    cut = t0 + (t1 - t0) * 0.6
    for rule, by_th in detail:
        for th, tr in by_th.items():
            s = summarise(tr)
            if not s["n"]:
                continue
            a = summarise([x for x in tr if x["t"] < cut]); b = summarise([x for x in tr if x["t"] >= cut])
            fa = f"{a['avg_c']:+.2f}¢ ({a['n']})" if a["n"] else "–"
            fb = f"{b['avg_c']:+.2f}¢ ({b['n']})" if b["n"] else "–"
            L.append(f"| {rule} | {th:g} | {s['n']} | {s['win']:.0%} | {s['avg_c']:+.2f}¢ | {s['roi']:+.1%} | {s['t']:+.2f} | {fa} | {fb} |")
    L += ["", "Notes: Kalshi settles on the CF Benchmarks BTC index, the model uses Binance BTCUSDT (a small basis). "
          "Fills at the quoted ask ignore size and queue; real fills on thin strikes will be worse. "
          "A |t-stat| under ~2 is indistinguishable from luck.", ""]
    return "\n".join(L), out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", default="KXBTCD")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--max-markets", type=int, default=2000)
    ap.add_argument("--per-event", type=int, default=6)
    ap.add_argument("--max-spread", type=float, default=0.10)
    ap.add_argument("--out", default="kalshi_report.md")
    ap.add_argument("--rows-cache")
    a = ap.parse_args()
    t_start = time.time()
    if a.rows_cache and Path(a.rows_cache).exists():
        blob = json.loads(Path(a.rows_cache).read_text()); rows, meta = blob["rows"], blob["meta"]
    else:
        rows, meta = build_rows(a.series, a.days, a.max_markets, a.per_event)
        if a.rows_cache:
            Path(a.rows_cache).write_text(json.dumps({"rows": rows, "meta": meta}))
    meta["api_calls"] = dict(CALLS); meta["seconds"] = round(time.time() - t_start)
    md, js = report(a.series, a.days, rows, meta, a.max_spread)
    Path(a.out).write_text(md)
    Path(a.out).with_suffix(".json").write_text(json.dumps(js, indent=1, default=str))
    print(md)
