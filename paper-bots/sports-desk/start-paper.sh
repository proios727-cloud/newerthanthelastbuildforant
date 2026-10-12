#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python3 runtime/bot.py --config runtime/config.example.json --bankroll "${PAPER_BANKROLL:-1000}" --loop 300 "$@"
