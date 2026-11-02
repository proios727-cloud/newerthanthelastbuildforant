"""Step 4: playbooks. Breakouts in TRENDING, mean reversion in CHOPPY, nothing in PANIC."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from features import arrays, atr, ema, rsi


@dataclass
class Signal:
    playbook: str
    side: str  # LONG | SHORT
    entry: float
    stop: float
    target: float
    reason: str

    @property
    def rr(self) -> float:
        return abs(self.target - self.entry) / abs(self.entry - self.stop)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["rr"] = round(self.rr, 2)
        return d


def breakout(candles, cfg) -> Signal | None:
    _, h, l, c, _ = arrays(candles)
    a = atr(h, l, c, cfg.atr_period)[-1]
    e20, e50 = ema(c, 20)[-1], ema(c, 50)[-1]
    n = cfg.breakout_lookback
    hi, lo = h[-n - 1:-1].max(), l[-n - 1:-1].min()
    px = c[-1]
    if px > hi and e20 > e50:
        return Signal("breakout", "LONG", px, px - cfg.stop_atr * a, px + cfg.breakout_target_atr * a,
                      f"close {px:.2f} > {n}-bar high {hi:.2f}, EMA20>EMA50")
    if cfg.allow_shorts and px < lo and e20 < e50:
        return Signal("breakout", "SHORT", px, px + cfg.stop_atr * a, px - cfg.breakout_target_atr * a,
                      f"close {px:.2f} < {n}-bar low {lo:.2f}, EMA20<EMA50")
    return None


def mean_reversion(candles, cfg) -> Signal | None:
    _, h, l, c, _ = arrays(candles)
    a = atr(h, l, c, cfg.atr_period)[-1]
    w = c[-20:]
    mid, sd = w.mean(), w.std()
    r = rsi(c)[-1]
    px = c[-1]
    if px < mid - 2 * sd and r < 35 and mid > px + 0.5 * a:
        return Signal("mean_reversion", "LONG", px, px - cfg.stop_atr * a, float(mid),
                      f"close {px:.2f} below lower band {mid - 2 * sd:.2f}, RSI {r:.1f}")
    if cfg.allow_shorts and px > mid + 2 * sd and r > 65 and mid < px - 0.5 * a:
        return Signal("mean_reversion", "SHORT", px, px + cfg.stop_atr * a, float(mid),
                      f"close {px:.2f} above upper band {mid + 2 * sd:.2f}, RSI {r:.1f}")
    return None


PLAYBOOK = {"TRENDING": breakout, "CHOPPY": mean_reversion, "PANIC": None}


def signal_for(regime: str, candles, cfg) -> Signal | None:
    fn = PLAYBOOK.get(regime)
    return fn(candles, cfg) if fn else None


def resolve(signal: dict, future: list[dict]) -> str:
    """Counterfactual: which of stop/target the next candles hit first (stop wins ties)."""
    long = signal["side"] == "LONG"
    for k in future:
        hit_stop = k["l"] <= signal["stop"] if long else k["h"] >= signal["stop"]
        hit_tgt = k["h"] >= signal["target"] if long else k["l"] <= signal["target"]
        if hit_stop:
            return "STOP"
        if hit_tgt:
            return "TARGET"
    return "OPEN"

