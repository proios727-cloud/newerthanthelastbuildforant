"""Strategy -> preview bridge.

Takes a strategy signal dict, pulls a fresh quote, builds an order preview through
the normal risk pipeline, and queues it for EXECUTE. Strategies never trade; this
module never bypasses fund/risk.py. Only desk-native strategies (a spec.yaml in
strategies/) may propose - the strategy id is checked against the registry.
"""
import importlib
import json
import pathlib

from data import collectors
from fund import funnel, risk
from fund import preview as preview_mod
from fund import clock
from .ledger import Ledger, parse_ts
from .config import ROOT

STRATEGIES = ROOT / "strategies"


def _known_strategies():
    return {p.parent.name for p in STRATEGIES.glob("*/spec.yaml")}


def propose(signal, ledger, cfg, previews_path, now=None, events=()):
    """signal: {symbol, side, qty_hint, conviction, reason, strategy}.

    Returns (preview, funnel_events_logged) or raises preview.GateError on VETO.
    """
    strategy = signal.get("strategy")
    known = _known_strategies()
    if strategy not in known:
        raise ValueError(f"unknown strategy '{strategy}' - not in {sorted(known)}")

    now = now or clock.now()
    funnel.log_stage("scan_hit", symbol=signal["symbol"], strategy=strategy,
                     reason=signal.get("reason", ""))

    q = collectors.get_stored_quote(signal["symbol"])
    if q is None or (now - parse_ts(q["ts"])).total_seconds() > cfg.limits.max_quote_age_sec:
        q = collectors.quote(signal["symbol"], cfg)
    # Whatever quote we use - stored or freshly fetched - must be fresh.
    if q is None or (now - parse_ts(q["ts"])).total_seconds() > cfg.limits.max_quote_age_sec:
        raise RuntimeError(f"no fresh quote for {signal['symbol']} (stale or missing)")

    nav = ledger.nav()
    px = q["price"]
    qty = signal["qty_hint"] * nav / px if signal.get("qty_hint") else 0.0
    if qty <= 0:
        raise ValueError("signal produced zero qty")

    order = risk.Order(signal["symbol"], signal["side"], qty, px, now,
                       bid=q.get("bid"), ask=q.get("ask"))
    p = preview_mod.build(order, ledger, cfg, now, events=events)
    funnel.log_stage("risk_pass", symbol=signal["symbol"], strategy=strategy)
    funnel.log_stage("preview", id=p["id"], symbol=signal["symbol"], strategy=strategy)

    ps = json.loads(previews_path.read_text()) if previews_path.exists() else {}
    ps[p["id"]] = p
    previews_path.write_text(json.dumps(ps, indent=2))
    return p