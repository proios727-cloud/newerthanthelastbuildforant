"""Standard indicators from their published definitions. Every output is input-length; None until warm."""
import math


def sma(x, n):
    out = [None] * len(x)
    if n <= 0:
        raise ValueError("n must be positive")
    s = 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _smooth(x, n, alpha):
    """Exponential smoothing seeded with the SMA of the first n non-None values."""
    out = [None] * len(x)
    start = next((i for i, v in enumerate(x) if v is not None), None)
    if start is None or len(x) - start < n:
        return out
    seed_at = start + n - 1
    prev = sum(x[start:seed_at + 1]) / n
    out[seed_at] = prev
    for i in range(seed_at + 1, len(x)):
        prev = prev + alpha * (x[i] - prev)
        out[i] = prev
    return out


def ema(x, n):
    return _smooth(x, n, 2.0 / (n + 1))


def rma(x, n):
    """Wilder's moving average."""
    return _smooth(x, n, 1.0 / n)


def rsi(close, n=14):
    out = [None] * len(close)
    if len(close) <= n:
        return out
    gains = [None] + [max(close[i] - close[i - 1], 0.0) for i in range(1, len(close))]
    losses = [None] + [max(close[i - 1] - close[i], 0.0) for i in range(1, len(close))]
    ag, al = rma(gains, n), rma(losses, n)
    for i in range(len(close)):
        if ag[i] is None:
            continue
        out[i] = 100.0 if al[i] == 0 else 100.0 - 100.0 / (1.0 + ag[i] / al[i])
    return out


def macd(close, fast=12, slow=26, signal=9):
    f, s = ema(close, fast), ema(close, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    sig = _smooth(line, signal, 2.0 / (signal + 1))
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def bollinger(close, n=20, k=2.0):
    mid = sma(close, n)
    upper, lower = [None] * len(close), [None] * len(close)
    for i in range(n - 1, len(close)):
        w = close[i - n + 1:i + 1]
        sd = math.sqrt(sum((v - mid[i]) ** 2 for v in w) / n)
        upper[i], lower[i] = mid[i] + k * sd, mid[i] - k * sd
    return mid, upper, lower


def true_range(bars):
    out = []
    for i, b in enumerate(bars):
        if i == 0:
            out.append(b.high - b.low)
        else:
            pc = bars[i - 1].close
            out.append(max(b.high - b.low, abs(b.high - pc), abs(b.low - pc)))
    return out


def atr(bars, n=14):
    return rma(true_range(bars), n)
