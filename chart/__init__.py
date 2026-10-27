"""Original indicator engine and bar backtester. Spec: chart/SPEC.md."""
import csv
from dataclasses import dataclass

from .backtest import STRATEGIES, Result, backtest, rsi_revert, sma_cross
from .indicators import atr, bollinger, ema, macd, rma, rsi, sma, true_range


@dataclass(frozen=True)
class Bar:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def load_csv(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    keys = {k.lower().strip(): k for k in rows[0]}
    tk = next((keys[k] for k in ("date", "time", "timestamp") if k in keys), None)
    missing = [c for c in ("open", "high", "low", "close") if c not in keys]
    if tk is None or missing:
        raise ValueError(f"CSV needs a date/time column and open/high/low/close; missing {missing or ['date']}")
    bars = []
    for r in rows:
        vol = r.get(keys["volume"]) if "volume" in keys else None
        bars.append(Bar(r[tk], float(r[keys["open"]]), float(r[keys["high"]]),
                        float(r[keys["low"]]), float(r[keys["close"]]), float(vol or 0)))
    for a, b in zip(bars, bars[1:]):
        if not a.ts < b.ts:
            raise ValueError(f"rows must be strictly ascending: {a.ts} then {b.ts}")
    return bars
