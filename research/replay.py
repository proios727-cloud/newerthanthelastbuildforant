"""Bar-by-bar replay of the tournament's out-of-sample trades through the $500 snowball.

    python -m research.replay        # writes data/live/replay.json for the Desk Tabs Replay tab

Uses exactly the walk-forward trades the tournament scored (same params, same split), so the
replay can't drift from the leaderboard. The snowball books trades in the tournament's order;
each frame shows the equity once every trade booked so far has exited on or before that bar,
so nothing is shown before it could have been known.
"""
import json
import sys

import research
from fund.snowball import Snowball
from research.strategies import meanrev, options_premium

MODES = {"meanrev": meanrev, "premium": options_premium}
WARM = 20          # bars shown before the split for context
TV_CHECK = {       # TradingView (RH_TV_HFT get-ohlcv, 1D) closes, pulled 2026-09-30, for the source cross-check
    "SPY": {"2024-10-01": 568.62, "2025-09-30": 666.18, "2026-09-28": 765.61},
    "QQQ": {"2024-10-01": 481.27, "2025-09-30": 600.37, "2026-09-28": 736.53},
    "IWM": {"2024-10-01": 217.89, "2025-09-30": 241.96, "2026-09-28": 280.02},
}


def crosscheck(bars):
    """Max absolute close difference between the saved bars and TradingView's on the check dates."""
    worst = 0.0
    for s, pts in TV_CHECK.items():
        by = {r[0]: r[4] for r in bars.get(s, [])}
        worst = max([worst] + [abs(by[d] - c) for d, c in pts.items() if d in by])
    return round(worst, 4)


def build(module, bars):
    r = research.walk_forward(module, bars)
    trades = r["oos_trades"]
    sb = Snowball(start=500.0, max_dd=0.15)
    halted_at = None
    for k, t in enumerate(trades):
        sb.take(t.net, f"{t.symbol} {t.entry_date}")
        if sb.halted and halted_at is None:
            halted_at = k
    syms = list(getattr(module, "SYMBOLS", None) or (module.SYMBOL,))
    dates = [row[0] for row in bars[syms[0]]]
    s0 = max(0, dates.index(r["split_date"]) - WARM)
    frames, k = [], -1
    for d in dates[s0:]:
        while k + 1 < len(sb.curve) and all(t.exit_date <= d for t in trades[:k + 2]):
            k += 1
        eq, banked = (sb.curve[k][1], sb.curve[k][2]) if k >= 0 else (500.0, 0.0)
        frames.append({"d": d, "eq": eq, "banked": banked, "n": k + 1,
                       "halted": halted_at is not None and k >= halted_at})
    return {
        "name": r["name"], "params": r["params"], "split_date": r["split_date"],
        "symbols": syms,
        "bars": {s: [row[:5] for row in bars[s][s0:]] for s in syms},
        "trades": [{"symbol": t.symbol, "entry": t.entry_date, "exit": t.exit_date,
                    "net": round(t.net, 5)} for t in trades],
        "frames": frames,
        "final": {"equity": round(sb.equity, 2), "banked": round(sb.banked, 2), "halted": sb.halted or None},
    }


def run():
    bars, meta = research.load_bars()
    out = {"source": meta["source"], "tv_crosscheck_max_diff": crosscheck(bars),
           "modes": {k: build(m, bars) for k, m in MODES.items()}}
    (research.LIVE / "replay.json").write_text(json.dumps(out, separators=(",", ":")))
    return out


def main():
    r = run()
    print(f"TradingView vs saved bars, max close diff: {r['tv_crosscheck_max_diff']}")
    for k, m in r["modes"].items():
        f = m["final"]
        print(f"{k:<8} {m['name']:<32} {len(m['trades'])} trades, {len(m['frames'])} bars  "
              f"$500 → ${f['equity']} (banked ${f['banked']}) halted={f['halted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
