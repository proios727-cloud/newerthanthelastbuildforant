# Independent paper bots

Crypto and sports are standalone Python projects with independent bankrolls, configuration, SQLite state and launch commands. No private exchange orders are installed. Start with START-HERE.md and CASH-READINESS.md. Optional eve agent files remain in the earlier downloadable artifact; these runners do not require Node or model credentials.

From the repository root:

```powershell
py -3 paper-bots/sports-desk/runtime/bot.py --check-api
py -3 paper-bots/crypto-desk/runtime/bot.py --check --config paper-bots/crypto-desk/runtime/config.4h-research.json
```

To reuse an existing local .env without copying it, add `--env-file` with its actual quoted path to the sports command. The key is not displayed. No key is stored in this branch; API access and quota remain unverified until run with your environment.

Crypto: 53 engineering test executions passed; sports:52. These include copied common33-test core plus desk20/19 tests. Backtests have not established positive edge. Sports needs verified rules/fees/event mappings before market paper execution.
