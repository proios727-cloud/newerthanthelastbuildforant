"""python3 -m chart backtest prices.csv --strategy sma_cross --fast 10 --slow 30 --fee-bps 1
python3 -m chart walkforward chart/data/SPY.csv --strategy rsi_revert --train 0.7
python3 -m chart scan --out ledger/signals.json
"""
import argparse
import json
import pathlib

from . import STRATEGIES, backtest, load_csv
from .scan import scan
from .sweep import walk_forward


def _round(x):
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


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
    w = sub.add_parser("walkforward", help="choose params on the train slice, score them on the test slice")
    w.add_argument("csv")
    w.add_argument("--strategy", choices=sorted(STRATEGIES), default="sma_cross")
    w.add_argument("--train", type=float, default=0.7)
    w.add_argument("--fee-bps", type=float, default=0.0)
    w.add_argument("--slippage-bps", type=float, default=0.0)
    s = sub.add_parser("scan", help="walk-forward every universe CSV in a folder and print the desk signal_list")
    s.add_argument("folder", nargs="?", default="chart/data")
    s.add_argument("--train", type=float, default=0.7)
    s.add_argument("--fee-bps", type=float, default=1.0)
    s.add_argument("--slippage-bps", type=float, default=2.0)
    s.add_argument("--out", help="also write the JSON here")
    a = p.parse_args(argv)
    if a.cmd == "walkforward":
        wf = walk_forward(load_csv(a.csv), a.strategy, train_frac=a.train,
                          fee_bps=a.fee_bps, slippage_bps=a.slippage_bps)
        wf.pop("signals")
        print(json.dumps(_round(wf), indent=2))
        return
    if a.cmd == "scan":
        from fund import config
        res = scan(pathlib.Path(a.folder).glob("*.csv"), config.load().universe, train_frac=a.train,
                   fee_bps=a.fee_bps, slippage_bps=a.slippage_bps)
        text = json.dumps(res, indent=2)
        if a.out:
            pathlib.Path(a.out).write_text(text + "\n")
        print(text)
        return

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
