"""Inventory existing chain snapshots; never treat endpoints as a strategy backtest."""
import argparse
import json
from pathlib import Path


def inventory(repo_root):
    directory = Path(repo_root) / "options" / "data" / "chains"
    files = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            contracts = data.get("contracts", [])
            files.append({"file": path.name, "root": data.get("symbol"),
                          "captured_at": data.get("captured_at"),
                          "source": data.get("source"),
                          "contracts": len(contracts),
                          "calls": sum(c.get("option_type") == "call" for c in contracts)})
        except (ValueError, AttributeError, OSError) as error:
            files.append({"file": path.name, "error_type": type(error).__name__})
    return {"snapshot_inventory": files, "strategy_backtest_ready": False,
            "reason": "Chain snapshots alone cannot verify closed-minute signals, premium stops, time exits or drawdown.",
            "required": ["aligned closed one-minute SPY/QQQ bars", "same-contract intraday bid/ask paths and sizes", "source and observable timestamps", "session calendars and fee assumptions"],
            "next_step": "Export aligned inputs to the replay schema; this inventory does not evaluate replay input files."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(inventory(args.repo_root), indent=2))
