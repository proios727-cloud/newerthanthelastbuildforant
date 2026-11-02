"""Paper broker: simulated fills against the live book and subsequent candles. State persists to disk."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


class PaperBroker:
    def __init__(self, cfg, path: Path):
        self.cfg, self.path = cfg, path
        if path.exists():
            self.s = json.loads(path.read_text())
        else:
            self.s = {"equity": cfg.starting_equity, "position": None, "pending": None, "day": None,
                      "day_start_equity": cfg.starting_equity, "day_pnl": 0.0, "trades_today": 0,
                      "cooldown": 0, "last_candle_t": None, "closed_trades": 0}

    # ---- persistence / day bookkeeping
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.s, indent=2))
        tmp.replace(self.path)

    def roll_day(self, candle_t: int):
        d = utc_day(candle_t)
        if self.s["day"] != d:
            self.s.update(day=d, day_start_equity=self.s["equity"], day_pnl=0.0, trades_today=0)

    def tick_cooldown(self):
        self.s["cooldown"] = max(0, self.s["cooldown"] - 1)

    # ---- fills
    def _fee(self, notional):
        return notional * self.cfg.fee_bps / 1e4

    def _open(self, side, qty, price, stop, target, signal_id, kind, t):
        fee = self._fee(qty * price)
        self.s["equity"] -= fee
        self.s["day_pnl"] -= fee
        self.s["trades_today"] += 1
        self.s["position"] = {"id": signal_id, "side": side, "qty": qty, "entry": price, "stop": stop,
                              "target": target, "entry_fee": fee, "opened_t": t, "entry_type": kind}
        return {"event": "fill", "leg": "entry", "order_type": kind, "side": side, "qty": qty,
                "price": round(price, 2), "fee": round(fee, 4), "trade_id": signal_id}

    def market_entry(self, side, qty, book, stop, target, signal_id, t):
        slip = 1 + (self.cfg.slippage_bps / 1e4) * (1 if side == "LONG" else -1)
        px = (book["asks"][0][0] if side == "LONG" else book["bids"][0][0]) * slip
        return self._open(side, qty, px, stop, target, signal_id, "MARKET", t)

    def place_limit(self, side, qty, book, stop, target, signal_id):
        px = book["bids"][0][0] if side == "LONG" else book["asks"][0][0]
        self.s["pending"] = {"id": signal_id, "side": side, "qty": qty, "price": px, "stop": stop,
                             "target": target, "ttl": self.cfg.limit_ttl_candles}
        return {"event": "order", "order_type": "LIMIT", "side": side, "qty": qty, "price": px, "trade_id": signal_id}

    def _close(self, price, reason, t):
        p = self.s["position"]
        sign = 1 if p["side"] == "LONG" else -1
        gross = sign * (price - p["entry"]) * p["qty"]
        fee = self._fee(p["qty"] * price)
        pnl = gross - fee - p["entry_fee"]
        self.s["equity"] += gross - fee
        self.s["day_pnl"] += gross - fee
        self.s["position"] = None
        self.s["closed_trades"] += 1
        if pnl < 0:
            self.s["cooldown"] = self.cfg.loss_cooldown_candles
        return {"event": "exit", "reason": reason, "side": p["side"], "qty": p["qty"], "entry": round(p["entry"], 2),
                "exit": round(price, 2), "pnl": round(pnl, 4), "r_multiple": round(pnl / (abs(p["entry"] - p["stop"]) * p["qty"]), 3),
                "trade_id": p["id"], "held_ms": t - p["opened_t"], "equity": round(self.s["equity"], 2)}

    def close_market(self, book, reason, t):
        if not self.s["position"]:
            return None
        long = self.s["position"]["side"] == "LONG"
        slip = 1 - (self.cfg.slippage_bps / 1e4) * (1 if long else -1)
        px = (book["bids"][0][0] if long else book["asks"][0][0]) * slip
        return self._close(px, reason, t)

    def on_candle(self, k: dict) -> list[dict]:
        """Resolve resting limit orders and stops/targets against a newly closed candle."""
        events = []
        just_filled = False
        pend = self.s["pending"]
        if pend:
            hit = k["l"] <= pend["price"] if pend["side"] == "LONG" else k["h"] >= pend["price"]
            if hit:
                self.s["pending"] = None
                events.append(self._open(pend["side"], pend["qty"], pend["price"], pend["stop"], pend["target"],
                                         pend["id"], "LIMIT", k["t"]))
                just_filled = True  # intrabar order unknown: don't also test stop/target on the fill candle
            else:
                pend["ttl"] -= 1
                if pend["ttl"] <= 0:
                    self.s["pending"] = None
                    events.append({"event": "order_expired", "trade_id": pend["id"]})
        p = self.s["position"]
        if p and not just_filled:
            long = p["side"] == "LONG"
            if (k["l"] <= p["stop"]) if long else (k["h"] >= p["stop"]):
                events.append(self._close(p["stop"], "STOP", k["close_time"]))
            elif (k["h"] >= p["target"]) if long else (k["l"] <= p["target"]):
                events.append(self._close(p["target"], "TARGET", k["close_time"]))
        return events

    def new_id(self):
        return uuid.uuid4().hex[:12]
