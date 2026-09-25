"""Order previews and the approval gate: preview → human types the approval word → (paper) fill.

There is no live execution path. In LIVE mode `approve` refuses until a broker connector exists.
"""
import uuid
from dataclasses import asdict

from . import clock, risk
from .ledger import parse_ts


class GateError(Exception):
    pass


def fee(cfg, symbol, qty, price):
    if cfg.asset(symbol) == "crypto":
        return round(qty * price * cfg.fees["crypto_bps"] / 1e4, 2)
    return round(qty * cfg.fees["equity_per_share"], 2)


def build(order, ledger, cfg, now, events=(), stop=None, target=None):
    v = risk.check(order, ledger, cfg, now, events)
    if not v.passed:
        raise GateError(f"VETO {v.rules[0][0]}: {v.rules[0][1]}")
    limit = (order.ask if order.side == "buy" else order.bid) or order.price
    return {
        "id": uuid.uuid4().hex[:8],
        "created_at": now.isoformat(),
        "symbol": order.symbol, "side": order.side, "qty": v.max_qty, "limit": limit,
        "stop": stop, "target": target,
        "est_fee": fee(cfg, order.symbol, v.max_qty, limit),
        "notional": round(v.max_qty * limit, 2),
        "reducing": v.reducing,
        "risk": v.rules,
        "order": {**asdict(order), "quote_ts": order.quote_ts.isoformat()},
        "status": "awaiting_approval",
    }


def approve(preview, word, ledger, cfg, now, events=()):
    if preview.get("status") != "awaiting_approval":
        raise GateError(f"preview {preview['id']} is {preview.get('status')}")
    if word != cfg.approval_word:
        raise GateError(f"approval word must be exactly '{cfg.approval_word}'")
    created = parse_ts(preview["created_at"])
    age = (now - created).total_seconds()
    if age > cfg.limits.preview_ttl_sec:
        preview["status"] = "stale"
        raise GateError(f"preview is {age:.0f}s old (> {cfg.limits.preview_ttl_sec:.0f}s) — re-quote")
    if not clock.can_trade(cfg.asset(preview["symbol"]), now):
        raise GateError("session closed for this asset")

    # Re-run risk against the book as it is now (other fills may have landed since the preview).
    o = dict(preview["order"], quote_ts=parse_ts(preview["order"]["quote_ts"]), qty=preview["qty"])
    v = risk.check(risk.Order(**o), ledger, cfg, created, events)
    if not v.passed or v.max_qty < preview["qty"]:
        preview["status"] = "vetoed"
        raise GateError(f"risk re-check failed: {v.rules}")

    if cfg.mode == "LIVE":
        raise GateError("LIVE execution is not wired — no broker connector (gate 5)")
    rec = ledger.fill(preview["symbol"], preview["side"], preview["qty"], preview["limit"], now,
                      fee=preview["est_fee"], ref=preview["id"])
    preview["status"] = "filled_paper"
    preview["filled_at"] = now.isoformat()
    return rec
