"""Strategy tournament on real data, $500 snowball replay, and today's triggers.

    python -m research.tournament            # prints leaderboard + winner, writes data/live/tournament.json

Every candidate is walk-forward tested (params chosen in-sample, scored out-of-sample only).
A candidate is PROMOTED only if, out of sample: expectancy > 0 after costs, ≥ MIN_TRADES trades,
and max drawdown (at the harness's fixed 25% allocation) ≤ the snowball kill limit.
Each candidate's out-of-sample trades are replayed through a $500 Snowball so losers show too.
"""
import json
import sys

import research
from fund.snowball import Snowball
from research.strategies import meanrev, options_premium, rotation, trend

CANDIDATES = (meanrev, trend, rotation, options_premium)
MIN_TRADES = 30
KILL_DD = 0.15
START = 500.0


def qualifies(oos):
    reasons = []
    if oos["expectancy"] <= 0:
        reasons.append("expectancy ≤ 0")
    if oos["trades"] < MIN_TRADES:
        reasons.append(f"only {oos['trades']} trades (< {MIN_TRADES})")
    if oos["max_dd"] > KILL_DD:
        reasons.append(f"drawdown {oos['max_dd']:.0%} > {KILL_DD:.0%}")
    return not reasons, reasons


def triggers(bars, name, params):
    """Signals on the latest completed bar (act at the next open). Only for rule-based equity strategies."""
    out = []
    if name == meanrev.NAME:
        for s in meanrev.SYMBOLS:
            c = [r[4] for r in bars[s]]
            i = len(c) - 1
            rsi, sma = meanrev._rsi2(c, i), meanrev._sma(c, i, params["trend"])
            live = c[i] > sma and rsi < params["rsi_th"]
            out.append({"symbol": s, "close": c[i], "rsi2": round(rsi, 1), f"sma{params['trend']}": round(sma, 2),
                        "signal": "BUY next open" if live else "none"})
    elif name == trend.NAME:
        for s, rows in bars.items():
            c, h = [r[4] for r in rows], [r[2] for r in rows]
            i = len(c) - 1
            hi = max(h[i - params["entry"]:i])
            sma = sum(c[i - params["sma"] + 1:i + 1]) / params["sma"]
            live = c[i] > hi and c[i] > sma
            out.append({"symbol": s, "close": c[i], "breakout_level": round(hi, 2),
                        "signal": "BUY next open" if live else "none"})
    return out


def run():
    bars, meta = research.load_bars()
    board = []
    for mod in CANDIDATES:
        r = research.walk_forward(mod, bars)
        ok, why = qualifies(r["out_of_sample"])
        sb = Snowball(start=START, max_dd=KILL_DD)
        summary = sb.run((f"{t.symbol} {t.entry_date}", t.net) for t in r["oos_trades"])
        board.append({"name": r["name"], "params": r["params"], "split_date": r["split_date"],
                      "in_sample": r["in_sample"], "out_of_sample": r["out_of_sample"],
                      "promoted": ok, "rejected_because": why, "snowball": summary,
                      "curve": sb.curve, "modeled": mod is options_premium})
    board.sort(key=lambda b: (b["promoted"], b["out_of_sample"]["score"]), reverse=True)
    winner = next((b for b in board if b["promoted"]), None)
    result = {
        "data": {"source": meta["source"], "fetched_at": meta["fetched_at"],
                 "first": next(iter(bars.values()))[0][0], "last": next(iter(bars.values()))[-1][0]},
        "rules": {"min_trades": MIN_TRADES, "kill_dd": KILL_DD, "start": START},
        "leaderboard": board,
        "winner": winner["name"] if winner else None,
        "triggers": triggers(bars, winner["name"], winner["params"]) if winner else [],
    }
    (research.LIVE / "tournament.json").write_text(json.dumps(result, indent=1))
    return result


def main():
    r = run()
    print(f"data {r['data']['first']} → {r['data']['last']}  ({r['data']['source']})")
    print(f"{'strategy':<32}{'OOS trades':>11}{'exp/trade':>11}{'win':>7}{'maxDD':>8}  $500 →      verdict")
    for b in r["leaderboard"]:
        o, s = b["out_of_sample"], b["snowball"]
        v = "PROMOTED" if b["promoted"] else "rejected: " + "; ".join(b["rejected_because"])
        print(f"{b['name']:<32}{o['trades']:>11}{o['expectancy']:>11.4f}{o['win_rate']:>7.0%}{o['max_dd']:>8.1%}"
              f"  ${s['equity']:>8.2f}  {v}")
    print("winner:", r["winner"] or "none qualified")
    for t in r["triggers"]:
        print("  trigger:", t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
