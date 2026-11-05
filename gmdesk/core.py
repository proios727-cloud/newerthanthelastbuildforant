"""Shared math: streaming VPIN, state machine, limits, spread decomposition, maker fee.

Prices are YES probabilities in [0,1]; sizes are contracts; s = +1 taker bought YES.
"""
import math
from collections import deque


class VPIN:
    """Equal-volume buckets of signed taker flow; VPIN = mean |B-S|/V over the last n full buckets."""

    def __init__(self, bucket, n=50):
        self.bucket, self.n = float(bucket), n
        self.b = self.s = 0.0
        self.hist = deque(maxlen=n)

    def push(self, q, side):
        rem = float(q)
        while rem > 1e-12:
            take = min(rem, self.bucket - (self.b + self.s))
            if side > 0:
                self.b += take
            else:
                self.s += take
            rem -= take
            if self.b + self.s >= self.bucket - 1e-9:
                self.hist.append(abs(self.b - self.s) / self.bucket)
                self.b = self.s = 0.0

    @property
    def value(self):
        return sum(self.hist) / len(self.hist) if len(self.hist) == self.n else None


class Monitor:
    def __init__(self, warn=0.70, halt=0.90):
        self.warn, self.halt, self.status = warn, halt, "ACTIVE"

    def update(self, vpin):
        v = vpin or 0.0
        self.status = "HALTED" if v >= self.halt else "WARNING" if v >= self.warn else "ACTIVE"
        return self.status

    def pressure(self, vpin):
        return min(1.0, max(0.0, ((vpin or 0.0) - self.warn) / max(self.halt - self.warn, 1e-9)))

    def multiplier(self, vpin):
        if self.status == "HALTED":
            return None
        return 1.0 + 2.0 * self.pressure(vpin) if self.status == "WARNING" else 1.0


def position_limit(base, pressure):
    return max(1, int(base * (1.0 - 0.75 * pressure)))


def maker_fee(p, q, rate=0.0175):
    """Kalshi maker fee where charged: ceil(rate*C*P*(1-P)) dollars per order. Rounded per order."""
    return math.ceil(rate * q * p * (1 - p) * 100 - 1e-9) / 100


def decompose(prices, flows):
    """Roll effective spread + Kyle-lambda adverse-selection share over one trade sequence (cents)."""
    n = len(prices)
    if n < 20:
        return None
    dp = [(prices[i] - prices[i - 1]) * 100 for i in range(1, n)]
    q = flows[1:]
    m = lambda xs: sum(xs) / len(xs)
    a, b = dp[1:], dp[:-1]
    ma, mb = m(a), m(b)
    cov1 = m([(x - ma) * (y - mb) for x, y in zip(a, b)])
    eff = 2 * math.sqrt(max(-cov1, 0.0))
    mq, md = m(q), m(dp)
    vq = m([(x - mq) ** 2 for x in q])
    if vq <= 0 or eff <= 0:
        return None
    lam = m([(x - mq) * (y - md) for x, y in zip(q, dp)]) / vq
    adv = min(2 * abs(lam) * math.sqrt(vq), eff)
    return {"effective_c": eff, "adverse_c": adv, "inventory_c": eff - adv, "as_fraction": adv / eff,
            "kyle_lambda_c": lam}
