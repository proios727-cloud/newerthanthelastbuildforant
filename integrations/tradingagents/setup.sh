#!/usr/bin/env bash
# Clone, install, and test TradingAgents next to this repo.
set -euo pipefail
DIR="${TA_DIR:-$HOME/TradingAgents}"
[ -d "$DIR" ] || git clone --depth 1 https://github.com/TauricResearch/TradingAgents.git "$DIR"
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q -e "$DIR[dev]"
(cd "$DIR" && .venv/bin/pytest -q)
echo "Ready. Use: $DIR/.venv/bin/python integrations/tradingagents/run_desk.py TICKER YYYY-MM-DD"
