"""Risk Officer rules as pure functions. PASS carries a max size; VETO names the rule it broke.

Orders that only reduce an existing position (exits) bypass halts, blackout, spread and sizing
caps — the desk must always be able to get smaller — but still need a fresh quote and an open session.
"""
import math
from dataclasses import dataclass, field
from datetime import timedelta

from . import clock


@dataclass
class Order:
    symbol: str
    side: str            # buy | sell
    qty: float
    price: float         # reference price (last or mid)
    quote_ts: object     # aware datetime of the quote
    bid: float = None
    ask: float = None
    adv: float = None    # average daily volume, in units of the symbol


@dataclass
class Verdict:
    status: str                       # PASS | VETO
    max_qty: float = 0.0
    reducing: bool = False
    rules: list = field(default_factory=list)   # [(rule, detail)]

    @property
    def passed(self):
        return self.status == "PASS"


def _veto(rule, detail, reducing=False):
    return Verdict("VETO", 0.0, reducing, [(rule, detail)])


def _round_qty(asset, q):
    if q <= 0:
        return 0.0
    return float(math.floor(q)) if asset == "equity" else math.floor(q * 1e6) / 1e6


def spread_bps(bid, ask):
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2
    return (ask - bid) / mid * 1e4


def check(order, ledger, cfg, now, events=()):
    L = cfg.limits
    sym = order.symbol
    if sym not in cfg.universe:
        return _veto("universe", f"{sym} is not in the pinned universe")
    if order.side not in ("buy", "sell") or order.qty <= 0 or order.price <= 0:
        return _veto("malformed", "side must be buy/sell; qty and price must be positive")
    asset = cfg.asset(sym)

    age = (now - order.quote_ts).total_seconds()
    if age > L.max_quote_age_sec or age < -5:
        return _veto("stale_quote", f"quote age {age:.0f}s > {L.max_quote_age_sec:.0f}s")
    if not clock.can_trade(asset, now):
        return _veto("session", "equity orders only 09:30–16:00 ET on weekdays")

    s = 1 if order.side == "buy" else -1
    q = ledger.qty(sym)
    reducing = q != 0 and (q > 0) != (s > 0) and order.qty <= abs(q)
    if reducing:
        return Verdict("PASS", order.qty, True, [("reducing", "exit/trim — halts and caps do not apply")])

    sp = spread_bps(order.bid, order.ask)
    cap_sp = L.max_spread_bps[asset]
    if sp is not None and sp > cap_sp:
        return _veto("spread", f"spread {sp:.1f} bps > {cap_sp} bps")

    if ledger.day_pnl_pct() <= -L.day_loss_halt_pct:
        return _veto("day_loss_halt", f"day P&L {ledger.day_pnl_pct():.2f}% ≤ −{L.day_loss_halt_pct}%")
    if ledger.drawdown_pct() >= L.drawdown_halt_pct:
        return _veto("drawdown_halt", f"drawdown {ledger.drawdown_pct():.2f}% ≥ {L.drawdown_halt_pct}%")

    window = timedelta(minutes=L.event_blackout_min)
    for ev in events:
        if now <= ev <= now + window:
            return _veto("event_blackout", f"macro event at {clock.to_et(ev):%H:%M ET} within {L.event_blackout_min:.0f} min")

    nav = ledger.nav()
    if nav <= 0:
        return _veto("nav", "NAV is not positive")
    px = order.price

    # Every cap bounds |new position| in this symbol; the max order qty is bound − s·q.
    def mv_abs(other):
        return abs(ledger.market_value(other)) if other in ledger.marks else 0.0

    gross_ex = sum(mv_abs(o) for o in ledger.positions if o != sym)
    group = cfg.group(sym)
    group_ex = sum(mv_abs(o) for o in ledger.positions if o != sym and o in cfg.universe and cfg.group(o) == group)
    bounds = {
        "position_cap": (L.max_position_pct / 100 * nav) / px,
        "gross_cap": (L.max_gross_pct / 100 * nav - gross_ex) / px,
        "group_cap": (L.max_group_pct / 100 * nav - group_ex) / px,
    }
    caps = {rule: b - s * q for rule, b in bounds.items()}
    if order.adv:
        caps["adv_cap"] = L.max_adv_pct / 100 * order.adv

    binding = min(caps, key=caps.get)
    max_qty = _round_qty(asset, min(caps[binding], order.qty))
    if max_qty <= 0:
        return _veto(binding, f"no room: {binding} allows {max(0.0, caps[binding]):.6g} units")
    rules = [("sized_down", f"{binding} limits size to {max_qty:g} (asked {order.qty:g})")] if max_qty < order.qty else []
    return Verdict("PASS", max_qty, False, rules)
