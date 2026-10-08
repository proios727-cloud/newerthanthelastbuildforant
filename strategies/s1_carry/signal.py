"""S1 carry signal: funding-rate harvest on BTC/ETH perps.

Emits {symbol, side, qty_hint, conviction, reason} dicts - never trades.
qty_hint is a fraction of NAV (e.g. 0.05 = 5% position cap target); the
preview pipeline re-sizes through fund/risk.py which owns all caps.
"""
import pathlib

from data import collectors

SPEC = pathlib.Path(__file__).parent / "spec.yaml"
MIN_FUNDING_8H = 0.00005
SIDE = "sell"
UNIVERSE = ("BTC/USD", "ETH/USD")


def conviction_for(rate_8h):
    """Annualized funding / 10% target, capped at 1.0."""
    annualized = rate_8h * 3 * 365
    return min(annualized / 0.10, 1.0)


def signals(cfg):
    """Scan funding for the strategy universe; return signal dicts."""
    out = []
    for sym in UNIVERSE:
        if sym not in cfg.universe:
            continue
        f = collectors.funding_rate(sym)
        if not f:
            continue
        rate = f["rate_8h"]
        if rate < MIN_FUNDING_8H:
            continue
        conv = conviction_for(rate)
        out.append({
            "symbol": sym,
            "side": SIDE,
            "qty_hint": 0.05,  # fraction of NAV; risk.py re-sizes
            "conviction": round(conv, 3),
            "reason": f"funding {rate*100:.4f}%/8h (annualized {rate*3*365*100:.1f}%)",
            "strategy": "s1_carry",
        })
    return out