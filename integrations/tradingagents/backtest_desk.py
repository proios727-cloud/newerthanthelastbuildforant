"""Small, cheap TradingAgents backtest: score ratings vs. realized alpha.

usage: python backtest_desk.py [TICKERS] [START] [END] [EVERY_N_DAYS]
default: NVDA,SPY,AAPL  2026-06-01  2026-08-31  every 7 days  (~39 cells)
Writes integrations/tradingagents/results/<run_id>.json for the dashboard.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".tradingagents.env")

from tradingagents.backtest import iter_grid, run_backtest, summarize  # noqa: E402
from tradingagents.default_config import build_default_config  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"


def main() -> None:
    args = sys.argv[1:] + [None] * 4
    tickers = (args[0] or "NVDA,SPY,AAPL").upper().split(",")
    dates = iter_grid(args[1] or "2026-06-01", args[2] or "2026-08-31", int(args[3] or 7))
    print(f"{len(tickers)} tickers x {len(dates)} dates = {len(tickers) * len(dates)} cells")

    result = run_backtest(tickers, dates, build_default_config(),
                          progress=lambda i, n, t, d: print(f"[{i}/{n}] {t} {d}"))
    summary = summarize(result)
    print(summary.render())

    OUT.mkdir(exist_ok=True)
    report = {
        "run_id": result.run_id,
        "tickers": tickers,
        "dates": dates,
        "cells_run": result.cells_run,
        "failures": result.failures,
        "summary": asdict(summary),
    }
    path = OUT / f"{result.run_id}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    print(f"saved {path}")


if __name__ == "__main__":
    main()
