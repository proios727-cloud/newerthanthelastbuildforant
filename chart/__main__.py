"""python3 -m chart backtest prices.csv --strategy sma_cross --fast 10 --slow 30 --fee-bps 1"""
import argparse
import json

from . import STRATEGIES, backtest, load_csv


def main(argv=None):
    p = argparse.ArgumentParser(prog="chart")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest", help="run a strategy over an OHLC CSV")
    b.add_argument("csv")
    b.add_argument("--strategy", choices=sorted(STRATEGIES), default="sma_cross")
    b.add_argument("--fast", type=int, default=10)
    b.add_argument("--slow", type=int, default=30)
    b.add_argument("--rsi-n", type=int, default=14)
    b.add_argument("--lo", type=float, default=30)
    b.add_argument("--hi", type=float, default=70)
    b.add_argument("--fee-bps", type=float, default=0.0)
    b.add_argument("--slippage-bps", type=float, default=0.0)
    b.add_argument("--periods-per-year", type=int, default=252)
    a = p.parse_args(argv)

    bars = load_csv(a.csv)
    close = [x.close for x in bars]
    if a.strategy == "sma_cross":
        sig = STRATEGIES["sma_cross"](close, a.fast, a.slow)
    else:
        sig = STRATEGIES["rsi_revert"](close, a.rsi_n, a.lo, a.hi)
    r = backtest(bars, sig, a.fee_bps, a.slippage_bps, periods_per_year=a.periods_per_year)
    print(json.dumps({"bars": len(bars), "strategy": a.strategy,
                      "stats": {k: round(v, 6) for k, v in r.stats.items()},
                      "final_equity": round(r.equity[-1], 2) if r.equity else None}, indent=2))


if __name__ == "__main__":
    main()
