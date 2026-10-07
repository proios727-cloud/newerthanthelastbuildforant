"""$500 snowball: compound a strategy's trade returns with rollover, profit banking and a kill switch.

A strategy produces a list of trades, each a fractional return on the capital risked
(e.g. +0.021 = +2.1% after costs). The snowball decides how much of the live bankroll
to put on each one and books the result. Nothing here places orders.

Rules
- Size: quarter-Kelly from the trades seen so far (never future ones), clamped to
  [min_frac, max_frac] of the *risked* bankroll. Until `warmup` trades exist, use min_frac.
- Rollover: realized P&L stays in the risked bankroll, so wins grow the next position.
- Banking: whenever total equity makes a new high, `bank_frac` of the new gain above the
  previous high moves to a banked bucket that is never risked again.
- Kill switch: stop taking trades when drawdown from peak equity ≥ max_dd, or when the
  rolling mean of the last `window` trade returns is ≤ 0. The halt is sticky.
"""
from dataclasses import dataclass, field


@dataclass
class Snowball:
    start: float = 500.0
    bank_frac: float = 0.20
    max_dd: float = 0.15
    window: int = 20
    warmup: int = 10
    min_frac: float = 0.10
    max_frac: float = 0.50
    kelly_scale: float = 0.25
    risked: float = field(init=False)
    banked: float = field(init=False, default=0.0)
    peak: float = field(init=False)
    halted: str = field(init=False, default="")
    history: list = field(init=False, default_factory=list)   # trade returns seen
    curve: list = field(init=False, default_factory=list)     # [(label, equity, banked)]

    def __post_init__(self):
        self.risked = float(self.start)
        self.peak = float(self.start)

    @property
    def equity(self):
        return self.risked + self.banked

    def fraction(self):
        h = self.history
        if len(h) < self.warmup:
            return self.min_frac
        wins = [r for r in h if r > 0]
        losses = [-r for r in h if r < 0]
        if not wins or not losses:
            return self.min_frac if not wins else self.max_frac
        p = len(wins) / len(h)
        b = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        kelly = p - (1 - p) / b
        return max(self.min_frac, min(self.max_frac, kelly * self.kelly_scale))

    def _check_kill(self):
        if self.equity <= self.peak * (1 - self.max_dd):
            self.halted = f"drawdown ≥ {self.max_dd:.0%}"
        elif len(self.history) >= self.window and sum(self.history[-self.window:]) <= 0:
            self.halted = f"last {self.window} trades expectancy ≤ 0"

    def take(self, ret, label=""):
        """Book one trade return. Returns the dollar P&L (0 when halted)."""
        if self.halted:
            return 0.0
        stake = self.risked * self.fraction()
        pnl = stake * ret
        self.risked += pnl
        self.history.append(ret)
        if self.equity > self.peak:
            gain = self.equity - self.peak
            move = gain * self.bank_frac
            self.risked -= move
            self.banked += move
            self.peak = self.equity
        self.curve.append((label, round(self.equity, 2), round(self.banked, 2)))
        self._check_kill()
        return pnl

    def run(self, trades):
        """trades: iterable of (label, return)."""
        for label, r in trades:
            self.take(r, label)
            if self.halted:
                break
        return self.summary()

    def summary(self):
        mdd, pk = 0.0, self.start
        for _, e, _ in self.curve:
            pk = max(pk, e)
            mdd = max(mdd, (pk - e) / pk)
        n = len(self.history)
        return {
            "start": self.start, "equity": round(self.equity, 2), "banked": round(self.banked, 2),
            "risked": round(self.risked, 2), "return_pct": round((self.equity / self.start - 1) * 100, 2),
            "trades": n, "win_rate": round(sum(r > 0 for r in self.history) / n, 3) if n else 0.0,
            "max_drawdown_pct": round(mdd * 100, 2), "halted": self.halted or None,
        }
