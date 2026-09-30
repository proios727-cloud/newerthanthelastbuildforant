"""Paper crypto trend book: vol-targeted, long/flat, traded through spot ETFs (the research's S-TREND).

Signal on Coinbase daily closes (BTC, ETH, SOL; crypto trades 24/7), orders in the ETF proxies (IBIT, ETHA,
BSOL) at the next US close: ETF spreads are a few basis points against 40-95 bp per side for crypto spot
at retail tiers (docs/research/crypto-strategies.md).

  on    SMA20 > SMA100 on the last 2 completed closes     off   SMA20 < SMA100 on the last 2
  stop  close < 80% of the highest close since entry (trailing)
  weight  sleeve x min(1, 30% / RV30)   sleeves BTC 50%, ETH 30%, SOL 20%; the rest sits in cash at the T-bill rate
  trade   only when the target crosses zero or moves more than 20% from what is held; buy at the ask, sell at the bid
  kill    a book 20% below its peak sells everything and arms the desk's kill switch

Two books run the same rules: $500 and $10k. JEV may veto buys (data error, structural crypto event,
order mistake); sells, stops and kills never go to JEV. Paper only; nothing here can place an order.
"""
import json
import math
from datetime import date, datetime, timedelta, timezone

STRATEGY_ID = "trend-etf-v1"
ASSETS = {"BTC": ("COINBASE:BTCUSD", "IBIT", 0.50), "ETH": ("COINBASE:ETHUSD", "ETHA", 0.30),
          "SOL": ("COINBASE:SOLUSD", "BSOL", 0.20)}
FAST, SLOW, RV_DAYS, VOL_TARGET = 20, 100, 30, 0.30
TRAIL, REBAL, DD_KILL = 0.80, 0.20, 0.20
BOOKS = {"b500": 500.0, "b10k": 10_000.0}
TBILL_DEFAULT = 0.0424     # 3-month T-bill, 2026-09-25 (research snapshot); pass "tbill" in the quotes file to update


def new_state():
    return {"bars": {}, "signal": {a: {"on": False, "peak": None} for a in ASSETS},
            "books": {n: {"start": v, "cash": v, "shares": {}, "peak_nav": v, "killed": None,
                          "trades": [], "log": []} for n, v in BOOKS.items()},
            "last_apply": None, "last_signal_bar": None}


def ingest(st, raw, now=None):
    """raw = {"BTC": [[t_unix, close], ...], ...} as TradingView returns them. Keeps completed daily bars only."""
    now = now or datetime.now(timezone.utc).timestamp()
    out = {}
    for a in ASSETS:
        rows = sorted((int(t), float(c)) for t, c in raw.get(a, []) if int(t) + 86400 <= now and float(c) > 0)
        if len(rows) >= SLOW + 2:
            st["bars"][a] = {"closes": [c for _, c in rows],
                             "last": datetime.fromtimestamp(rows[-1][0], timezone.utc).date().isoformat()}
        out[a] = {"kept": len(rows), "last": st["bars"].get(a, {}).get("last")}
    return out


def _sma(xs, n, end):
    return sum(xs[end - n:end]) / n


def indicators(closes):
    n = len(closes)
    f1, s1 = _sma(closes, FAST, n), _sma(closes, SLOW, n)
    f0, s0 = _sma(closes, FAST, n - 1), _sma(closes, SLOW, n - 1)
    lr = [math.log(closes[i] / closes[i - 1]) for i in range(n - RV_DAYS, n)]
    m = sum(lr) / len(lr)
    rv = math.sqrt(sum((x - m) ** 2 for x in lr) / (len(lr) - 1)) * math.sqrt(365)
    return {"sma20": round(f1, 4), "sma100": round(s1, 4), "rv30": round(rv, 4),
            "up2": f1 > s1 and f0 > s0, "down2": f1 < s1 and f0 < s0, "close": closes[-1]}


def update_signals(st):
    """Advance each asset's on/off state and trailing peak once per new completed bar. {asset: target weight}."""
    targets = {}
    for a, (_, _, sleeve) in ASSETS.items():
        b = st["bars"].get(a)
        if not b or len(b["closes"]) < SLOW + 2:
            targets[a] = 0.0
            continue
        ind, sig = indicators(b["closes"]), st["signal"][a]
        if not sig["on"] and ind["up2"]:
            sig.update(on=True, peak=ind["close"])
        elif sig["on"]:
            sig["peak"] = max(sig["peak"] or ind["close"], ind["close"])
            if ind["down2"] or ind["close"] < TRAIL * sig["peak"]:
                sig.update(on=False, peak=None, exit_reason="cross" if ind["down2"] else "trailing stop")
        sig["ind"] = ind
        targets[a] = round(sleeve * min(1.0, VOL_TARGET / ind["rv30"]), 4) if sig["on"] and ind["rv30"] > 0 else 0.0
    return targets


def good_quote(q):
    return bool(q) and q.get("bid", 0) > 0 and q.get("ask", 0) > 0 and q["bid"] <= q["ask"]


def mid(q):
    return (q["bid"] + q["ask"]) / 2


def nav(book, quotes):
    v = book["cash"]
    for etf, qty in book["shares"].items():
        q = quotes.get(etf)
        v += qty * (mid(q) if good_quote(q) else book.get("last_px", {}).get(etf, 0.0))
    return round(v, 2)


def _trade(book, name, a, etf, qty, px, q, today, why, verdict=None):
    side = "buy" if qty > 0 else "sell"
    book["cash"] -= qty * px
    book["shares"][etf] = round(book["shares"].get(etf, 0.0) + qty, 6)
    if abs(book["shares"][etf]) < 1e-6:
        book["shares"].pop(etf)
    rec = {"date": today.isoformat(), "book": name, "asset": a, "etf": etf, "side": side, "qty": round(abs(qty), 6),
           "fill_px": px, "expected_px": round(mid(q), 4), "slip": round(abs(px - mid(q)), 4), "why": why,
           "strategy_id": STRATEGY_ID, "decision_id": f"{STRATEGY_ID}:{name}:{today.isoformat()}:{etf}",
           "jev_mode": (verdict or {}).get("mode"), "jev_answers": (verdict or {}).get("answers"),
           "jev_schema_version": (verdict or {}).get("schema")}
    book["trades"].append(rec)
    book["log"].append({**rec, "kind": "trend_trade"})
    return rec


def apply(st, quotes, today, judge_fn=None, kill=None):
    """quotes = {"IBIT": {"bid", "ask"}, "ETHA": {...}, "BSOL": {...}, "tbill": 0.0424 (optional)}.
    Returns {"events": [...], "kill": reason or None, "targets": {...}}."""
    t = today.isoformat()
    if st["last_apply"] == t:
        return {"skipped": "already applied today"}
    events, arm = [], None
    stale = [a for a in ASSETS if not st["bars"].get(a)
             or date.fromisoformat(st["bars"][a]["last"]) < today - timedelta(days=2)]
    targets = {a: 0.0 for a in ASSETS}
    if not stale and st["last_signal_bar"] != st["bars"]["BTC"]["last"]:
        targets = update_signals(st)
        st["last_signal_bar"] = st["bars"]["BTC"]["last"]
    elif not stale:
        targets = {a: (round(ASSETS[a][2] * min(1.0, VOL_TARGET / st["signal"][a]["ind"]["rv30"]), 4)
                       if st["signal"][a]["on"] else 0.0) for a in ASSETS}
    tbill = float(quotes.get("tbill", TBILL_DEFAULT))
    days = (today - date.fromisoformat(st["last_apply"])).days if st["last_apply"] else 0

    for name, book in st["books"].items():
        book["cash"] += book["cash"] * tbill * days / 365 if book["cash"] > 0 else 0.0
        for etf, q in quotes.items():
            if isinstance(q, dict) and good_quote(q):
                book.setdefault("last_px", {})[etf] = round(mid(q), 4)
        v = nav(book, quotes)
        book["peak_nav"] = max(book["peak_nav"], v)
        if stale:
            book["log"].append({"date": t, "kind": "trend_skip", "reason": f"stale or missing bars: {stale}"})
            continue
        if not book["killed"] and v <= (1 - DD_KILL) * book["peak_nav"]:
            book["killed"] = f"{name} NAV {v} is {DD_KILL:.0%} below peak {book['peak_nav']}"
            arm = book["killed"]
        for a, (_, etf, _) in ASSETS.items():
            q, held = quotes.get(etf), book["shares"].get(etf, 0.0)
            if not good_quote(q):
                book["log"].append({"date": t, "kind": "trend_skip", "etf": etf, "reason": "no, zero or crossed quote"})
                continue
            tw = 0.0 if book["killed"] else targets[a]
            held_w = held * mid(q) / v if v > 0 else 0.0
            if not ((tw == 0) != (held_w == 0) or (held_w > 0 and abs(tw - held_w) > REBAL * held_w)):
                continue
            qty = (tw * v - held * mid(q)) / (q["ask"] if tw * v > held * mid(q) else q["bid"])
            if tw == 0:
                qty = -held
            if qty < 0:                                   # sells, stops and kills never wait on JEV
                why = "kill" if book["killed"] else ("exit" if tw == 0 else "trim")
                events.append(_trade(book, name, a, etf, qty, q["bid"], q, today, why))
                continue
            if kill:
                book["log"].append({"date": t, "kind": "trend_skip", "etf": etf, "reason": f"kill switch: {kill}"})
                continue
            verdict = None
            if judge_fn:
                verdict = judge_fn(a, {"etf": etf, "side": "buy", "qty": round(qty, 6), "ask": q["ask"], "bid": q["bid"],
                                       "target_weight": tw, "held_weight": round(held_w, 4), "nav": v,
                                       "signal": st["signal"][a].get("ind"), "bar_date": st["bars"][a]["last"]})
                if verdict and verdict.get("veto"):
                    book["log"].append({"date": t, "kind": "trend_skip", "etf": etf, "reason": f"jev {verdict['veto'][0]}",
                                        "detail": verdict["veto"][1], "jev_answers": verdict.get("answers")})
                    continue
            events.append(_trade(book, name, a, etf, qty, q["ask"], q, today, "entry" if held == 0 else "add", verdict))
    st["last_apply"] = t
    return {"events": events, "kill": arm, "targets": targets, "stale": stale}


def summary(st, quotes=None):
    quotes = quotes or {}
    out = {"signal": {a: {"on": s["on"], **{k: s.get("ind", {}).get(k) for k in ("sma20", "sma100", "rv30", "close")}}
                      for a, s in st["signal"].items()},
           "bars_through": {a: b["last"] for a, b in st["bars"].items()}}
    for name, b in st["books"].items():
        v = nav(b, quotes)
        out[name] = {"nav": v, "return_pct": round(100 * (v / b["start"] - 1), 3),
                     "exposure_pct": round(100 * (1 - b["cash"] / v), 1) if v else None,
                     "holdings": {e: round(q, 4) for e, q in b["shares"].items()}, "trades": len(b["trades"]),
                     "drawdown_pct": round(100 * (1 - v / b["peak_nav"]), 2), "killed": b["killed"]}
    return out


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else new_state()


def save(st, path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
