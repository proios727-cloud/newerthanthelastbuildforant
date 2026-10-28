"""python3 -m chart backtest prices.csv --strategy sma_cross --fast 10 --slow 30 --fee-bps 1
python3 -m chart walkforward chart/data/SPY.csv --strategy rsi_revert --train 0.7
python3 -m chart walkforward chart/data/SPY.csv --strategy bollinger_revert --rolling
python3 -m chart scan --out ledger/signals.json
python3 -m chart forward record      # once a day, after the close and before the next open
python3 -m chart forward report
python3 -m chart validate chart/data/SPY.csv
"""
import argparse
import json
import pathlib

from . import STRATEGIES, backtest, load_csv
from .scan import scan
from .sweep import GRIDS, rolling_walk_forward, walk_forward


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
    w.add_argument("--strategy", choices=sorted(GRIDS), default="sma_cross")
    w.add_argument("--train", type=float, default=0.7, help="single split: fraction of bars to train on")
    w.add_argument("--rolling", action="store_true", help="re-pick params before every test block instead")
    w.add_argument("--min-train", type=int, default=252)
    w.add_argument("--test", type=int, default=21)
    w.add_argument("--fee-bps", type=float, default=0.0)
    w.add_argument("--slippage-bps", type=float, default=0.0)
    s = sub.add_parser("scan", help="walk-forward every universe CSV in a folder and print the desk signal_list")
    s.add_argument("folder", nargs="?", default="chart/data")
    s.add_argument("--min-train", type=int, default=252, help="bars before the first test block (default: 1 year)")
    s.add_argument("--test", type=int, default=21, help="bars per test block (default: 1 month)")
    s.add_argument("--fee-bps", type=float, default=1.0)
    s.add_argument("--slippage-bps", type=float, default=2.0)
    s.add_argument("--out", help="also write the JSON here")
    s.add_argument("--all", action="store_true",
                   help="research mode: scan every CSV in the folder, not only symbols in desk.json's universe")
    f = sub.add_parser("forward", help="log today's scan before the open, or score logged signals")
    f.add_argument("action", choices=("record", "report", "rotation-record", "rotation-report", "rotation-replay"))
    f.add_argument("folder", nargs="?", default="chart/data")
    f.add_argument("--log", help="signal log path (default ledger/signals.jsonl)")
    u = sub.add_parser("update", help="append the latest Alpha Vantage daily bars (needs ALPHAVANTAGE_API_KEY)")
    u.add_argument("folder", nargs="?", default="chart/data")
    u.add_argument("--all", action="store_true", help="update every CSV in the folder, not only desk.json equities")
    r = sub.add_parser("report", help="write the visual scorecard (.html) or its data (.json)")
    r.add_argument("folders", nargs="+", help="NAME=FOLDER pairs, e.g. Stocks=chart/data")
    r.add_argument("--out", required=True)
    r.add_argument("--rotation", help="ETF folder for the rotation-rule panel (stress spread + live-calendar replay)")
    st = sub.add_parser("stress", help="stress-test a basket rotation rule across rebalance days, costs and universes")
    st.add_argument("folder", nargs="?", default="chart/data/etf")
    st.add_argument("--lookback", type=int, default=60)
    st.add_argument("--hold", type=int, default=21)
    st.add_argument("--top", type=int, default=3)
    v = sub.add_parser("validate", help="sanity-check OHLC CSVs, optionally against an overlapping reference")
    v.add_argument("csv", nargs="+")
    v.add_argument("--ref", help="reference CSV whose overlapping closes must match")
    a = p.parse_args(argv)
    if a.cmd == "forward":
        from fund import config
        from . import forward
        uni = config.load().universe
        if a.action.startswith("rotation-"):
            bars = {p.stem.upper(): load_csv(p) for p in sorted(pathlib.Path(a.folder).glob("*.csv"))}
            log = a.log or forward.ROTATION_LOG
            if a.action == "rotation-replay":
                print(json.dumps(forward.replay_rotation(bars), indent=2))
            elif a.action == "rotation-record":
                sig = forward.record_rotation(bars, log)
                print(json.dumps(sig, indent=2) if sig else "not a decision day, or already recorded")
            else:
                print(json.dumps(forward.report_rotation(bars, log), indent=2))
            return
        log = a.log or forward.LOG
        if a.action == "record":
            row = forward.record(scan(pathlib.Path(a.folder).glob("*.csv"), uni, min_train=252, test=21,
                                     fee_bps=1, slippage_bps=2), log)
            print(json.dumps(row, indent=2) if row else "already recorded for this as-of date")
        else:
            print(json.dumps(forward.report(log, folder=a.folder, universe=uni), indent=2))
        return
    if a.cmd == "update":
        from fund import config
        from .update import update
        uni = ({f.stem.upper(): {"asset": "equity"} for f in pathlib.Path(a.folder).glob("*.csv")} if a.all
               else config.load().universe)
        print(json.dumps(update(a.folder, uni), indent=2))
        return
    if a.cmd == "report":
        from .report import build, render_html
        groups = dict(x.split("=", 1) for x in a.folders)
        data = build(groups, rotation_folder=a.rotation)
        text = render_html(data) if a.out.endswith(".html") else json.dumps(data, separators=(",", ":"))
        pathlib.Path(a.out).write_text(text, encoding="utf-8")
        print(f"wrote {a.out}")
        return
    if a.cmd == "stress":
        from .robust import stress
        bars = {f.stem.upper(): load_csv(f) for f in sorted(pathlib.Path(a.folder).glob("*.csv"))}
        print(json.dumps(_round(stress(bars, {"lookback": a.lookback, "hold": a.hold, "top": a.top})), indent=2))
        return
    if a.cmd == "validate":
        from .validate import check
        res = [check(c, a.ref) for c in a.csv]
        print(json.dumps(res, indent=2))
        raise SystemExit(0 if all(r["ok"] for r in res) else 1)
    if a.cmd == "walkforward":
        costs = {"fee_bps": a.fee_bps, "slippage_bps": a.slippage_bps}
        if a.rolling:
            wf = rolling_walk_forward(load_csv(a.csv), a.strategy, min_train=a.min_train, test=a.test, **costs)
        else:
            wf = walk_forward(load_csv(a.csv), a.strategy, train_frac=a.train, **costs)
            wf.pop("signals")
        print(json.dumps(_round(wf), indent=2))
        return
    if a.cmd == "scan":
        from fund import config
        files = sorted(pathlib.Path(a.folder).glob("*.csv"))
        uni = {f.stem.upper(): {"asset": "equity"} for f in files} if a.all else config.load().universe
        res = scan(files, uni, min_train=a.min_train, test=a.test,
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
