#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python3 runtime/bot.py --config runtime/config.4h-research.json --db runtime/state/4h-research.sqlite --bankroll "${PAPER_BANKROLL:-1000}" --loop --interval 60 "$@"
