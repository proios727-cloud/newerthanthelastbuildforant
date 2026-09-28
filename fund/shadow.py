"""Quant Scanner signals and the shadow book.

The shadow book trades every signal the Risk Officer passes, at the daily close, in a separate
paper ledger (ledger/shadow.json). It never touches the real paper book and never needs EXECUTE:
it measures what the desk *would* have done, so the 30-day run tests the signals and the risk rules,
not just the marking path.

Signals (long only, on daily closes):
  momentum        close > SMA20 > SMA50 and the 20-day return is positive
  breakout        close above the highest of the prior 20 closes
  mean_reversion  RSI(2) < 10 while close > SMA50 (a dip inside an uptrend)
Exits: stop at close·(1 − 2σ), target at close·(1 + 4σ), with σ the 20-day stdev of daily returns;
or after MAX_HOLD bars. Fills are at the close with the desk's fees; there is no spread model, so
shadow P&L is optimistic by roughly half the spread per side.
"""
import json
import math
from datetime import datetime, time, timedelta, timezone

from . import clock, risk
from .ledger import Ledger
from .preview import fee

MIN_BARS = 51
MAX_HOLD = 5
STOP_SIGMA, TARGET_SIGMA = 2.0, 4.0


# ---- indicators -----------------------------------------------------------
def sma(c, n):
    return sum(c[-n:]) / n


def rsi(c, n=2):
    ch = [b - a for a, b in zip(c[-n - 1:-1], c[-n:])]
    up = sum(x for x in ch if x > 0)
    dn = -sum(x for x in ch if x < 0)
    return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)


def sigma(c, n=20):
    r = [b / a - 1 for a, b in zip(c[-n - 1:-1], c[-n:])]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1))


def signals(closes):
    """[(signal, score)] for one symbol, strongest first. Needs MIN_BARS closes."""
    c = closes
    if len(c) < MIN_BARS:
        return []
    px, s20, s50 = c[-1], sma(c, 20), sma(c, 50)
    ret20 = px / c[-21] - 1
    out = []
    if px > s20 > s50 and ret20 > 0:
        out.append(("momentum", ret20))
    if px > max(c[-21:-1]):
        out.append(("breakout", px / max(c[-21:-1]) - 1))
    r2 = rsi(c)
    if r2 < 10 and px > s50:
        out.append(("mean_reversion", (10 - r2) / 100))
    return sorted(out, key=lambda x: -x[1])


def scan(bars):
    """Ranked signal list across the universe: one row per symbol (its strongest signal)."""
    rows = []
    for sym, b in bars.items():
        sig = signals(b["closes"])
        if not sig:
            continue
        c = b["closes"]
        sd = sigma(c)
        rows.append({"symbol": sym, "signal": sig[0][0], "score": round(sig[0][1], 5),
                     "also": [s for s, _ in sig[1:]], "close": c[-1], "bar": b["last"],
                     "stop": round(c[-1] * (1 - STOP_SIGMA * sd), 6),
                     "target": round(c[-1] * (1 + TARGET_SIGMA * sd), 6)})
    return sorted(rows, key=lambda r: -r["score"])


# ---- bar dates ------------------------------------------------------------
def bar_ts(asset, day):
    """When a daily close is 'traded': 15:59 ET for equities (a market-on-close proxy inside the
    session), 23:59 UTC for crypto (the UTC daily bar's close)."""
    d = datetime.fromisoformat(day).date()
    if asset == "crypto":
        return datetime.combine(d, time(23, 59), tzinfo=timezone.utc)
    return datetime.combine(d, time(15, 59), tzinfo=clock.ET)


def bar_complete(asset, t_unix, now):
    """A TradingView daily bar is final once its session is over."""
    start = datetime.fromtimestamp(t_unix, timezone.utc)
    if asset == "crypto":
        return start + timedelta(days=1) <= now
    et = clock.to_et(start)
    return clock.to_et(now) >= datetime.combine(et.date(), time(16, 15), tzinfo=clock.ET)


def append_bars(bars, cfg, raw, now):
    """Merge raw connector bars {symbol: [[t_unix, close], ...]} into bars.json (completed, newer
    bars only). Returns {symbol: [dates added]}."""
    added = {}
    for sym, rows in raw.items():
        if sym not in bars:
            raise KeyError(f"{sym} is not in ledger/bars.json")
        asset = cfg.asset(sym)
        b = bars[sym]
        for t, c in sorted(rows):
            day = datetime.fromtimestamp(t, timezone.utc).date().isoformat()
            if day <= b["last"] or not bar_complete(asset, t, now):
                continue
            if c <= 0:
                raise ValueError(f"{sym} {day}: close must be positive")
            b["closes"].append(float(c))
            b["last"] = day
            added.setdefault(sym, []).append(day)
        b["closes"] = b["closes"][-120:]
    return added


# ---- the shadow book --------------------------------------------------------
class Shadow:
    def __init__(self, ledger, meta=None, done=None):
        self.ledger = ledger
        self.meta = meta or {}     # symbol -> {signal, stop, target, entry_bar, bars_held}
        self.done = done or {}     # symbol -> last bar date already processed

    @classmethod
    def new(cls, cfg):
        return cls(Ledger(cfg.starting_nav))

    def to_dict(self):
        return {"ledger": self.ledger.to_dict(), "meta": self.meta, "done": self.done}

    @classmethod
    def from_dict(cls, d):
        return cls(Ledger.from_dict(d["ledger"]), d["meta"], d["done"])

    def step(self, bars, cfg, events=()):
        """Process every symbol whose newest bar hasn't been seen. Bars are handled in time order
        (so the fund-day roll only moves forward); at each close: mark, exit, then enter.
        Returns a list of event dicts (shadow_fill / shadow_veto / shadow_exit)."""
        out = []
        fresh = {s: b for s, b in bars.items() if b["last"] > self.done.get(s, "")}
        groups = {}
        for s, b in fresh.items():
            groups.setdefault(bar_ts(cfg.asset(s), b["last"]), {})[s] = b
        for ts in sorted(groups):
            g = groups[ts]
            for s, b in g.items():
                self.ledger.mark(s, b["closes"][-1], ts)
            exited = set()
            for s in g:
                ev = self._exit(s, bars[s]["closes"][-1], ts, cfg)
                exited.update(e["symbol"] for e in ev)
                out += ev
            for row in scan(g):
                if row["symbol"] not in exited:  # no re-entry on the bar we just left
                    out += self._enter(row, ts, cfg, events)
            for s, b in g.items():
                self.done[s] = b["last"]
        return out

    def _exit(self, s, px, ts, cfg):
        q, m = self.ledger.qty(s), self.meta.get(s)
        if not q or not m:
            return []
        m["bars_held"] += 1
        why = ("stop" if px <= m["stop"] else "target" if px >= m["target"]
               else "time" if m["bars_held"] >= MAX_HOLD else None)
        if not why:
            return []
        rec = self.ledger.fill(s, "sell", q, px, ts, fee=fee(cfg, s, q, px), ref=f"shadow-{why}")
        self.meta.pop(s)
        return [{"kind": "shadow_exit", "ts": ts.isoformat(), "symbol": s, "why": why, "qty": q,
                 "price": px, "realized": round(rec["realized"] - rec["fee"], 2)}]

    def _enter(self, row, ts, cfg, events):
        L, s, px = self.ledger, row["symbol"], row["close"]
        if L.qty(s):
            return []
        want = cfg.limits.max_position_pct / 100 * L.nav() / px
        v = risk.check(risk.Order(s, "buy", want, px, ts), L, cfg, ts, events)
        if not v.passed:
            return [{"kind": "shadow_veto", "ts": ts.isoformat(), "symbol": s, "signal": row["signal"],
                     "rule": v.rules[0][0], "detail": v.rules[0][1]}]
        L.fill(s, "buy", v.max_qty, px, ts, fee=fee(cfg, s, v.max_qty, px), ref=f"shadow-{row['signal']}")
        self.meta[s] = {"signal": row["signal"], "stop": row["stop"], "target": row["target"],
                        "entry_bar": row["bar"], "bars_held": 0}
        return [{"kind": "shadow_fill", "ts": ts.isoformat(), "symbol": s, "signal": row["signal"],
                 "qty": v.max_qty, "price": px, "stop": row["stop"], "target": row["target"]}]

    def summary(self):
        L = self.ledger
        exits = [f for f in L.fills if f["side"] == "sell"]
        wins = sum(1 for f in exits if f["realized"] - f["fee"] > 0)
        return {"nav": round(L.nav(), 2), "return_pct": round(100 * (L.nav() / L.starting_nav - 1), 3),
                "drawdown_pct": round(L.drawdown_pct(), 3), "open": sorted(self.meta),
                "closed_trades": len(exits), "win_rate": round(wins / len(exits), 3) if exits else None}


def load(path, cfg):
    return Shadow.from_dict(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else Shadow.new(cfg)


def save(sh, path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sh.to_dict(), indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
