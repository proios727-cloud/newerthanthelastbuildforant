"""Step 7: hard risk layer. Nothing reaches the broker without passing every check here."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Verdict:
    ok: bool
    reasons: list[str]
    qty: float = 0.0
    notional: float = 0.0


def check(cfg, *, regime_p: float, take_p: float, signal, equity: float, open_positions: int,
          trades_today: int, day_pnl: float, day_start_equity: float, cooldown_left: int) -> Verdict:
    reasons = []
    if regime_p < cfg.regime_threshold:
        reasons.append(f"regime p {regime_p:.3f} < {cfg.regime_threshold}")
    if take_p < cfg.take_threshold:
        reasons.append(f"TAKE p {take_p:.3f} < {cfg.take_threshold}")
    if open_positions >= cfg.max_open_positions:
        reasons.append("max open positions")
    if trades_today >= cfg.max_trades_per_day:
        reasons.append("max trades per day")
    if day_pnl <= -day_start_equity * cfg.max_daily_loss_pct / 100:
        reasons.append(f"daily loss limit hit ({day_pnl:.2f})")
    if cooldown_left > 0:
        reasons.append(f"loss cooldown ({cooldown_left} candles)")
    stop_dist = abs(signal.entry - signal.stop)
    if stop_dist <= 0:
        reasons.append("invalid stop")
    if signal.rr < 1.0:
        reasons.append(f"reward:risk {signal.rr:.2f} < 1")
    if reasons:
        return Verdict(False, reasons)

    qty_risk = equity * cfg.risk_per_trade_pct / 100 / stop_dist
    qty_cap = equity * cfg.max_position_pct / 100 / signal.entry
    qty = round(min(qty_risk, qty_cap), 5)
    if qty <= 0:
        return Verdict(False, ["size rounds to zero"])
    capped = ["size capped by max_position_pct"] if qty_cap < qty_risk else []
    return Verdict(True, capped, qty, round(qty * signal.entry, 2))
