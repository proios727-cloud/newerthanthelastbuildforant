"""Replay the SPY/QQQ day-trade rules (research/intraday-orb/RULE.md) over the last N sessions on a small account.

    python3 scripts/replay_daytrade.py --bars DIR [--sessions 10] [--start 2000] [--out DIR]

Out-of-sample only: each month's variant is the one chosen by the research's walk-forward from earlier sessions
(chart.intraday.walk_forward), so nothing is fitted to the replay window. Four equal sleeves (SPY and QQQ ×
opening-range breakout and gap fade) each start with a quarter of the account and trade 100% of their sleeve in
fractional shares, with no leverage, at the rule's base cost (1 bp fee + 1 bp slippage per side), flat at the close.

A second curve keeps only long trades. Shorting needs a margin account, and a margin account under $25k is limited to
3 day trades per 5 business days (pattern day trader rule). A cash account can only take the long trades, and only
with settled cash.

Writes OUT/replay_trades.csv (every trade) and OUT/replay_daily.csv (one row per session: P&L, equity, and the
long-only P&L and equity). The research verdict on these rules is REJECT (research/intraday-orb/VERDICT.md). This is a
replay of history, not a forecast.
"""
import argparse
import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chart import load_csv  # noqa: E402
from chart.intraday import BASE_COST, sessions, walk_forward  # noqa: E402

SYMBOLS, STRATEGIES = ("SPY", "QQQ"), ("orb", "gap_fade")


def replay(bars_dir, n_sessions=10, start=2000.0):
    trades, days = [], None
    for sym in SYMBOLS:
        sess = sessions(load_csv(pathlib.Path(bars_dir) / f"{sym}.csv"))
        window = [d for d, _ in sess][-n_sessions:]
        days = days or window
        wf = walk_forward(sess)
        for strat in STRATEGIES:
            oos, picks, _ = wf[strat]
            variant = {m: lbl for m, lbl, _ in picks}
            for t in oos:
                if t["date"] in window:
                    net = t["gross"] - 2 * BASE_COST / 1e4
                    trades.append({**t, "symbol": sym, "strategy": strat, "variant": variant.get(t["date"][:7], ""),
                                   "net": net})
    sleeve = {(s, k): start / 4 for s in SYMBOLS for k in STRATEGIES}
    sleeve_long = dict(sleeve)
    rows, out_trades = [], []
    for d in days:
        pnl = pnl_long = 0.0
        today = sorted((t for t in trades if t["date"] == d), key=lambda t: (t["symbol"], t["strategy"]))
        for t in today:
            key = (t["symbol"], t["strategy"])
            notional = sleeve[key]
            dollars = notional * t["net"]
            sleeve[key] += dollars
            pnl += dollars
            long_dollars = 0.0
            if t["side"] > 0:
                long_dollars = sleeve_long[key] * t["net"]
                sleeve_long[key] += long_dollars
                pnl_long += long_dollars
            out_trades.append({"date": d, "symbol": t["symbol"], "strategy": t["strategy"], "variant": t["variant"],
                               "side": "long" if t["side"] > 0 else "short", "entry": round(t["entry"], 2),
                               "exit": round(t["exit"], 2), "reason": t["reason"],
                               "shares": round(notional / t["entry"], 4), "notional": round(notional, 2),
                               "return_pct": round(100 * t["net"], 3), "pnl": round(dollars, 2),
                               "cost": round(notional * 2 * BASE_COST / 1e4, 2),
                               "cash_account_ok": "yes" if t["side"] > 0 else "no (short)"})
        rows.append({"date": d, "trades": len(today), "pnl": round(pnl, 2), "equity": round(sum(sleeve.values()), 2),
                     "pnl_long_only": round(pnl_long, 2), "equity_long_only": round(sum(sleeve_long.values()), 2)})
    return out_trades, rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default=str(ROOT / "chart/data/intraday/15m"))
    ap.add_argument("--sessions", type=int, default=10)
    ap.add_argument("--start", type=float, default=2000.0)
    ap.add_argument("--out", default=".")
    a = ap.parse_args(argv)
    trades, days = replay(a.bars, a.sessions, a.start)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("replay_trades.csv", trades), ("replay_daily.csv", days)):
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["date"])
            w.writeheader()
            w.writerows(rows)
    end, end_long = days[-1]["equity"], days[-1]["equity_long_only"]
    print(f"{days[0]['date']} -> {days[-1]['date']}: {len(trades)} trades; ${a.start:,.0f} -> ${end:,.2f} "
          f"({end / a.start - 1:+.2%}); long only ${end_long:,.2f} ({end_long / a.start - 1:+.2%})")


if __name__ == "__main__":
    main()
