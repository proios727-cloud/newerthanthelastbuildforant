"""Synthetic paper example, never a market recommendation or live connection."""
import argparse
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path

from engine import (PaperLedger, fair_value_gate, no_vig,
                    empirical_joint_probability, quarter_kelly, kalshi_depth_ask)


def run():
    fill = kalshi_depth_ask({"yes_dollars":[[".48","30"]], "no_dollars":[[".50","20"], [".49","20"]]},
                            side="yes", quantity=10, quote_timestamp=999, now=1000)
    decision = fair_value_gate(p_lower=.65, bid=.48, ask=float(fill.average_ask),
                               fee_per_contract=.015, slippage_per_contract=.005,
                               quote_timestamp=999, source_timestamp=990, now=1000)
    size = quarter_kelly(p_lower=.65, effective_cost=decision.effective_cost, bankroll=1000)
    ledger = PaperLedger(":memory:")
    identifier = ledger.enter(market="SYNTHETIC-NO-REAL-MARKET", side="yes", quantity=10, ask=".50", entry_fee=".15")
    first = ledger.exit(position_id=identifier, quantity=4, bid=".60", exit_fee=".04")
    second = ledger.exit(position_id=identifier, quantity=6, bid=".55", exit_fee=".06")
    result = dict(label="SYNTHETIC PAPER DATA: hypothetical probabilities, fees and fills; no live data or orders",
                  depth_fill=asdict(fill), decision=asdict(decision), risk_size=asdict(size),
                  no_vig_reference=no_vig({"home":1.8, "away":2.1}, complete=True, mutually_exclusive=True),
                  aligned_correlated_joint=empirical_joint_probability([[True,True,False,False], [True,True,False,False]]),
                  realized_exit_pnl=[first, second], position=ledger.position(identifier))
    ledger.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("demo.synthetic.json"))
    args = parser.parse_args()
    report = json.dumps(run(), indent=2, default=str, allow_nan=False) + "\n"
    args.output.write_text(report, encoding="utf-8")
    print(report)
