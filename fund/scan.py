"""Quant Scanner seat: momentum, mean-reversion and breakout signals from recorded marks, ranked.

The chain follows desk.json handoffs: quant → signal_list → analyst (thesis) → risk → trader (preview).
A signal expires after `signal_ttl_min` unless the analyst attaches a thesis; a thesis holds for
`thesis_ttl_min`. Nothing is previewed without a thesis.

Price history is every mark the desk has taken (ledger/history.jsonl), one row per mark.
"""
import json
import math
import pathlib
import statistics
import uuid
from datetime import timedelta

from .ledger import parse_ts

DEFAULTS = {
    "window": 20,
    "min_obs": 21,
    "momentum_lookback": 8,
    "momentum_min_pct": 0.5,
    "z_entry": 2.0,
    "stop_sigma": 2.0,
    "reward_risk": 2.0,
    "risk_per_trade_pct": 0.5,
    "max_signals": 5,
    "allow_short": True,
    "signal_ttl_min": 15,
    "thesis_ttl_min": 30,
}


def scan_config(desk_fund):
    return {**DEFAULTS, **desk_fund.get("scan", {})}


# ---- history ---------------------------------------------------------------
def record(path, marked):
    """Append marks ({symbol, price, ts}) to the history file."""
    if not marked:
        return
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for m in marked:
            f.write(json.dumps({"symbol": m["symbol"], "price": m["price"], "ts": m["ts"]}) + "\n")


def load_history(path, keep=200):
    """symbol -> [prices] oldest first, deduplicated by timestamp, last `keep` rows."""
    path = pathlib.Path(path)
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows.setdefault(r["symbol"], {})[r["ts"]] = r["price"]
    return {s: [p for _, p in sorted(d.items(), key=lambda kv: parse_ts(kv[0]))][-keep:] for s, d in rows.items()}


# ---- signals (pure) --------------------------------------------------------
def _levels(side, last, dist, rr):
    return (last - dist, last + rr * dist) if side == "buy" else (last + dist, last - rr * dist)


def signals_for(symbol, prices, sc):
    """All setups that fire on this series. Each: {symbol, side, setup, score, price, stop, target, why}."""
    W = sc["window"]
    if len(prices) < max(sc["min_obs"], W + 1):
        return []
    last, win, prior = prices[-1], prices[-W:], prices[-W - 1:-1]
    sma, sd = statistics.fmean(win), statistics.pstdev(win)
    diffs = [b - a for a, b in zip(prices[-W - 1:-1], prices[-W:])]
    step = statistics.pstdev(diffs) or sd / math.sqrt(W) or last * 0.001
    dist = max(sc["stop_sigma"] * step, last * 0.002)
    rr, out = sc["reward_risk"], []

    hi, lo = max(prior), min(prior)
    if last > hi or last < lo:
        side = "buy" if last > hi else "sell"
        edge = hi if side == "buy" else lo
        stop, target = _levels(side, last, dist, rr)
        out.append({"setup": "breakout", "side": side, "score": 1 + abs(last - edge) / step, "stop": stop, "target": target,
                    "why": f"{'above' if side == 'buy' else 'below'} the {W}-mark {'high' if side == 'buy' else 'low'} {edge:.6g}"})

    L = sc["momentum_lookback"]
    ret = 100 * (last / prices[-1 - L] - 1)
    if abs(ret) >= sc["momentum_min_pct"] and (last > sma) == (ret > 0):
        side = "buy" if ret > 0 else "sell"
        stop, target = _levels(side, last, dist, rr)
        out.append({"setup": "momentum", "side": side, "score": abs(ret) / sc["momentum_min_pct"], "stop": stop, "target": target,
                    "why": f"{ret:+.2f}% over {L} marks, price {'above' if ret > 0 else 'below'} the {W}-mark average"})

    # Fade extremes only inside the prior range; a range break is a trend, not a reversion.
    if sd > 0 and lo <= last <= hi:
        z = (last - sma) / sd
        if abs(z) >= sc["z_entry"]:
            side = "buy" if z < 0 else "sell"
            reward = abs(sma - last)
            stop = last - reward / rr if side == "buy" else last + reward / rr
            out.append({"setup": "mean_reversion", "side": side, "score": abs(z), "stop": stop, "target": sma,
                        "why": f"z-score {z:+.2f} vs the {W}-mark average {sma:.6g}"})

    for s in out:
        s.update(symbol=symbol, price=last)
    return out


def scan(history, universe, positions, sc):
    """Rank one signal per symbol (its strongest setup). Skips shorts when disallowed and adds to open positions."""
    best = []
    for sym in universe:
        cands = []
        for s in signals_for(sym, history.get(sym, []), sc):
            q = positions.get(sym, {}).get("qty", 0.0)
            if s["side"] == "sell" and not sc["allow_short"] and q <= 0:
                continue
            if (q > 0 and s["side"] == "buy") or (q < 0 and s["side"] == "sell"):
                continue
            cands.append(s)
        if cands:
            best.append(max(cands, key=lambda s: s["score"]))
    best.sort(key=lambda s: s["score"], reverse=True)
    return best[: sc["max_signals"]]


# ---- signal book (ledger/signals.json) -------------------------------------
def new_book():
    return {"signals": {}, "counts": {"scanned": 0, "thesis": 0, "risk_passed": 0, "previewed": 0}}


def load_book(path):
    path = pathlib.Path(path)
    return {**new_book(), **json.loads(path.read_text())} if path.exists() else new_book()


def save_book(book, path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book, indent=2))


def expire(book, now, sc):
    """Mark signals past their handoff timeout as expired."""
    for s in book["signals"].values():
        if s["status"] == "new" and now - parse_ts(s["created_at"]) > timedelta(minutes=sc["signal_ttl_min"]):
            s["status"] = "expired"
        elif s["status"] == "thesis" and now - parse_ts(s["thesis"]["at"]) > timedelta(minutes=sc["thesis_ttl_min"]):
            s["status"] = "expired"


def post(book, ranked, now, sc):
    """Publish a fresh signal list: un-thesised signals from the last scan are replaced."""
    expire(book, now, sc)
    for s in book["signals"].values():
        if s["status"] == "new":
            s["status"] = "replaced"
    posted = []
    for s in ranked:
        sid = uuid.uuid4().hex[:8]
        book["signals"][sid] = {**s, "id": sid, "created_at": now.isoformat(), "status": "new"}
        posted.append(book["signals"][sid])
    book["counts"]["scanned"] += len(posted)
    return posted


def attach_thesis(book, sid, text, invalidation, now, sc):
    expire(book, now, sc)
    s = book["signals"].get(sid)
    if s is None:
        raise KeyError(f"no signal {sid}")
    if s["status"] != "new":
        raise ValueError(f"signal {sid} is {s['status']}; theses attach only to new signals")
    if not text.strip():
        raise ValueError("thesis text is required")
    if invalidation is not None:
        wrong_side = invalidation >= s["price"] if s["side"] == "buy" else invalidation <= s["price"]
        if wrong_side:
            raise ValueError(f"invalidation {invalidation} must be {'below' if s['side'] == 'buy' else 'above'} the price {s['price']}")
    s["thesis"] = {"text": text.strip(), "invalidation": invalidation, "at": now.isoformat()}
    s["status"] = "thesis"
    book["counts"]["thesis"] += 1
    return s


def risk_qty(signal, nav, sc):
    """Units that lose `risk_per_trade_pct` of NAV if the stop is hit. Risk caps it further."""
    stop = signal.get("thesis", {}).get("invalidation") or signal["stop"]
    dist = abs(signal["price"] - stop)
    qty = sc["risk_per_trade_pct"] / 100 * nav / dist if dist > 0 else 0.0
    return qty, stop
