"""Volume profile from OHLCV bars: volume by price, point of control, value area, high- and low-volume nodes (HVN / LVN).

Each bar's volume is spread evenly across the price bins its high-low range covers (bars carry no tick detail, so this is
an approximation; finer bars give a finer profile).
- **POC (point of control):** the bin with the most volume.
- **Value area:** the smallest band around the POC holding `value_area` (70%) of the volume.
- **HVN:** a bin that is a local peak and at least `hvn_mult` × the average bin. Price tends to slow and rotate there.
- **LVN:** a bin inside the traded range that is a local trough and at most `lvn_mult` × the average bin. Price tends to
  move through quickly; often lines up with option-chain air pockets.
"""
import math


def profile(bars, bin_size=None, value_area=0.70, hvn_mult=1.3, lvn_mult=0.5, smooth=1):
    if not bars:
        return {"bins": [], "poc": None, "vah": None, "val": None}
    lo, hi = min(b.low for b in bars), max(b.high for b in bars)
    if bin_size is None:
        bin_size = max((hi - lo) / 60, 0.01)
    n = max(1, math.ceil((hi - lo) / bin_size - 1e-9))
    top = lambda x: min(n - 1, max(0, math.ceil((x - lo) / bin_size - 1e-9) - 1))  # noqa: E731
    vol = [0.0] * n
    for b in bars:
        i0 = min(n - 1, int((b.low - lo) // bin_size))
        i1 = max(i0, top(b.high))
        share = b.volume / (i1 - i0 + 1)
        for i in range(i0, i1 + 1):
            vol[i] += share
    # Light smoothing so single-bin noise isn't read as a node.
    sm = [sum(vol[max(0, i - smooth):i + smooth + 1]) / len(vol[max(0, i - smooth):i + smooth + 1]) for i in range(n)]
    avg = sum(vol) / n
    poc = max(range(n), key=lambda i: vol[i])
    total, inside, a, b = sum(vol), vol[poc], poc, poc
    while inside < value_area * total and (a > 0 or b < n - 1):
        up = vol[b + 1] if b < n - 1 else -1
        dn = vol[a - 1] if a > 0 else -1
        if up >= dn:
            b += 1
            inside += vol[b]
        else:
            a -= 1
            inside += vol[a]
    rows = []
    for i in range(n):
        left, right = sm[i - 1] if i else -math.inf, sm[i + 1] if i < n - 1 else -math.inf
        peak = sm[i] >= left and sm[i] >= right and sm[i] >= hvn_mult * avg
        lleft, lright = sm[i - 1] if i else math.inf, sm[i + 1] if i < n - 1 else math.inf
        trough = 0 < i < n - 1 and sm[i] <= lleft and sm[i] <= lright and sm[i] <= lvn_mult * avg
        rows.append({"price": round(lo + (i + 0.5) * bin_size, 4), "volume": round(vol[i]),
                     "node": "HVN" if peak else "LVN" if trough else ""})
    mid = lambda i: round(lo + (i + 0.5) * bin_size, 4)  # noqa: E731
    return {"bins": rows, "poc": mid(poc), "vah": mid(b), "val": mid(a), "bin_size": bin_size}
