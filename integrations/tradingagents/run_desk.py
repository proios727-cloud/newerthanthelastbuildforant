"""Run TradingAgents for one ticker and log the rating to shadow.jsonl (PAPER, no orders)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.home() / ".tradingagents.env")

from tradingagents.default_config import build_default_config  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(ticker: str, date: str) -> None:
    graph = TradingAgentsGraph(debug=False, config=build_default_config())
    _, decision = graph.propagate(ticker, date)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "tradingagents",
        "mode": "PAPER",
        "ticker": ticker,
        "as_of": date,
        "decision": decision if isinstance(decision, (str, dict)) else str(decision),
        "status": "awaiting_risk_and_EXECUTE",
    }
    with open(ROOT / "shadow.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: run_desk.py TICKER YYYY-MM-DD")
    main(sys.argv[1].upper(), sys.argv[2])
