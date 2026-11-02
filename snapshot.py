"""Step 3: render chart + order book into one PNG snapshot per candle."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from features import arrays, ema  # noqa: E402


def render(candles: list[dict], book: dict, path: Path, title: str, bars: int = 96) -> Path:
    ks = candles[-bars:]
    o, h, l, c, v = arrays(ks)
    _, _, _, call, _ = arrays(candles)
    e20, e50 = ema(call, 20)[-bars:], ema(call, 50)[-bars:]
    x = np.arange(len(ks))

    fig = plt.figure(figsize=(10, 6.2), dpi=80)
    gs = fig.add_gridspec(2, 2, height_ratios=[3, 1], width_ratios=[3, 1.2], hspace=0.08, wspace=0.18)
    ax, axv, axd = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[:, 1])

    up = c >= o
    col = np.where(up, "#16a34a", "#dc2626")
    ax.vlines(x, l, h, color=col, linewidth=0.8)
    ax.bar(x, np.maximum(abs(c - o), (h.max() - l.min()) * 0.0015), bottom=np.minimum(o, c), color=col, width=0.7)
    ax.plot(x, e20, color="#2563eb", lw=1, label="EMA20")
    ax.plot(x, e50, color="#f59e0b", lw=1, label="EMA50")
    ax.set_title(title, fontsize=10, loc="left")
    ax.legend(loc="upper left", fontsize=7)
    ax.tick_params(labelbottom=False, labelsize=7)
    ax.grid(alpha=0.2)
    axv.bar(x, v, color=col, width=0.7)
    axv.tick_params(labelsize=7)
    axv.set_ylabel("vol", fontsize=7)

    mid = (book["bids"][0][0] + book["asks"][0][0]) / 2
    bids = [(p, q) for p, q in book["bids"] if p >= mid * 0.99]
    asks = [(p, q) for p, q in book["asks"] if p <= mid * 1.01]
    if bids and asks:
        bp, bq = zip(*bids)
        ap, aq = zip(*asks)
        axd.fill_betweenx(bp, 0, np.cumsum(bq), step="post", color="#16a34a", alpha=0.5, label="bids")
        axd.fill_betweenx(ap, 0, np.cumsum(aq), step="post", color="#dc2626", alpha=0.5, label="asks")
    axd.axhline(mid, color="k", lw=0.6, ls="--")
    axd.set_title("Order book depth ±1% (cum. BTC)", fontsize=9)
    axd.tick_params(labelsize=7)
    axd.legend(fontsize=7, loc="lower right")
    axd.grid(alpha=0.2)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="png")
    plt.close(fig)
    return path
