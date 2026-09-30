"""Strategy research harness shared by every candidate in the tournament.

Contract for a strategy module in research/strategies/:
    NAME: str
    PARAM_GRID: list[dict]                     # small grid searched on the in-sample part only
    def trades(bars, params, start, end) -> list[Trade]
        bars: {symbol: [[date, open, high, low, close, volume], ...]} (full history, oldest first)
        start/end: row indices bounding where ENTRIES may happen. Signals may look back before
        `start` (warm-up) but must never read a bar after the one they act on — entries use the
        next bar's open, exits use a later bar's open/close. Costs are applied by `net()`.

Walk-forward: parameters are chosen on rows [0, split) and scored on rows [split, n) only.
"""
import json
import pathlib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = ROOT / "data" / "live"

# Round-trip cost per trade as a fraction of notional: commission-free broker, half-spread each side
# plus slippage. SPY/QQQ/IWM ~1bp spread; single names wider. Conservative on purpose.
COST = {"SPY": 0.0004, "QQQ": 0.0004, "IWM": 0.0006}
DEFAULT_COST = 0.0010


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    gross: float        # fractional return before costs (short = negative price move)

    @property
    def net(self):
        return self.gross - COST.get(self.symbol, DEFAULT_COST)


def load_bars(path=LIVE / "equity_daily.json"):
    d = json.loads(pathlib.Path(path).read_text())
    return d["bars"], d


def common_length(bars):
    return min(len(v) for v in bars.values())


def stats(trades):
    r = [t.net for t in trades]
    n = len(r)
    if not n:
        return {"trades": 0, "expectancy": 0.0, "win_rate": 0.0, "total": 0.0, "max_dd": 0.0, "score": 0.0}
    eq, pk, mdd = 1.0, 1.0, 0.0
    for x in r:
        eq *= 1 + x * 0.25          # score at a fixed 25% allocation so strategies compare fairly
        pk = max(pk, eq)
        mdd = max(mdd, 1 - eq / pk)
    total = eq - 1
    return {"trades": n, "expectancy": round(sum(r) / n, 5), "win_rate": round(sum(x > 0 for x in r) / n, 3),
            "total": round(total, 4), "max_dd": round(mdd, 4), "score": round(total / max(mdd, 0.01), 3)}


def walk_forward(module, bars, split_frac=0.70):
    n = common_length(bars)
    split = int(n * split_frac)
    best, best_s = None, None
    for p in module.PARAM_GRID:
        s = stats(module.trades(bars, p, 0, split))
        if s["trades"] >= 10 and (best_s is None or s["score"] > best_s["score"]):
            best, best_s = p, s
    if best is None:
        best = module.PARAM_GRID[0]
        best_s = stats(module.trades(bars, best, 0, split))
    oos = module.trades(bars, best, split, n)
    return {"name": module.NAME, "params": best, "in_sample": best_s, "out_of_sample": stats(oos),
            "oos_trades": oos, "split_date": next(iter(bars.values()))[split][0]}
