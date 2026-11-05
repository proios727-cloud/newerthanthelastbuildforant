# Two independent paper bots

The crypto and sports folders are standalone projects with separate capital, databases, configurations, logs and start/stop commands. The deterministic loops use Python standard library; optional conversational agents are separate and are not necessary to run a collector. The crypto runner currently trades simulated BTC/SOL spot positions, not Kalshi crypto binaries. The sports runner uses simulated Kalshi binary positions.

1. Install Python 3.10 or newer on the machine that will stay awake.
2. Extract the desired desk folder. Start with its runtime/README.md and run its diagnostic command.
3. Choose a PAPER bankroll. Launch with start-paper.bat on Windows (Python Launcher needed) or start-paper.sh on Mac/Linux. No real deposit is required. Defaults keep configured gates; do not loosen fees to produce attractive results.
4. Sports needs an Odds API key in the environment and an explicit reviewed event/ticker/outcome/rules/fee mapping. Its default readiness check rejects the placeholder configuration. The free plan is sufficient for limited diagnostics, not unlimited collection.
5. Use the desk stop command or Ctrl+C. Inspect status and unresolved positions. Remove HALT explicitly before restart. Save each SQLite DB securely on its running host; databases are not included in the clean deliverable.

Crypto runtime live diagnostics and public history were tested from this workspace. Synthetic fixtures verify execution logic; they are not market profits. Read CASH-READINESS.md before subscribing or funding. Live private orders, authenticated broker reconciliation, sports in-play forecasts/combos and production cloud deployment are not implemented. Depositing cash does not activate live trading.

Current chart research: fixed EMA trend/daily regime, pullback and breakout hypotheses compared on public Kraken 1h/4h data with fee and slippage assumptions. The held-out 4h EMA result is positive but only one trade per asset and below fee-adjusted same-exposure buy-and-hold. The tested strategies have not established a capital-ready advantage. Default runtime fees exceed the configured maximum roundtrip cost, so new entries are intentionally blocked.
