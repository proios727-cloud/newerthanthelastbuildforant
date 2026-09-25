"""Paper ledger: cash, signed positions, marks, fills, NAV, peak, and the fund-day roll.

Every number the board or reporter shows must come from here.
"""
import json
import pathlib
from datetime import datetime

from . import clock


def _sign(x):
    return (x > 0) - (x < 0)


class Ledger:
    def __init__(self, starting_nav, cash=None, positions=None, marks=None, fills=None,
                 peak_nav=None, day=None):
        self.starting_nav = float(starting_nav)
        self.cash = float(starting_nav if cash is None else cash)
        self.positions = positions or {}   # symbol -> {qty, avg_cost, realized}
        self.marks = marks or {}           # symbol -> {price, bid, ask, ts}
        self.fills = fills or []
        self.peak_nav = float(peak_nav if peak_nav is not None else self.starting_nav)
        self.day = day                     # {date, start_nav}

    # ---- valuation -------------------------------------------------------
    def price(self, symbol):
        m = self.marks.get(symbol)
        if m is None:
            raise KeyError(f"no mark for {symbol}")
        return m["price"]

    def market_value(self, symbol):
        p = self.positions.get(symbol)
        return 0.0 if not p or p["qty"] == 0 else p["qty"] * self.price(symbol)

    def nav(self):
        return self.cash + sum(self.market_value(s) for s in self.positions)

    def gross(self):
        return sum(abs(self.market_value(s)) for s in self.positions)

    def qty(self, symbol):
        return self.positions.get(symbol, {}).get("qty", 0.0)

    def day_pnl(self):
        return 0.0 if not self.day else self.nav() - self.day["start_nav"]

    def day_pnl_pct(self):
        return 0.0 if not self.day or not self.day["start_nav"] else 100 * self.day_pnl() / self.day["start_nav"]

    def drawdown_pct(self):
        return 0.0 if not self.peak_nav else 100 * max(0.0, self.peak_nav - self.nav()) / self.peak_nav

    # ---- events ----------------------------------------------------------
    def _roll(self, ts):
        d = clock.fund_day(ts)
        if not self.day or self.day["date"] != d:
            # snapshot NAV at the roll using the marks that were current before this event
            self.day = {"date": d, "start_nav": self.nav()}

    def _touch_peak(self):
        self.peak_nav = max(self.peak_nav, self.nav())

    def mark(self, symbol, price, ts, bid=None, ask=None):
        if price <= 0:
            raise ValueError("price must be positive")
        self._roll(ts)
        self.marks[symbol] = {"price": float(price), "bid": bid, "ask": ask, "ts": ts.isoformat()}
        self._touch_peak()

    def fill(self, symbol, side, qty, price, ts, fee=0.0, ref=None):
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        if qty <= 0 or price <= 0:
            raise ValueError("qty and price must be positive")
        self._roll(ts)
        d = qty if side == "buy" else -qty
        p = self.positions.setdefault(symbol, {"qty": 0.0, "avg_cost": 0.0, "realized": 0.0})
        q, avg = p["qty"], p["avg_cost"]
        realized = 0.0
        if q == 0 or _sign(q) == _sign(d):
            new_q = q + d
            p["avg_cost"] = (abs(q) * avg + abs(d) * price) / abs(new_q)
        else:
            closed = min(abs(d), abs(q))
            realized = closed * (price - avg) * _sign(q)
            new_q = q + d
            if new_q == 0:
                p["avg_cost"] = 0.0
            elif _sign(new_q) != _sign(q):
                p["avg_cost"] = price  # flipped through zero
        p["qty"] = new_q
        p["realized"] += realized - fee
        self.cash -= d * price + fee
        if symbol not in self.marks:
            self.marks[symbol] = {"price": float(price), "bid": None, "ask": None, "ts": ts.isoformat()}
        rec = {"ts": ts.isoformat(), "symbol": symbol, "side": side, "qty": qty, "price": price,
               "fee": fee, "realized": realized, "ref": ref}
        self.fills.append(rec)
        self._touch_peak()
        return rec

    # ---- persistence -----------------------------------------------------
    def to_dict(self):
        return {"starting_nav": self.starting_nav, "cash": self.cash, "positions": self.positions,
                "marks": self.marks, "fills": self.fills, "peak_nav": self.peak_nav, "day": self.day}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def save(self, path):
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    def snapshot(self):
        return {"nav": round(self.nav(), 2), "cash": round(self.cash, 2), "gross": round(self.gross(), 2),
                "gross_pct": round(100 * self.gross() / self.nav(), 2) if self.nav() else None,
                "day_pnl": round(self.day_pnl(), 2), "day_pnl_pct": round(self.day_pnl_pct(), 3),
                "drawdown_pct": round(self.drawdown_pct(), 3), "peak_nav": round(self.peak_nav, 2),
                "day": self.day, "positions": {s: p for s, p in self.positions.items() if p["qty"]}}


def parse_ts(s):
    return datetime.fromisoformat(s)
