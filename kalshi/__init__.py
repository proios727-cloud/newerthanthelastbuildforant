"""Kalshi 15-minute BTC/ETH up/down maker desk (KXBTC15M / KXETH15M).

Prices are integer cents (1–99). A YES bid plus a NO bid that sum to under 100¢ locks
(100 − yes − no)¢ per contract if both sides fill. The risk is a one-sided fill; `exposure`
and `should_cut` keep that explicit.

Modes: SHADOW (log only) → DEMO (Kalshi demo API) → LIVE. LIVE is refused here: there is no
signed live client in this repo, and going live needs the human approval word like the fund.
"""
import math
from dataclasses import dataclass

MODES = ("SHADOW", "DEMO", "LIVE")


class ModeError(Exception):
    pass


def require_mode(mode):
    if mode not in MODES:
        raise ModeError(f"mode must be one of {MODES}")
    if mode == "LIVE":
        raise ModeError("LIVE is not wired — no signed live client (gate)")
    return mode


def taker_fee_cents(price_c, qty, rate=0.07):
    """Kalshi's general taker fee: ceil(rate · C · P · (1−P)) dollars, returned in cents."""
    p = price_c / 100
    return math.ceil(round(rate * qty * p * (1 - p) * 100, 6))


@dataclass(frozen=True)
class Quote:
    yes_bid: int
    no_bid: int

    @property
    def lock_c(self):
        return 100 - self.yes_bid - self.no_bid


def quote(p_yes, edge_c=2, skew_c=0):
    """Bids around a fair YES probability. `skew_c` > 0 leans toward YES (raises the YES bid).

    Returns None when no valid pair locks at least `edge_c`.
    """
    if not 0 < p_yes < 1 or edge_c < 1:
        return None
    fair_yes = p_yes * 100
    yes = math.floor(fair_yes - edge_c / 2 + skew_c)
    no = math.floor(100 - fair_yes - edge_c / 2 - skew_c)
    yes, no = max(1, min(98, yes)), max(1, min(98, no))
    q = Quote(yes, no)
    return q if q.lock_c >= edge_c else None


def exposure(yes_filled, no_filled, q):
    """Worst-case loss in cents per the current fills (positive = money at risk)."""
    paired = min(yes_filled, no_filled)
    open_yes, open_no = yes_filled - paired, no_filled - paired
    return open_yes * q.yes_bid + open_no * q.no_bid - paired * q.lock_c


def should_cut(yes_filled, no_filled, q, p_yes_now, secs_left, max_adverse_c=6, final_secs=60):
    """Cut a one-sided fill when fair value has moved against it or the window is ending."""
    if yes_filled == no_filled:
        return False
    long_yes = yes_filled > no_filled
    fair_now = p_yes_now * 100 if long_yes else (1 - p_yes_now) * 100
    paid = q.yes_bid if long_yes else q.no_bid
    return paid - fair_now >= max_adverse_c or secs_left <= final_secs
